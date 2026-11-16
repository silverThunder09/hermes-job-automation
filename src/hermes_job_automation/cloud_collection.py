"""Save-only consumer of untrusted public-browser collection data.

Validation never accesses configuration or storage. Unsupported/ambiguous evidence
is deliberately rejected, not repaired into an eligible posting.
"""
import json
import os
import re
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from .eligibility import check_eligibility
from .models import Posting
from .state import normalize_url, posting_key


MAX_BATCH_BYTES = 256 * 1024
_TEXT_LIMITS = {"platform": 20, "platform_id": 40, "title": 500, "company": 300,
                "url": 200, "deadline": 200, "location": 500, "experience": 1000,
                "education": 500, "employment_type": 200, "requirements": 32000,
                "collected_at": 40, "source_kind": 50}
_NULLABLE = {"deadline", "location", "experience", "education", "employment_type"}


def _require(condition):
    if not condition:
        raise ValueError("Invalid cloud collection batch.")


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Invalid cloud collection batch.")


def _utc(value):
    _require(isinstance(value, str) and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)", value))
    # PostgreSQL trims fractional trailing zeroes; Python 3.9 accepts only
    # three or six digits. Pad a parsing copy and preserve the source value.
    normalized = re.sub(r"\.(\d{1,6})(?=Z|\+00:00$)",
                        lambda match: "." + match.group(1).ljust(6, "0"), value)
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))


def _text(value, limit, nonempty=False):
    _require(isinstance(value, str) and len(value) <= limit)
    value.encode("utf-8", errors="strict")
    _require(not any(ord(c) < 32 and c not in "\n\r\t" for c in value))
    _require(not nonempty or bool(value.strip()))


def _outside_location_text(location, text):
    # Resolve the province before interpreting an ambiguous municipality name.
    # Gwangju-si is in Gyeonggi; Gwangju Metropolitan City remains outside scope.
    if re.match(r"^경기(?:도)?(?:\s|$)", location):
        return re.sub(r"(?<!\w)광주(?:시)?(?!\w)", "", text)
    return text


def _qualified_location(location):
    _require(re.match(r"^(?:경기(?:도)?|서울(?:특별시)?|인천(?:광역시)?)(?:\s|$)", location) is not None)
    outside = _outside_location_text(location, location)
    _require(not re.search(r"또는|부산|대구|대전|광주|울산|세종|강원|충청|전라|경상|제주|해외|전국|재택|/|,|\|", outside))


def _experience_conflicts(text):
    novice_exclusion = (
        r"신입(?:[은는이가을를])?\s*"
        r"(?:(?:지원|응시|채용|입사|접수)(?:[은는이가을를])?\s*)?"
        r"(?:불가|불가능|제외|미채용|대상\s*아님|받지\s*않|하지\s*않|할\s*수\s*없)"
    )
    experienced_only = (
        r"경력(?:자|직)\s*(?:(?:만|에\s*한해)\s*(?:지원|응시|채용|모집|가능)"
        r"|필수|전용|한정)"
    )
    return re.search(novice_exclusion, text) is not None or re.search(experienced_only, text) is not None


def _qualified(posting, current):
    education = re.sub(r"\s+", "", posting.education or "")
    _require(re.fullmatch(r"학력무관|고졸(?:이상)?", education) is not None)
    location = posting.location or ""
    _qualified_location(location)
    _require((posting.employment_type or "").strip() in {"정규직", "인턴"})
    role = " ".join((posting.title, posting.requirements))
    keyword_text = " ".join((role, *posting.skills))
    _require(re.search(r"(?<![\w])(?:java|spring)(?![\w])", keyword_text, re.I) is not None)
    _require(re.search(r"백엔드|백앤드|(?<![a-z])backend(?![a-z])|서버", role, re.I) is not None)
    _require(not re.search(r"제조|생산|기계|금형|프론트엔드", posting.title))
    # Bridge exact paid-backend-zero evidence for the existing junior filter on
    # a disposable copy only; preserve every field of the original payload.
    candidate = posting
    _require(re.fullmatch(r"신입|경력\s*무관|유급\s*백엔드\s*경력\s*0\s*년", posting.experience or "") is not None)
    _require(not _experience_conflicts(role))
    _require(not re.search(r"(?:모집|채용|접수)\s*(?:마감|종료|중단)(?!일|예정|임박)", role))
    _require(not re.search(r"계약직|일용직|프리랜서|파견직", posting.requirements))
    location_detail = _outside_location_text(location, posting.requirements)
    _require(not re.search(r"근무(?:지|지역)\s*[:：]?\s*(?:부산|대구|대전|광주|울산|세종|강원|충청|전라|경상|제주|해외)", location_detail))
    if re.fullmatch(r"유급\s*백엔드\s*경력\s*0\s*년", posting.experience or ""):
        candidate = replace(posting, experience=posting.experience + " 신입")
    _require(check_eligibility(candidate, now=current).status == "eligible")


