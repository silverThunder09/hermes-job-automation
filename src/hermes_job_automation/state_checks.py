"""Explicit, retained public-sample storage checks (never submits or uploads)."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Posting
from .state import create_state_store, posting_key


PUBLIC_SAMPLE = {
    "platform": "saramin", "platform_id": "55385305", "company": "도슨티",
    "title": "AI-native Builder",
    "url": "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=55385305",
}


def state_health(settings) -> Dict[str, Any]:
    """Read-only diagnostics, including incomplete setup without opening storage."""
    if getattr(settings, "state_backend", "supabase") != "supabase":
        # Reuse the factory's clear selection error; never normalize a bad value.
        create_state_store(settings, read_only=True)
    missing = [name for name, attribute in (
        ("SUPABASE_URL", "supabase_url"), ("SUPABASE_SECRET_KEY", "supabase_secret_key"),
        ("SUPABASE_STORAGE_BUCKET", "supabase_storage_bucket"),
    ) if not getattr(settings, attribute, "")]
    if missing:
        return {"backend": "supabase", "status": "missing_configuration", "missing": missing}
    return create_state_store(settings, read_only=True).health()


def _verify(condition: bool, check: str) -> None:
    if not condition:
        raise RuntimeError("State smoke verification failed: {}; samples were retained for reconciliation.".format(check))


def run_state_smoke(settings, explicit_write: bool = False, sample_file: Optional[Path] = None) -> Dict[str, Any]:
    if not explicit_write:
        raise ValueError("state-smoke requires --explicit-write; this check retains a new public sample.")
    source = dict(PUBLIC_SAMPLE)
    if sample_file is not None:
        source = json.loads(sample_file.read_text(encoding="utf-8"))
    if (not isinstance(source, dict) or set(source) - set(PUBLIC_SAMPLE)
            or any(not isinstance(source.get(k), str) or not source[k].strip() for k in ("company", "title", "url"))):
        raise ValueError("Sample file must be a public-only JSON object with company/title/url and optional platform/platform_id.")
    parts = urlsplit(source["url"])
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("Sample source must be a public HTTPS URL without credentials.")
    # The original URL is retained as provenance. This meaningful non-tracking
    # parameter isolates every execution from real postings and earlier samples.
    sample_id = uuid.uuid4().hex
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "job_assist_smoke"]
    query.append(("job_assist_smoke", sample_id))
    sample_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    now = datetime.now(timezone.utc).isoformat()
    item = Posting(platform="state-smoke", platform_id=sample_id, company=source["company"],
                   title=source["title"], url=sample_url, source_kind="public_storage_smoke",
                   requirements="Storage test only; not a vacancy assessment. Public source: " + source["url"],
                   collected_at=now)
    store = create_state_store(settings)
    store.health()  # Fail closed before writing if schema or private bucket is absent.
    key = posting_key(item)
    run_id = "state-smoke-" + sample_id
    eligibility = {"status": "review", "reasons": ["Public storage smoke sample; not an eligibility assessment."]}
    evaluation = {"total": 0, "eligibility": "review", "model": "storage-smoke-not-an-assessment"}
    store.create_run(run_id, now)
    _verify(store.save_posting(item, eligibility), "fresh sample insert")
    _verify(store.get_posting(key) == item.to_dict(), "save/get")
    _verify(store.get_eligibility(key) == eligibility, "eligibility")
    store.save_evaluation(item, evaluation)
    _verify(store.get_evaluation(key) == evaluation, "evaluation")
    store.record_application(key, "manual_review", now)
    before = store.get_application(key)
    _verify(before is not None and before.get("posting_key") == key
            and before.get("status") == "manual_review", "sample application read-back")
    duplicate = Posting.from_dict(item.to_dict())
    duplicate.url += "&utm_source=state-smoke"
    _verify(store.save_posting(duplicate, {"status": "excluded"}) is False, "tracking URL dedupe")
    duplicate.platform_id = "duplicate-" + sample_id
    _verify(store.save_posting(duplicate, {"status": "excluded"}) is False, "normalized URL dedupe")
    store.record_application(key, "ready_for_approval", now)
    _verify(store.get_application(key) == before, "application status/notes unchanged")
    _verify(store.get_posting(key) == item.to_dict(), "original payload unchanged")
    _verify(store.get_eligibility(key) == eligibility, "original eligibility unchanged")
    _verify(store.get_evaluation(key) == evaluation, "evaluation survives dedupe")
    checks = {"save_get": True, "eligibility": True, "evaluation": True,
              "dedupe": True, "application_unchanged": True}
    # The persisted report describes only checks already exercised. Its own
    # read-back is verified afterward, not asserted in advance inside that report.
    report = {"public_sample": True, "sample_key": key, "checks": dict(checks)}
    store.finish_run(run_id, datetime.now(timezone.utc).isoformat(), "completed", report)
    saved_run = store.get_run(run_id)
    _verify(saved_run is not None and saved_run.get("run_id") == run_id
            and saved_run.get("status") == "completed" and saved_run.get("report_json") == report,
            "run read-back")
    checks["run_readback"] = True
    return {"status": "verified", "backend": "supabase",
            "run_id": run_id, "sample_key": key, "source_url": source["url"],
            "checks": checks, "retained": True, "uploads": False, "real_applications": False}
