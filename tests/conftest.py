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


@pytest.fixture
def temp_state_path(tmp_path):
    return Path(tmp_path) / "state.sqlite3"


@pytest.fixture
def submission_settings(tmp_path):
    return SimpleNamespace(
        auto_submit=False,
        form_autofill_enabled=False,
        submission_approval_file=Path(tmp_path) / "approvals.json",
    )