def load_cloud_batch(path, now=None) -> List[Posting]:
    """Validate <=256 KiB strict UTF-8 JSON and return 1..10 qualified postings.

    Raises a fixed ValueError without input text, paths or exception chaining.
    All rows pass before the caller receives any Posting.
    """
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(MAX_BATCH_BYTES + 1)
        _require(len(raw) <= MAX_BATCH_BYTES)
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
        _require(isinstance(data, dict) and set(data) == {"schema_version", "source", "collected_at", "postings"})
        _require(type(data["schema_version"]) is int and data["schema_version"] == 1)
        _require(data["source"] == "jumpit_public_browser")
        stamp = _utc(data["collected_at"])
        current = now if now is not None else datetime.now(timezone.utc)
        _require(isinstance(current, datetime) and current.utcoffset() is not None)
        current = current.astimezone(timezone.utc)
        _require(timedelta(0) <= current - stamp <= timedelta(hours=24))
        rows = data["postings"]
        _require(isinstance(rows, list) and 1 <= len(rows) <= 10)
        result = []
        seen = [set(), set(), set()]
        for row in rows:
            _require(isinstance(row, dict) and set(row) == set(Posting.__dataclass_fields__))
            for name, limit in _TEXT_LIMITS.items():
                if row[name] is None and name in _NULLABLE:
                    continue
                _text(row[name], limit, nonempty=name != "requirements")
            _require(isinstance(row["skills"], list) and len(row["skills"]) <= 50)
            for skill in row["skills"]:
                _text(skill, 100, nonempty=True)
            _require(row["platform"] == "점핏" and row["source_kind"] == "agent_researched_public")
            _require(re.fullmatch(r"[0-9]{1,40}", row["platform_id"]) is not None)
            _require(row["url"] == "https://jumpit.saramin.co.kr/position/" + row["platform_id"])
            _require(_utc(row["collected_at"]) == stamp)
            posting = Posting(**row)
            _qualified(posting, current.astimezone(ZoneInfo("Asia/Seoul")))
            identities = (posting_key(posting), normalize_url(posting.url), (posting.platform, posting.platform_id))
            for prior, identity in zip(seen, identities):
                _require(identity not in prior)
                prior.add(identity)
            result.append(posting)
        return result
    except Exception:
        raise ValueError("Invalid cloud collection batch.") from None


_REVIEW = {"status": "review", "reasons": ["agent-researched", "user-review-pending"], "missing_information": []}


class CloudCollectionError(RuntimeError):
    """Fixed-message failure; inspect the private receipt, never exception text."""


def _checkpoint(path, receipt):
    # Reserve the target once with exclusive creation. Later checkpoints replace
    # it atomically, so a process crash leaves the last complete pending receipt.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(path.parent),
                                         prefix=".cloud-receipt-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(receipt, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _new_snapshot(snapshot, posting):
    _require(snapshot is not None)
    row = snapshot["posting"]
    expected = {"posting_key": posting_key(posting), "normalized_url": normalize_url(posting.url),
                "platform": posting.platform.lower(), "platform_id": posting.platform_id,
                "company": posting.company, "title": posting.title,
                "payload_json": posting.to_dict(), "eligibility_json": _REVIEW}
    _require({k: v for k, v in row.items() if k not in {"first_seen_at", "last_seen_at"}} == expected)
    _require(_utc(row["first_seen_at"]) == _utc(posting.collected_at)
             and _utc(row["last_seen_at"]) == _utc(posting.collected_at))
    _require(snapshot["evaluation"] is None and snapshot["application"] is None)


