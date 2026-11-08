"""Offline contracts for document routing, not an automatic agent loader."""
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "AGENTS.md"
INDEX = ROOT / "docs/agents/README.md"
HARNESS = (
    "AGENTS.md", "docs/agents/README.md", "docs/agents/development.md",
    "docs/agents/issue-tracker.md", "CONTRIBUTING.md", "docs/PR_AUTOMATION.md",
    "docs/WORKFLOW_POLICY.md", "skills/job-tailoring/SKILL.md",
)
LINK = re.compile(r"\[[^\]]+\]\(([^\s)]+)\)")


def links(path):
    return LINK.findall(path.read_text(encoding="utf-8"))


def section(text, heading):
    match = re.search(r"^## " + re.escape(heading) + r"\s*$", text, re.M)
    assert match, "Missing routing section: " + heading
    return re.split(r"^## ", text[match.end():], maxsplit=1, flags=re.M)[0]


def anchors(text):
    explicit = set(re.findall(r'<a id="([^"]+)"', text))
    for title in re.findall(r"^#{1,6} (.+)$", text, re.M):
        slug = re.sub(r"[^\w\s-]", "", title.lower()).replace(" ", "-")
        explicit.add(slug)
    return explicit


def test_root_is_smaller_than_original_and_keeps_task_scoped_loading():
    assert len(ROUTER.read_bytes()) < 2694
    text = ROUTER.read_text(encoding="utf-8")
    assert "Read only the matching entry" in text
    assert "not an automatic loader" in text
    assert "pip install" not in text
    assert "playwright install" not in text
    assert "docs/agents/development.md" in links(ROUTER)
    assert "skills/job-tailoring/SKILL.md" in links(ROUTER)
    assert "skills/job-search/SKILL.md" in links(ROUTER)


@pytest.mark.parametrize("heading,target", [
    ("Research", "../../skills/job-tailoring/SKILL.md#company-analysis"),
    ("Documents", "../../skills/job-tailoring/SKILL.md#local-ocr"),
    ("Access", "../SARAMIN_ACCESS.md"),
    ("Access", "../OPERATIONS.md#제출-승인"),
    ("Storage", "../SUPABASE_STATE.md"),
    ("Storage", "../GOOGLE_WORKSPACE_SETUP.md"),
    ("Runtime", "../../README.md#오프라인-브라우저-실행-진단"),
    ("Runtime", "../HERMES_OFFICIAL_RESEARCH.md"),
    ("Runtime", "../adr/0003-scheduled-collection-and-retention.md"),
    ("Product", "../PRODUCT_SCOPE.md"),
])
def test_feature_route_has_the_required_local_entry(heading, target):
    assert INDEX.is_file(), "Missing conditional feature index"
    content = section(INDEX.read_text(encoding="utf-8"), heading)
    assert target in LINK.findall(content)
    assert "docs/agents/README.md#" + heading.lower() in links(ROUTER)


@pytest.mark.parametrize("name", HARNESS)
def test_harness_links_and_anchors_resolve_within_repository(name):
    path = ROOT / name
    assert path.is_file(), "Missing harness document: " + name
    for target in links(path):
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue
        resolved = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
        resolved.relative_to(ROOT.resolve())
        assert resolved.is_file(), (name, target)
        if parsed.fragment:
            assert unquote(parsed.fragment) in anchors(resolved.read_text(encoding="utf-8")), (name, target)


def test_feature_index_can_discover_all_top_level_docs_and_project_skills():
    assert INDEX.is_file()
    entries = [ROUTER, INDEX, ROOT / "docs/agents/development.md"]
    discovered = {
        (entry.parent / urlsplit(target).path).resolve()
        for entry in entries for target in links(entry)
        if not urlsplit(target).scheme and urlsplit(target).path
    }
    expected = set((ROOT / "docs").glob("*.md")) | set((ROOT / "skills").glob("*/SKILL.md"))
    assert expected <= discovered, sorted(str(p.relative_to(ROOT)) for p in expected - discovered)


def test_feature_index_code_pointers_name_real_files():
    assert INDEX.is_file()
    code_refs = re.findall(r"`([^`\n]+\.py)`", INDEX.read_text(encoding="utf-8"))
    assert code_refs
    for name in code_refs:
        target = ROOT / name if "/" in name else ROOT / "src/hermes_job_automation" / name
        assert target.is_file(), "Missing code pointer: " + name


def test_development_route_and_bounded_review_loop_have_one_source():
    dev = ROOT / "docs/agents/development.md"
    tracker = ROOT / "docs/agents/issue-tracker.md"
    assert dev.is_file() and tracker.is_file()
    assert "issue-tracker.md" in links(dev)
    assert "../PR_AUTOMATION.md#review-loop" in links(dev)
    policy = (ROOT / "docs/PR_AUTOMATION.md").read_text(encoding="utf-8")
    assert "review-loop" in anchors(policy)
    loop = section(policy, "결함 재추적과 반복 한도")
    for contract in ("자동 수정은 2회까지", "3회째", "사람 승인", "초기화하지", "연결 이슈", "head/base"):
        assert contract in loop
    for name in ("CONTRIBUTING.md", "docs/WORKFLOW_POLICY.md"):
        assert any("PR_AUTOMATION.md#review-loop" in target for target in links(ROOT / name))
    assert "Proposed" in (ROOT / "docs/adr/0004-quality-gates-and-approvals.md").read_text(encoding="utf-8")
