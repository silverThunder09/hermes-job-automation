import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import HTTPSHandler, build_opener
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from hermes_job_automation.models import Posting


@pytest.fixture
def now():
    return datetime(2026, 11, 3, 12, 0, tzinfo=ZoneInfo("Asia/Seoul"))


@pytest.fixture
def posting():
    def make(**overrides):
        values = {
            "platform": "테스트",
            "platform_id": "123",
            "company": "검증회사",
            "title": "Java 백엔드 신입 개발자",
            "url": "https://example.invalid/jobs/123",
            "deadline": "2026-11-30",
            "location": "서울 강남구",
            "experience": "신입",
            "education": "고졸 이상",
            "employment_type": "정규직",
            "requirements": "Java, Spring Boot",
            "source_kind": "test",
        }
        values.update(overrides)
        return Posting(**values)

    return make


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch):
    """Never read the operator's .env or inherit remote credentials in unit tests."""
    monkeypatch.setattr("hermes_job_automation.config._load_dotenv", lambda: None)
    for name in ("JOB_ASSIST_STATE_BACKEND", "SUPABASE_URL", "SUPABASE_SECRET_KEY",
                 "SUPABASE_STORAGE_BUCKET"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def submission_settings(tmp_path):
    return SimpleNamespace(
        auto_submit=False,
        form_autofill_enabled=False,
        submission_approval_file=Path(tmp_path) / "approvals.json",
    )

@pytest.fixture
def postgrest(monkeypatch):
    calls = []
    replies = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def do_PATCH(self):
            self.respond()

        def respond(self):
            size = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(size)
            calls.append((self.command, self.path, dict(self.headers), json.loads(body) if body else None))
            reply = replies.pop(0) if replies else (500, {}, {})
            status, payload, headers = reply(calls) if callable(reply) else reply
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class LocalHTTPS(HTTPSHandler):
        def https_open(self, req):
            req.host = "127.0.0.1:{}".format(server.server_port)
            return self.do_open(http.client.HTTPConnection, req)

    def local_opener(*handlers):
        return build_opener(LocalHTTPS(), *handlers)

    monkeypatch.setattr("hermes_job_automation.supabase_state.build_opener", local_opener)
    yield SimpleNamespace(calls=calls, replies=replies)
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def state_settings(tmp_path):
    return SimpleNamespace(state_backend="supabase", data_dir=tmp_path,
                           supabase_url="https://fixture.supabase.co",
                           supabase_secret_key="sb_secret_test_only",
                           supabase_storage_bucket="job-artifacts")


@pytest.fixture
def health_contract(postgrest):
    def queue():
        tables = ["job_assist_applications", "job_assist_evaluations", "job_assist_postings",
                  "job_assist_runs", "job_assist_schema_versions"]
        postgrest.replies.extend([(200, {"schema_version": 1, "tables": tables, "rls_enabled": True}, {})]
                                + [(200, [], {})] * 5
                                + [(200, {"id": "job-artifacts", "public": False}, {})])
    return queue


@pytest.fixture
def smoke_contract(postgrest, health_contract):
    """Scripted HTTP transcript, NOT a persistence implementation or database."""
    def queue(corrupt=None):
        health_contract()
        start = len(postgrest.calls) + len(postgrest.replies)

        def request_payload(relative):
            return postgrest.calls[start + relative][3]

        def posting_reply(calls):
            payload = dict(request_payload(1)["p_payload"])
            if corrupt == "posting":
                payload["company"] = "wrong response"
            return 200, [{"payload_json": payload}], {}

        def eligibility_reply(calls):
            return 200, [{"eligibility_json": request_payload(1)["p_eligibility"]}], {}

        def evaluation_reply(calls):
            return 200, [{"evaluation_json": request_payload(4)["evaluation_json"]}], {}

        def application_reply(calls):
            request = request_payload(6)
            return 200, [{"posting_key": "wrong:key" if corrupt == "application_key" else request["p_key"], "status": "manual_review",
                          "attempt_id": None, "submitted_at": None, "confirmation_evidence": None,
                          "notes": {}, "updated_at": request["p_now"]}], {}

        def run_reply(calls):
            payload = dict(request_payload(15))
            payload["run_id"] = "wrong-run" if corrupt == "run_id" else request_payload(0)["run_id"]
            if corrupt == "run":
                payload["report_json"] = {"wrong": True}
            return 200, [payload], {}

        postgrest.replies.extend([
            (201, None, {}), (200, True, {}), posting_reply, eligibility_reply,
            (201, None, {}), evaluation_reply, (200, None, {}), application_reply,
            (200, False, {}), (200, False, {}), (200, None, {}), application_reply,
            posting_reply, eligibility_reply, evaluation_reply,
            (204, None, {}), run_reply,
        ])
    return queue
