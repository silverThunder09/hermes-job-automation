"""Offline documentation contracts; not proof of deployed collection."""
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "docs/adr/0011-private-collection-writer.md"
LINK = re.compile(r"\[[^\]]+\]\(([^\s)]+)\)")
ENTRIES = (
    "README.md", "docs/OPERATIONS.md", "docs/CLOUD_DEVELOPMENT.md",
    "docs/PLATFORM_ACCESS.md", "docs/SARAMIN_ACCESS.md", "docs/adr/README.md",
    "docs/agents/README.md", "skills/job-search/SKILL.md",
)


@pytest.mark.parametrize("name", ENTRIES)
def test_selected_cloud_collection_decision_is_reachable_from_its_entry(name):
    path = ROOT / name
    targets = [
        (path.parent / unquote(urlsplit(target).path)).resolve()
        for target in LINK.findall(path.read_text(encoding="utf-8"))
        if not urlsplit(target).scheme and urlsplit(target).path
    ]
    assert DECISION.resolve() in targets, name


def test_selected_runtime_distinguishes_on_off_and_legacy_api():
    text = DECISION.read_text(encoding="utf-8")
    header = text.split("## ", 1)[0]
    assert "Accepted" in header
    assert "미구현" in header and "미배포" in header
    for contract in (
        "PC-on", "PC-off", "클라우드 브라우저/MCP", "GitHub Actions",
        "Supabase", "사람인 공식 API", "폐기", "manual_only", "approval_required",
    ):
        assert contract in text, contract


def test_remote_save_authority_does_not_claim_scheduled_or_submission_authority():
    text = DECISION.read_text(encoding="utf-8")
    for contract in (
        "최대 10개", "1회", "Java", "Spring", "학력무관/고졸", "0년",
        "collection", "storage", "DB 키", "고정", "중복", "재조회",
        "예약", "실제 지원", "삭제", "운영 SQL", "모델 인증", "별도",
        "CAPTCHA", "우회", "미검증",
    ):
        assert contract in text, contract


@pytest.mark.parametrize("name,obsolete", (
    ("README.md", "현재 자동 수집 구현은 승인된 공식 API 경로입니다"),
    ("README.md", "- 채용 사이트: 공식 API 신청·승인 및 사용범위 확인"),
    ("docs/OPERATIONS.md", "3. 사람인 API를 쓸 때는 이용 승인이 끝난 뒤"),
    ("skills/job-search/SKILL.md", "Use only approved official APIs and user-reviewed manual imports."),
))
def test_active_setup_no_longer_requires_the_retired_api(name, obsolete):
    assert obsolete not in (ROOT / name).read_text(encoding="utf-8")


def test_decision_local_links_resolve_without_private_workspace_paths():
    text = DECISION.read_text(encoding="utf-8")
    for target in LINK.findall(text):
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue
        resolved = (DECISION.parent / unquote(parsed.path)).resolve()
        resolved.relative_to(ROOT.resolve())
        assert resolved.is_file(), target
    assert "C:/Users/" not in text and "D:/hermes-job-automation/work/" not in text
