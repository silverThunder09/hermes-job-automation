import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional
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


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    report_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS postings (
                    posting_key TEXT PRIMARY KEY,
                    normalized_url TEXT NOT NULL UNIQUE,
                    platform TEXT NOT NULL,
                    platform_id TEXT,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    eligibility_json TEXT NOT NULL DEFAULT '{}',
                    evaluation_json TEXT NOT NULL DEFAULT '{}',
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS posting_platform_id
                    ON postings(platform, platform_id) WHERE platform_id IS NOT NULL;
                CREATE TABLE IF NOT EXISTS applications (
                    posting_key TEXT PRIMARY KEY REFERENCES postings(posting_key),
                    status TEXT NOT NULL,
                    attempt_id TEXT,
                    submitted_at TEXT,
                    confirmation_evidence TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS submission_approvals (
                    platform TEXT NOT NULL,
                    posting_id TEXT NOT NULL,
                    max_score INTEGER NOT NULL,
                    valid_until TEXT NOT NULL,
                    approved_at TEXT NOT NULL,
                    conditions_json TEXT NOT NULL,
                    PRIMARY KEY(platform, posting_id)
                );
                """
            )

    def save_posting(self, posting: Posting, eligibility: Dict[str, Any]) -> bool:
        key = posting_key(posting)
        normalized = normalize_url(posting.url)
        now = posting.collected_at
        payload = json.dumps(posting.to_dict(), ensure_ascii=False)
        eligibility_json = json.dumps(eligibility, ensure_ascii=False)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            exists = db.execute(
                "SELECT 1 FROM postings WHERE posting_key=? OR normalized_url=?",
                (key, normalized),
            ).fetchone()
            if exists:
                db.execute(
                    "UPDATE postings SET last_seen_at=? WHERE posting_key=? OR normalized_url=?",
                    (now, key, normalized),
                )
                db.commit()
                return False
            db.execute(
                """
                INSERT INTO postings (
                    posting_key, normalized_url, platform, platform_id, company, title,
                    payload_json, eligibility_json, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    normalized,
                    posting.platform,
                    posting.platform_id,
                    posting.company,
                    posting.title,
                    payload,
                    eligibility_json,
                    now,
                    now,
                ),
            )
            db.commit()
            return True

    def save_evaluation(self, posting: Posting, evaluation: Dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE postings SET evaluation_json=? WHERE posting_key=?",
                (json.dumps(evaluation, ensure_ascii=False), posting_key(posting)),
            )

    def get_posting(self, key: str) -> Optional[Dict[str, Any]]:
        with self.connect() as db:
            row = db.execute(
                "SELECT payload_json FROM postings WHERE posting_key=?", (key,)
            ).fetchone()
            return json.loads(row["payload_json"]) if row else None

    def get_eligibility(self, key: str) -> Optional[Dict[str, Any]]:
        with self.connect() as db:
            row = db.execute(
                "SELECT eligibility_json FROM postings WHERE posting_key=?", (key,)
            ).fetchone()
            return json.loads(row["eligibility_json"]) if row else None

    def record_application(self, key: str, status: str, now: str) -> None:
        if status not in {"manual_review", "ready_for_approval"}:
            raise ValueError("Unsupported non-submission application status.")
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO applications(posting_key, status, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(posting_key) DO UPDATE SET
                    status=excluded.status, updated_at=excluded.updated_at
                """,
                (key, status, now),
            )

    def create_run(self, run_id: str, started_at: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs(run_id, started_at, status) VALUES (?, ?, 'running')",
                (run_id, started_at),
            )

    def finish_run(self, run_id: str, finished_at: str, status: str, report: Dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE runs SET finished_at=?, status=?, report_json=? WHERE run_id=?",
                (finished_at, status, json.dumps(report, ensure_ascii=False), run_id),
            )

    def application_status(self, key: str) -> Optional[str]:
        with self.connect() as db:
            row = db.execute(
                "SELECT status FROM applications WHERE posting_key=?", (key,)
            ).fetchone()
            return row["status"] if row else None

    def claim_submission(self, key: str, attempt_id: str, now: str) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status FROM applications WHERE posting_key=?", (key,)
            ).fetchone()
            if row and row["status"] in {"submitting", "submitted", "unknown"}:
                db.rollback()
                raise RuntimeError("Submission already attempted; manual reconciliation is required.")
            db.execute(
                """
                INSERT INTO applications(posting_key, status, attempt_id, updated_at)
                VALUES (?, 'submitting', ?, ?)
                ON CONFLICT(posting_key) DO UPDATE SET
                    status='submitting', attempt_id=excluded.attempt_id, updated_at=excluded.updated_at
                """,
                (key, attempt_id, now),
            )
            db.commit()

    def finish_submission(
        self,
        key: str,
        status: str,
        now: str,
        evidence: str = "",
    ) -> None:
        if status not in {"submitted", "unknown", "failed_before_submit", "manual_review"}:
            raise ValueError("Unsupported submission status.")
        with self.connect() as db:
            db.execute(
                """
                UPDATE applications
                SET status=?, submitted_at=?, confirmation_evidence=?, updated_at=?
                WHERE posting_key=?
                """,
                (status, now if status == "submitted" else None, evidence, now, key),
            )
