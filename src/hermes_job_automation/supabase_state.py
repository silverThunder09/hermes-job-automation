"""Service-role PostgREST state adapter; no SDK, redirects, or SQL execution API."""
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import Posting
from .state import normalize_url, posting_key


class StateStorageError(RuntimeError):
    """A deliberately credential-free storage failure."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise StateStorageError("State storage refused an HTTP redirect.")


class SupabaseStateStore:
    def __init__(self, url: str, secret_key: str, bucket: str, read_only: bool = False):
        if not re.fullmatch(r"https://[a-z0-9-]+\.supabase\.co/?", url or ""):
            raise ValueError("SUPABASE_URL must be a hosted HTTPS Supabase origin, without a path or credentials.")
        if not secret_key.startswith("sb_secret_") or any(c.isspace() for c in secret_key):
            raise ValueError("SUPABASE_SECRET_KEY must be a modern server-side secret key.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", bucket or ""):
            raise ValueError("SUPABASE_STORAGE_BUCKET is required and must be a bucket identifier.")
        self._origin = url.rstrip("/")
        self._secret_key = secret_key
        self._bucket = bucket
        self._read_only = read_only
        self._opener = build_opener(_NoRedirect())

    def _request(self, path: str, method: str = "GET", payload=None, prefer: str = ""):
        # Paths are internal constants or URL-encoded identifiers, never caller URLs.
        if self._read_only and method != "GET":
            raise StateStorageError("State storage is read-only.")
        try:
            data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8") if payload is not None else None
            request = Request(self._origin + path, data=data, method=method, headers={
                "apikey": self._secret_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            })
            if prefer:
                request.add_header("Prefer", prefer)
            with self._opener.open(request, timeout=30) as response:
                body = response.read(8 * 1024 * 1024 + 1)
                if len(body) > 8 * 1024 * 1024:
                    raise StateStorageError("State storage response exceeds the size limit.")
                return json.loads(body.decode("utf-8")) if body else None
        except StateStorageError:
            raise
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise StateStorageError("State storage HTTP failure ({}); inspect schema/permissions or reconcile uncertain writes.".format(status)) from None
        except Exception:
            # Never expose response bodies, URLs, request headers, or network exception text.
            raise StateStorageError("State storage transport/JSON failure; reconcile uncertain writes before retrying.") from None

    def _rpc(self, name: str, payload: Dict[str, Any]):
        return self._request("/rest/v1/rpc/job_assist_" + name, "POST", payload)

    def _get(self, table: str, field: str, key: str):
        query = urlencode({"posting_key": "eq." + key, "select": field, "limit": "1"})
        rows = self._request("/rest/v1/job_assist_" + table + "?" + query)
        if not isinstance(rows, list) or (rows and not isinstance(rows[0], dict)):
            raise StateStorageError("State storage returned an unexpected row response.")
        return rows[0].get(field) if rows else None

    def save_posting(self, posting: Posting, eligibility: Dict[str, Any]) -> bool:
        result = self._rpc("save_posting", {
            "p_key": posting_key(posting), "p_url": normalize_url(posting.url),
            "p_platform": posting.platform.lower(), "p_platform_id": (posting.platform_id or "").strip() or None,
            "p_payload": posting.to_dict(), "p_eligibility": eligibility, "p_now": posting.collected_at,
        })
        if not isinstance(result, bool):
            raise StateStorageError("State storage returned an unexpected save response.")
        return result

    def get_posting(self, key: str) -> Optional[Dict[str, Any]]:
        return self._get("postings", "payload_json", key)

    def get_eligibility(self, key: str) -> Optional[Dict[str, Any]]:
        return self._get("postings", "eligibility_json", key)

    def save_evaluation(self, posting: Posting, evaluation: Dict[str, Any]) -> None:
        self._request("/rest/v1/job_assist_evaluations?on_conflict=posting_key", "POST", {
            "posting_key": posting_key(posting), "evaluation_json": evaluation,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, prefer="resolution=merge-duplicates,return=minimal")

    def get_evaluation(self, key: str) -> Optional[Dict[str, Any]]:
        return self._get("evaluations", "evaluation_json", key)

    def get_application(self, key: str) -> Optional[Dict[str, Any]]:
        query = urlencode({"posting_key": "eq." + key, "select": "*", "limit": "1"})
        rows = self._request("/rest/v1/job_assist_applications?" + query)
        if not isinstance(rows, list) or (rows and not isinstance(rows[0], dict)):
            raise StateStorageError("State storage returned an unexpected application response.")
        return rows[0] if rows else None

    def application_status(self, key: str) -> Optional[str]:
        return self._get("applications", "status", key)

    def record_application(self, key: str, status: str, now: str) -> None:
        if status not in {"manual_review", "ready_for_approval"}:
            raise ValueError("Unsupported non-submission application status.")
        self._rpc("record_application", {"p_key": key, "p_status": status, "p_now": now})

    def claim_submission(self, key: str, attempt_id: str, now: str) -> None:
        self._rpc("claim_submission", {"p_key": key, "p_attempt_id": attempt_id, "p_now": now})

    def finish_submission(self, key: str, status: str, now: str, evidence: str = "") -> None:
        if status not in {"submitted", "unknown", "failed_before_submit", "manual_review"}:
            raise ValueError("Unsupported submission status.")
        self._rpc("finish_submission", {"p_key": key, "p_status": status, "p_now": now, "p_evidence": evidence})

    def create_run(self, run_id: str, started_at: str) -> None:
        self._request("/rest/v1/job_assist_runs", "POST", {
            "run_id": run_id, "started_at": started_at, "status": "running", "report_json": {},
        }, prefer="return=minimal")

    def finish_run(self, run_id: str, finished_at: str, status: str, report: Dict[str, Any]) -> None:
        query = urlencode({"run_id": "eq." + run_id})
        self._request("/rest/v1/job_assist_runs?" + query, "PATCH", {
            "finished_at": finished_at, "status": status, "report_json": report,
        }, prefer="return=minimal")

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        rows = self._request("/rest/v1/job_assist_runs?" + urlencode({"run_id": "eq." + run_id, "select": "*", "limit": "1"}))
        if not isinstance(rows, list) or (rows and not isinstance(rows[0], dict)):
            raise StateStorageError("State storage returned an unexpected run response.")
        return rows[0] if rows else None

    def health(self) -> Dict[str, Any]:
        columns = {
            "job_assist_applications": "posting_key,status,attempt_id,submitted_at,confirmation_evidence,notes,updated_at",
            "job_assist_evaluations": "posting_key,evaluation_json,updated_at",
            "job_assist_postings": "posting_key,normalized_url,platform,platform_id,company,title,payload_json,eligibility_json,first_seen_at,last_seen_at",
            "job_assist_runs": "run_id,started_at,finished_at,status,report_json",
            "job_assist_schema_versions": "version,installed_at",
        }
        probe = self._request("/rest/v1/rpc/job_assist_state_health")
        if (not isinstance(probe, dict) or probe.get("schema_version") != 1
                or probe.get("tables") != sorted(columns) or probe.get("rls_enabled") is not True):
            raise StateStorageError("State schema version/tables/RLS mismatch; apply the SQL migration first.")
        for table, fields in columns.items():
            rows = self._request("/rest/v1/" + table + "?" + urlencode({"select": fields, "limit": "0"}))
            if rows != []:
                raise StateStorageError("State storage returned an unexpected schema probe response.")
        bucket = self._request("/storage/v1/bucket/" + quote(self._bucket, safe=""))
        if not isinstance(bucket, dict) or bucket.get("id") != self._bucket or bucket.get("public") is not False:
            raise StateStorageError("State artifact bucket must exist and be private; no bucket was modified.")
        return {"backend": "supabase", "status": "ready", "schema_version": 1,
                "tables": sorted(columns), "bucket": self._bucket, "bucket_private": True}
