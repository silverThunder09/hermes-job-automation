import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from .models import Evaluation, Posting
from .state import StateStore, posting_key


CHALLENGE_WORDS = (
    "captcha",
    "recaptcha",
    "otp",
    "one-time password",
    "인증번호",
    "추가 인증",
    "휴대폰 인증",
    "2단계 인증",
    "보안문자",
)
SUCCESS_WORDS = ("지원이 완료", "접수가 완료", "접수번호", "지원 완료", "입사지원 완료")


def detect_human_challenge(page_text: str) -> bool:
    lowered = page_text.lower()
    return any(word in lowered for word in CHALLENGE_WORDS)


def _approval_for(
    settings,
    posting: Posting,
    evaluation: Evaluation,
    approvals: Optional[list] = None,
) -> Dict[str, Any]:
    data = approvals
    if data is None:
        if not settings.submission_approval_file.exists():
            raise RuntimeError("PLATFORM_APPROVAL_MISSING")
        data = json.loads(settings.submission_approval_file.read_text(encoding="utf-8"))
    now = datetime.now().astimezone()
    for item in data:
        if item.get("platform") != posting.platform or not item.get("enabled"):
            continue
        allowed_ids = item.get("posting_ids", [])
        if posting.platform_id not in allowed_ids and "*" not in allowed_ids:
            continue
        domain = (urlparse(posting.url).hostname or "").lower()
        allowed_domains = [str(value).lower() for value in item.get("domains", [])]
        if allowed_domains and domain not in allowed_domains:
            continue
        if evaluation.total > int(item.get("max_score", 100)):
            continue
        valid_until = datetime.fromisoformat(item["valid_until"])
        if valid_until.tzinfo is None:
            valid_until = valid_until.astimezone()
        if valid_until < now:
            continue
        if not item.get("approved_at") or not item.get("conditions"):
            continue
        return item
    raise RuntimeError("MATCHING_PLATFORM_AND_POSTING_APPROVAL_MISSING")


def authorize_submission(
    settings,
    posting: Posting,
    evaluation: Evaluation,
    approvals: Optional[list] = None,
) -> Dict[str, Any]:
    if not settings.auto_submit:
        raise RuntimeError("AUTO_SUBMIT_DISABLED")
    if not settings.form_autofill_enabled:
        raise RuntimeError("FORM_AUTOFILL_DISABLED")
    if evaluation.eligibility != "eligible":
        raise RuntimeError("POSTING_NOT_CONFIRMED_ELIGIBLE")
    if not posting.platform_id:
        raise RuntimeError("POSTING_ID_REQUIRED_FOR_IDEMPOTENCY")
    return _approval_for(settings, posting, evaluation, approvals)


def submit_with_evidence(
    page,
    posting: Posting,
    evaluation: Evaluation,
    settings,
    store: StateStore,
    submit_selector: str,
    approvals: Optional[list] = None,
) -> str:
    authorize_submission(settings, posting, evaluation, approvals)
    if detect_human_challenge(page.locator("body").inner_text()):
        store.record_application(
            posting_key(posting), "manual_review", datetime.now().astimezone().isoformat()
        )
        return "manual_review"
    key = posting_key(posting)
    attempt_id = str(uuid.uuid4())
    store.claim_submission(key, attempt_id, datetime.now().astimezone().isoformat())
    try:
        page.locator(submit_selector).click()
    except Exception:
        store.finish_submission(
            key, "unknown", datetime.now().astimezone().isoformat()
        )
        return "unknown"
    text = page.locator("body").inner_text()
    if detect_human_challenge(text):
        store.finish_submission(key, "manual_review", datetime.now().astimezone().isoformat())
        return "manual_review"
    if any(word in text for word in SUCCESS_WORDS):
        store.finish_submission(
            key, "submitted", datetime.now().astimezone().isoformat(), evidence=text[:2000]
        )
        return "submitted"
    store.finish_submission(key, "unknown", datetime.now().astimezone().isoformat())
    return "unknown"


class DraftOnlyApplication:
    """Inspect and fill only fields with an explicit local mapping; never clicks submit."""

    def __init__(self, settings):
        self.settings = settings

    def fill_known_fields(self, page, values: Dict[str, str]) -> Dict[str, str]:
        if not self.settings.form_autofill_enabled:
            return {"status": "manual_only", "reason": "FORM_AUTOFILL_DISABLED"}
        filled = []
        for label, value in values.items():
            locator = page.get_by_label(label, exact=False)
            if locator.count() == 1 and value:
                locator.fill(value)
                filled.append(label)
        return {"status": "ready_for_review", "filled_fields": ",".join(filled)}