def _preserved(before, after, posting):
    _require(after is not None)
    original, current = before["posting"], after["posting"]
    _require(json.dumps({k: v for k, v in original.items() if k != "last_seen_at"}, sort_keys=True, allow_nan=False)
             == json.dumps({k: v for k, v in current.items() if k != "last_seen_at"}, sort_keys=True, allow_nan=False))
    _require(json.dumps([before["evaluation"], before["application"]], sort_keys=True, allow_nan=False)
             == json.dumps([after["evaluation"], after["application"]], sort_keys=True, allow_nan=False))
    _require(_utc(current["last_seen_at"]) == max(_utc(original["last_seen_at"]), _utc(posting.collected_at)))


def save_cloud_batch(settings, path, *, explicit_write=False, receipt_path, now=None) -> dict:
    """Save only validated postings, with exclusive durable attempt receipts.

    Invalid inputs and a missing explicit True are rejected before settings/store
    access. Only save_posting may write remotely; success requires exact readback
    and a second identical save returning False. All errors are redacted.
    """
    if explicit_write is not True:
        raise ValueError("Explicit cloud collection write approval is required.")
    postings = load_cloud_batch(path, now=now)
    receipt = {"schema_version": 1, "status": "pending", "attempts": [], "rows": []}
    try:
        target = Path(receipt_path)
        with target.open("x", encoding="utf-8") as handle:
            json.dump(receipt, handle)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        raise CloudCollectionError("Cloud collection receipt unavailable.") from None
    try:
        from .state import create_state_store
        store = create_state_store(settings)
        store.health()
        before = [store.lookup_posting_state(posting) for posting in postings]
        canonical_keys = [snapshot["posting"]["posting_key"] for snapshot in before if snapshot is not None]
        _require(len(canonical_keys) == len(set(canonical_keys)))
        for snapshot in before:
            if snapshot is not None:
                _utc(snapshot["posting"]["first_seen_at"])
                _utc(snapshot["posting"]["last_seen_at"])
        for posting, baseline in zip(postings, before):
            outcome = "existing_duplicate" if baseline is not None else "new"
            for number in (1, 2):
                attempt = {"key": posting_key(posting), "attempt": number, "status": "pending", "result": None}
                receipt["attempts"].append(attempt)
                _checkpoint(target, receipt)
                try:
                    result = store.save_posting(posting, _REVIEW)
                except Exception:
                    # A failed/malformed ACK is not proof of rollback or insertion.
                    # Persist uncertainty before the one identity-based readback;
                    # never issue a second save (including the duplicate probe).
                    attempt["status"] = "unknown"
                    _checkpoint(target, receipt)
                    observed = store.lookup_posting_state(posting)
                    if baseline is None:
                        _new_snapshot(observed, posting)
                    else:
                        _preserved(baseline, observed, posting)
                    attempt["status"] = "reconciled"
                    receipt["rows"].append({"key": posting_key(posting), "outcome": "reconciled_present",
                                            "duplicate_check": "not_verified"})
                    receipt["status"] = "reconciled"
                    _checkpoint(target, receipt)
                    return receipt
                attempt.update(status="reported", result=result)
                _checkpoint(target, receipt)
                after = store.lookup_posting_state(posting)
                if number == 1 and baseline is None:
                    _new_snapshot(after, posting)
                    outcome = "new" if result else "concurrent_duplicate"
                else:
                    _require(result is False)
                    _preserved(baseline, after, posting)
                baseline = after
            receipt["rows"].append({"key": posting_key(posting), "outcome": outcome, "duplicate_check": "verified"})
            _checkpoint(target, receipt)
        receipt["status"] = "verified"
        _checkpoint(target, receipt)
        return receipt
    except Exception:
        receipt["status"] = "unknown" if receipt["attempts"] else "failed"
        try:
            _checkpoint(target, receipt)
        except Exception:
            pass  # The last durable checkpoint is pending; never retry a write.
        raise CloudCollectionError("Cloud collection save could not be verified; inspect the receipt.") from None
