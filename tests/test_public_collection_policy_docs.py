"""Offline policy-document contracts, not a browser permission/runtime gate."""
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/PLATFORM_ACCESS.md"
DECISION = ROOT / "docs/adr/0012-public-collection-policy.md"
LINK = re.compile(r"\[[^\]]+\]\(([^\s)]+)\)")


def targets(path):
    return {
        (path.parent / unquote(urlsplit(value).path)).resolve()
        for value in LINK.findall(path.read_text(encoding="utf-8"))
        if not urlsplit(value).scheme and urlsplit(value).path
    }


def test_policy_distinguishes_missing_permission_from_an_applicable_restriction():
    text = POLICY.read_text(encoding="utf-8")
    assert "명시적 허가 미확인만으로 중단하지 않는다" in text
    assert "미확인은 허용 확정도 금지 확정도 아니다" in text
    assert "## 진행·중단 기준" in text
    decisions = {}
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == 3:
            decisions[cells[0]] = cells[1]
    assert decisions["명시적 허가 미확인만 있음"] == "진행 가능"
    assert decisions["적용되는 명시적 수집·복제 금지 또는 동의 요건"] == "해당 작업 중단"
    assert decisions["대상 경로의 robots 제한"] == "해당 경로 중단"
    assert decisions["접근 차단·CAPTCHA·로그인·OTP 요구"] == "중단"
    assert decisions["429·서버 오류·일시 접속 실패"] == "중단·대기"
    assert "플랫폼별 공식 허가가 없으면 브라우저 검색 화면을 반복 호출" not in text
    assert "허용 범위가 확인되기 전에는 반복 수집/제출을 활성화하지" not in text


@pytest.mark.parametrize("name", (
    "README.md", "docs/OPERATIONS.md", "docs/CLOUD_DEVELOPMENT.md",
    "docs/agents/README.md", "skills/job-search/SKILL.md",
    "skills/job-tailoring/SKILL.md", "docs/SARAMIN_ACCESS.md",
    "docs/adr/0012-public-collection-policy.md",
))
def test_active_entry_reaches_the_single_policy_owner(name):
    assert POLICY.resolve() in targets(ROOT / name)


def test_successor_decision_is_explicit_and_preserves_operational_boundaries():
    text = DECISION.read_text(encoding="utf-8")
    assert "Accepted" in text.split("## ", 1)[0]
    assert "#31" in text
    for contract in ("0011", "명시적 허가 미확인",
                     "미확인만으로", "사용자", "최대 10개", "1회", "CAPTCHA", "우회",
                     "DB 키", "개인정보", "출처", "예약", "실제 지원", "별도", "코드 변경 없음"):
        assert contract in text
    for target in targets(DECISION):
        target.relative_to(ROOT.resolve())
        assert target.is_file()
    assert DECISION.resolve() in targets(POLICY)
    assert DECISION.resolve() in targets(ROOT / "docs/adr/README.md")


@pytest.mark.parametrize("name", (
    "docs/adr/0011-private-collection-writer.md",
    "docs/adr/0006-actions-batch-boundary.md",
    "docs/SARAMIN_ACCESS.md",
))
def test_historical_stopping_conditions_are_superseded_not_silently_rewritten(name):
    path = ROOT / name
    header = path.read_text(encoding="utf-8").split("## ", 1)[0]
    assert "후속" in header
    assert DECISION.resolve() in targets(path)


def test_policy_keeps_provenance_minimal_scope_and_no_activation_claim():
    text = POLICY.read_text(encoding="utf-8")
    for contract in ("공개", "비로그인", "사용자 승인", "소량", "최소", "출처",
                     "user_reviewed_manual", "DB 쓰기", "개인정보", "유료", "예약",
                     "manual_only", "미구현", "기술적 실패", "허용 확정"):
        assert contract in text
    assert "공식 문의는 필수 선행 조건이 아니다" in text
