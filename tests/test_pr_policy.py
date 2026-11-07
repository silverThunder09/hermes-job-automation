"""Offline public-interface tests for PR metadata rules; never calls GitHub."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_pr_policy.py"


def load_policy():
    spec = importlib.util.spec_from_file_location("pr_policy", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def body(issue="Closes #12", adr="docs/adr/0001-example.md"):
    return ("## 연결 이슈\n" + issue + "\n\n## 변경 내용\n저장소 어댑터를 분리합니다.\n"
            "\n## 검증\n`python -m pytest` 종료 코드 0.\n\n## ADR\n" + adr +
            "\n\n## 외부 변경·롤백\n원격 변경 없음. 로컬 코드를 이전 버전으로 되돌립니다.\n")


def test_accepts_conventional_korean_title_and_real_issue_with_adr(tmp_path):
    target = tmp_path / "docs/adr/0001-example.md"
    target.parent.mkdir(parents=True)
    target.write_text("# ADR-0001\n", encoding="utf-8")
    assert load_policy().validate_pr("feat(state): Supabase 저장소 연결", body(), tmp_path) == []


@pytest.mark.parametrize("title", ["업데이트", "feat: ", "FEAT: add state", "feat(state): " + "x" * 101])
def test_rejects_invalid_titles_without_echoing_user_content(tmp_path, title):
    errors = load_policy().validate_pr(title, body(adr="N/A: 기술 선택 변경 없는 문서 오탈자 수정입니다."), tmp_path)
    assert any("제목" in item for item in errors)
    assert all(title not in item for item in errors)


@pytest.mark.parametrize("reference", ["Closes #번호", "Closes #0", "Closes #01", "N/A", "<!-- Closes #12 -->"])
def test_requires_real_positive_issue_identifier(tmp_path, reference):
    errors = load_policy().validate_pr("fix: 상태 보존", body(issue=reference, adr="N/A: 기술 선택 변경 없는 버그 수정입니다."), tmp_path)
    assert any("이슈" in item for item in errors)


def test_bootstrap_issue_exception_only_allows_docs_or_ci(tmp_path):
    content = body(issue="N/A: bootstrap", adr="N/A: 초기 규칙과 템플릿을 추가하는 문서 변경입니다.")
    policy = load_policy()
    assert policy.validate_pr("docs: 개발 규칙 도입", content, tmp_path) == []
    assert any("이슈" in e for e in policy.validate_pr("feat: 저장소 추가", content, tmp_path))


@pytest.mark.parametrize("adr", ["", "N/A", "docs/adr/9999-missing.md", "../docs/adr/0001.md"])
def test_rejects_missing_or_unsafe_adr_reference(tmp_path, adr):
    errors = load_policy().validate_pr("feat: 저장소 추가", body(adr=adr), tmp_path)
    assert any("ADR" in item for item in errors)


def test_rejects_empty_required_sections_and_commented_template_answers(tmp_path):
    content = body(adr="N/A: 기술 선택 변경 없는 문서 수정입니다.")
    content = content.replace("저장소 어댑터를 분리합니다.", "<!-- TODO: 실제 변경 내용을 입력 -->")
    errors = load_policy().validate_pr("docs: 문서 보완", content, tmp_path)
    assert any("변경 내용" in item for item in errors)


def test_cli_returns_failure_for_invalid_metadata(tmp_path):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"title": "bad", "body": ""}}), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), "--event", str(event), "--root", str(tmp_path)],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1
    assert "제목" in result.stdout
