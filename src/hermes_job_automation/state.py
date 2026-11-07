import hashlib
from typing import Any, Dict, Optional, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Posting


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "search_uuid",
    "searchtype",
    "searchword",
    "view_type",
    "logpath",
    "listno",
    "sc",
    "refernonce",
    "t_category",
}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host if not port or port in (80, 443) else "{}:{}".format(host, port)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower() or "https", netloc, path, urlencode(sorted(query)), ""))


def posting_key(posting: Posting) -> str:
    if posting.platform_id:
        return "{}:{}".format(posting.platform.lower(), posting.platform_id.strip())
    digest = hashlib.sha256(normalize_url(posting.url).encode("utf-8")).hexdigest()
    return "{}:{}".format(posting.platform.lower(), digest)


class StateStore(Protocol):
    """Type-only application contract; never a local storage implementation."""

    def save_posting(self, posting: Posting, eligibility: Dict[str, Any]) -> bool: ...
    def get_posting(self, key: str) -> Optional[Dict[str, Any]]: ...
    def get_eligibility(self, key: str) -> Optional[Dict[str, Any]]: ...
    def save_evaluation(self, posting: Posting, evaluation: Dict[str, Any]) -> None: ...
    def get_evaluation(self, key: str) -> Optional[Dict[str, Any]]: ...
    def get_application(self, key: str) -> Optional[Dict[str, Any]]: ...
    def application_status(self, key: str) -> Optional[str]: ...
    def record_application(self, key: str, status: str, now: str) -> None: ...
    def claim_submission(self, key: str, attempt_id: str, now: str) -> None: ...
    def finish_submission(self, key: str, status: str, now: str, evidence: str = "") -> None: ...
    def create_run(self, run_id: str, started_at: str) -> None: ...
    def finish_run(self, run_id: str, finished_at: str, status: str, report: Dict[str, Any]) -> None: ...
    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]: ...
    def health(self) -> Dict[str, Any]: ...


def create_state_store(settings, read_only: bool = False) -> StateStore:
    """Reject obsolete/unknown selections and incomplete credentials; never fall back."""
    if getattr(settings, "state_backend", "supabase") != "supabase":
        raise ValueError("JOB_ASSIST_STATE_BACKEND supports only supabase; remove obsolete or invalid backend settings.")
    from .supabase_state import SupabaseStateStore

    return SupabaseStateStore(
        getattr(settings, "supabase_url", ""),
        getattr(settings, "supabase_secret_key", ""),
        getattr(settings, "supabase_storage_bucket", ""),
        read_only=read_only,
    )
