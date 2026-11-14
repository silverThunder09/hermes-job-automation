"""Build a private, local review from supplied evidence; never submit or write state."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlsplit

from .config import Settings
from .documents import create_application_documents
from .eligibility import check_eligibility
from .models import Posting
from .scoring import validate_evaluation
from .state import create_state_store, normalize_url, posting_key
from .writing import validate_draft_numbers


def _object(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError("Case object does not match its explicit schema.")
    return value


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Case text must be a nonempty string.")
    return value


def _strings(value, required=False):
    if not isinstance(value, list) or (required and not value):
        raise ValueError("Case list has an invalid structure.")
    for item in value:
        _text(item)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON fields are not allowed.")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("Nonfinite JSON numbers are not allowed.")


def _observed(value):
    _text(value)
    for pattern in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            stamp = datetime.strptime(value, pattern)
            break
        except ValueError:
            continue
    else:
        raise ValueError("Observation must include an ISO timestamp and timezone.")
    if stamp > datetime.now(timezone.utc):
        raise ValueError("Observation must not be in the future.")
    return stamp


def _validate_posting(value):
    _object(value, Posting.__dataclass_fields__)
    for field in ("platform", "title", "company", "url", "collected_at", "source_kind"):
        _text(value[field])
    identifier = value["platform_id"]
    if identifier is not None:
        _text(identifier)
        if identifier != identifier.strip():
            raise ValueError("Posting identifier has surrounding whitespace.")
    for field in ("deadline", "location", "experience", "education", "employment_type"):
        if value[field] is not None and not isinstance(value[field], str):
            raise ValueError("Posting fields must be strings or null.")
    if not isinstance(value["requirements"], str):
        raise ValueError("Posting requirements must be text.")
    _strings(value["skills"])
    url = value["url"]
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or any(c.isspace() for c in url)):
            raise ValueError()
        parsed.port
    except ValueError:
        raise ValueError("Posting URL must be a valid public HTTPS URL.") from None
    return Posting.from_dict(value)


def _validate_source_format(source, data):
    """Check PDF container markers or parse DOCX; not a full PDF conformance audit."""
    if source.suffix.lower() == ".docx":
        from docx import Document

        try:
            Document(str(source))
        except Exception:
            raise ValueError("Source is not a readable DOCX package.") from None
        return
    header = re.match(rb"%PDF-(?:1\.[0-7]|2\.0)[\r\n]", data)
    footer = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*\Z", data[-4096:])
    if not header or not footer:
        raise ValueError("Source is not a supported PDF container.")
    offset = int(footer.group(1))
    marker = data[offset:offset + 64]
    if not (marker.startswith(b"xref") or re.match(rb"\d+\s+\d+\s+obj\b", marker)):
        raise ValueError("Source PDF cross-reference marker is invalid.")


def _prepare(case_file, output_dir):
    try:
        payload = json.loads(case_file.read_text(encoding="utf-8"),
                             object_pairs_hook=_pairs, parse_constant=_invalid_constant)
    except (OSError, ValueError):
        raise ValueError("Case input could not be read as strict JSON.") from None
    _object(payload, ("schema_version", "posting_key", "posting_snapshot", "posting_observed_at",
                      "source", "profile", "evaluation", "documents", "missing_information"))
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ValueError("Unsupported case schema version.")
    _text(payload["posting_key"])
    posting = _validate_posting(payload["posting_snapshot"])
    if posting_key(posting) != payload["posting_key"]:
        raise ValueError("Posting snapshot and key do not match.")
    observed = _observed(payload["posting_observed_at"])
    _strings(payload["missing_information"])
    if not isinstance(payload["profile"], dict):
        raise ValueError("Profile evidence must be an object.")
    source_data = _object(payload["source"], ("path", "sha256", "kind"))
    _text(source_data["path"])
    if (not isinstance(source_data["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", source_data["sha256"]) is None
            or source_data["kind"] not in ("portfolio", "resume")):
        raise ValueError("Source provenance is invalid.")
    source = (case_file.parent / source_data["path"]).resolve()
    if source.suffix.lower() not in (".pdf", ".docx") or not source.is_file():
        raise ValueError("Source must be an existing PDF or DOCX file.")
    if output_dir.exists():
        raise FileExistsError("Output already exists; choose a new folder.")
    if any(path == output_dir or path in output_dir.parents or output_dir in path.parents
           for path in (source, case_file)) or any(path.is_file() for path in output_dir.parents):
        raise ValueError("Output path overlaps an input or is not a directory path.")
    data = source.read_bytes()
    before = hashlib.sha256(data).hexdigest()
    if before != source_data["sha256"]:
        raise ValueError("Source hash does not match the supplied evidence.")
    _validate_source_format(source, data)
    supplied = _object(payload["evaluation"], (
        "technical_fit", "work_fit", "project_fit", "preferred_qualifications", "total",
        "rationale", "gaps", "eligibility", "model"))
    for field in ("technical_fit", "work_fit", "project_fit", "preferred_qualifications", "total"):
        if type(supplied[field]) is not int:
            raise ValueError("Evaluation scores must be integers.")
    _strings(supplied["rationale"], required=True)
    _strings(supplied["gaps"])
    _text(supplied["model"])
    if (not isinstance(supplied["eligibility"], str)
            or supplied["eligibility"] not in ("eligible", "review", "excluded")):
        raise ValueError("Evaluation eligibility must be an explicit supported string.")
    evaluation = validate_evaluation(supplied, model=supplied["model"])
    draft = _object(payload["documents"], ("resume", "cover_letter"))
    for value in draft.values():
        _text(value)
    validate_draft_numbers(payload["profile"], posting, draft)
    return payload, posting, source, before, observed, evaluation


def build_case(settings: Settings, case_file: Path, output_dir: Path) -> Dict[str, Any]:
    case_file, output_dir = case_file.resolve(), output_dir.resolve()
    payload, posting, source, before, observed, evaluation = _prepare(case_file, output_dir)
    store = create_state_store(settings, read_only=True)
    stored = store.get_posting(payload["posting_key"])
    if not stored:
        raise ValueError("Posting is not registered in state storage.")
    registered = _validate_posting(stored)
    if (posting_key(registered) != payload["posting_key"]
            or any(getattr(registered, field) != getattr(posting, field)
                   for field in ("platform", "platform_id", "company", "title"))
            or normalize_url(registered.url) != normalize_url(posting.url)):
        raise ValueError("Registered posting identity does not match the snapshot.")
    eligibility = check_eligibility(posting)
    reasons = []
    if eligibility.status != "eligible":
        reasons.append("hard_filter_" + eligibility.status)
    if evaluation.eligibility != "eligible":
        reasons.append("evaluation_not_eligible")
    if evaluation.total < settings.minimum_score:
        reasons.append("below_minimum_score")
    if datetime.now(timezone.utc) - observed > timedelta(hours=24):
        reasons.append("observation_stale")
    output_dir.mkdir(parents=True, exist_ok=False)
    files = []
    if not reasons:
        label = ("포트폴리오 기반 신규 초안" if payload["source"]["kind"] == "portfolio"
                 else "원본 이력서 기반 검토 초안") + " · 최종 제출본 아님"
        files = create_application_documents(output_dir / "documents", posting,
                                             label + "\n\n" + payload["documents"]["resume"],
                                             label + "\n\n" + payload["documents"]["cover_letter"])
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    if after != before:
        raise ValueError("Source changed during the build; artifacts are not verified.")
    if not reasons and (len(files) != 4 or not all(path.is_file() for path in files)):
        raise ValueError("Document generation did not complete.")
    result = {
        "status": ("held" if reasons else "needs_information" if payload["missing_information"]
                   else "ready_for_user_review"),
        "posting_key": payload["posting_key"],
        "posting_observed_at": payload["posting_observed_at"],
        "evaluation": evaluation.to_dict(),
        "eligibility": eligibility.to_dict(),
        "reasons": reasons,
        "missing_information": payload["missing_information"],
        "source": {"kind": payload["source"]["kind"], "sha256_before": before,
                   "sha256_after": after},
        "files": [str(path) for path in files],
        "review_file": str(output_dir / "review.json"),
        "state_read_only": True,
        "external_state_writes": False,
        "application_submitted": False,
        "external_uploads": False,
        "final_user_approved": False,
        "sheet": {"status": "not_written"},
        "telegram": {"status": "not_written"},
    }
    with (output_dir / "review.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    return result
