"""Synthetic cases and local HTTP transcripts only; never a live Supabase result."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hermes_job_automation.state import posting_key


@pytest.fixture
def case_input(tmp_path, posting, state_settings):
    from docx import Document

    source = tmp_path / "portfolio.docx"
    document = Document()
    document.add_paragraph("합성 포트폴리오: Java 프로젝트")
    document.save(str(source))
    item = posting(deadline="상시채용")
    payload = {
        "schema_version": 1,
        "posting_key": posting_key(item),
        "posting_snapshot": item.to_dict(),
        "posting_observed_at": datetime.now(timezone.utc).isoformat(),
        "source": {"path": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                   "kind": "portfolio"},
        "profile": {"evidence": "합성 포트폴리오: Java 프로젝트"},
        "evaluation": {"technical_fit": 30, "work_fit": 25, "project_fit": 20,
                       "preferred_qualifications": 5, "total": 80,
                       "rationale": ["합성 근거 기반 에이전트 평가"], "gaps": [],
                       "eligibility": "eligible", "model": "agent-supplied-not-api"},
        "documents": {"resume": "Java 프로젝트 경험", "cover_letter": "결함을 수정했습니다."},
        "missing_information": [],
    }
    case_file = tmp_path / "case.json"
    state_settings.minimum_score = 70
    return case_file, payload, tmp_path / "review", state_settings


def save_case(case_file, payload):
    case_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def queue_posting(postgrest, payload, **overrides):
    stored = dict(payload["posting_snapshot"], **overrides)
    postgrest.replies.append((200, [{"payload_json": stored}], {}))


def assert_one_get(postgrest, key):
    from urllib.parse import parse_qs, urlsplit

    assert len(postgrest.calls) == 1
    method, url, headers, body = postgrest.calls[0]
    assert method == "GET"
    assert urlsplit(url).path == "/rest/v1/job_assist_postings"
    assert parse_qs(urlsplit(url).query)["posting_key"] == ["eq." + key]
    assert body is None
    assert not postgrest.replies


def test_review_evaluation_is_held_locally_with_only_one_get(case_input, postgrest):
    from hermes_job_automation.case_build import build_case

    case_file, payload, output, settings = case_input
    payload["evaluation"]["eligibility"] = "review"
    save_case(case_file, payload)
    queue_posting(postgrest, payload)
    result = build_case(settings, case_file, output)
    assert result["status"] == "held"
    assert "evaluation_not_eligible" in result["reasons"]
    assert result["eligibility"]["status"] == "eligible"
    assert result["evaluation"]["model"] == payload["evaluation"]["model"]
    assert result["state_read_only"] is True
    for flag in ("external_state_writes", "application_submitted", "external_uploads", "final_user_approved"):
        assert result[flag] is False
    for service in ("sheet", "telegram"):
        assert result[service] == {"status": "not_written"}
    assert result["files"] == []
    assert result["source"]["sha256_before"] == result["source"]["sha256_after"] == payload["source"]["sha256"]
    assert json.loads((output / "review.json").read_text(encoding="utf-8")) == result
    assert not (output / "documents").exists()
    assert_one_get(postgrest, payload["posting_key"])


INVALID_FIELDS = [
    ("schema_version", True), ("schema_version", 1.0), ("schema_version", "1"),
    ("schema_version", 2), ("posting_key", " "), ("posting_key", 123),
    ("posting_key", "테스트:124"), ("posting_snapshot", []), ("profile", []),
    ("evaluation", []), ("documents", []), ("source", []),
    ("missing_information", "missing"), ("missing_information", [False]),
    ("missing_information", [""]), ("posting_observed_at", None),
    ("posting_observed_at", "2026-01-01T00:00:00"),
    ("posting_observed_at", "not a timestamp"),
    ("posting_observed_at", "2999-01-01T00:00:00+00:00"),
    ("source.path", 3), ("source.path", ""), ("source.path", "missing.pdf"),
    ("source.sha256", "A" * 64), ("source.sha256", "g" * 64),
    ("source.sha256", "a" * 63), ("source.sha256", "0" * 64),
    ("source.kind", "image"), ("source.kind", True),
    ("evaluation.rationale", "reason"), ("evaluation.rationale", []),
    ("evaluation.rationale", [""]), ("evaluation.rationale", [42]),
    ("evaluation.gaps", "gap"), ("evaluation.gaps", [None]),
    ("evaluation.model", ""), ("evaluation.model", 42),
    ("evaluation.eligibility", True), ("evaluation.eligibility", "approved"),
    ("documents.resume", ""), ("documents.resume", ["text"]),
    ("documents.cover_letter", " \n"), ("documents.cover_letter", None),
    ("posting_snapshot.platform", ""), ("posting_snapshot.title", True),
    ("posting_snapshot.company", " "), ("posting_snapshot.platform_id", 123),
    ("posting_snapshot.platform_id", " 123"), ("posting_snapshot.platform_id", "123 "),
    ("posting_snapshot.platform_id", ""), ("posting_snapshot.skills", "Java"),
    ("posting_snapshot.skills", [3]), ("posting_snapshot.skills", [""]),
    ("posting_snapshot.requirements", None), ("posting_snapshot.collected_at", False),
    ("posting_snapshot.source_kind", ""),
    ("posting_snapshot.url", "http://example.invalid/jobs/123"),
    ("posting_snapshot.url", "https:///jobs/123"),
    ("posting_snapshot.url", "https://user:private@example.invalid/jobs/123"),
    ("posting_snapshot.url", "https://example.invalid:bad/jobs/123"),
    ("posting_snapshot.url", "https://example.invalid/jobs/123 \n"),
    ("documents.resume", "성과가 987654321% 증가했습니다."),
] + [("posting_snapshot." + field, 3) for field in (
    "deadline", "location", "experience", "education", "employment_type")
] + [("evaluation." + field, value) for field in (
    "technical_fit", "work_fit", "project_fit", "preferred_qualifications", "total")
     for value in (True, "30", 30.0, -1, 101)]


@pytest.mark.parametrize("field,value", INVALID_FIELDS)
def test_invalid_input_is_rejected_before_store_or_output(case_input, monkeypatch, field, value):
    from hermes_job_automation.case_build import build_case

    case_file, payload, output, settings = case_input
    parent = payload
    keys = field.split(".")
    for key in keys[:-1]:
        parent = parent[key]
    parent[keys[-1]] = value
    save_case(case_file, payload)
    monkeypatch.setattr("hermes_job_automation.case_build.create_state_store",
                        lambda *a, **k: pytest.fail("invalid input reached store factory"))
    with pytest.raises(ValueError):
        build_case(settings, case_file, output)
    assert not output.exists()


@pytest.mark.parametrize("section", [None, "source", "evaluation", "documents", "posting_snapshot"])
@pytest.mark.parametrize("change", ["missing", "unknown"])
def test_json_objects_have_explicit_schema(case_input, monkeypatch, section, change):
    from hermes_job_automation.case_build import build_case

    case_file, payload, output, settings = case_input
    parent = payload if section is None else payload[section]
    if change == "missing":
        parent.pop(next(iter(parent)))
    else:
        parent["unexpected"] = "private@example.invalid"
    save_case(case_file, payload)
    monkeypatch.setattr("hermes_job_automation.case_build.create_state_store",
                        lambda *a, **k: pytest.fail("invalid schema reached store factory"))
    with pytest.raises(ValueError) as error:
        build_case(settings, case_file, output)
    assert "private@example.invalid" not in str(error.value)
    assert not output.exists()


@pytest.mark.parametrize("text", ["[]", "null", "{", '{"schema_version":1,"schema_version":1}',
                                 '{"profile":{"value":NaN}}', '{"profile":{"value":Infinity}}'])
def test_invalid_json_is_safe_before_network(case_input, monkeypatch, text):
    from hermes_job_automation.case_build import build_case

    case_file, _, output, settings = case_input
    case_file.write_text(text, encoding="utf-8")
    monkeypatch.setattr("hermes_job_automation.case_build.create_state_store",
                        lambda *a, **k: pytest.fail("invalid JSON reached store factory"))
    with pytest.raises(ValueError):
        build_case(settings, case_file, output)
    assert not output.exists()


@pytest.mark.parametrize("kind", ["unsupported_source", "source_directory", "missing_case",
                                 "existing_directory", "existing_file", "output_contains_case",
                                 "output_is_source", "output_under_source", "output_is_case",
                                 "output_under_case"])
def test_unsafe_paths_fail_before_network_without_overwrite(case_input, monkeypatch, kind):
    from hermes_job_automation.case_build import build_case

    case_file, payload, output, settings = case_input
    source = case_file.parent / payload["source"]["path"]
    before = source.read_bytes()
    if kind == "unsupported_source":
        other = source.with_suffix(".txt")
        other.write_bytes(before)
        payload["source"]["path"] = str(other)
    elif kind == "source_directory":
        other = source.parent / "directory.pdf"
        other.mkdir()
        payload["source"]["path"] = str(other)
    elif kind == "existing_directory":
        output.mkdir()
        (output / "sentinel").write_text("keep", encoding="utf-8")
    elif kind == "existing_file":
        output.write_text("keep", encoding="utf-8")
    elif kind == "output_contains_case":
        output = case_file.parent
    elif kind == "output_is_source":
        output = source
    elif kind == "output_under_source":
        output = source / "child"
    elif kind == "output_is_case":
        output = case_file
    elif kind == "output_under_case":
        output = case_file / "child"
    save_case(case_file, payload)
    if kind == "missing_case":
        case_file = case_file.with_name("absent.json")
    monkeypatch.setattr("hermes_job_automation.case_build.create_state_store",
                        lambda *a, **k: pytest.fail("unsafe path reached store factory"))
    with pytest.raises((ValueError, FileExistsError)):
        build_case(settings, case_file, output)
    assert source.read_bytes() == before
    if kind == "existing_directory":
        assert (output / "sentinel").read_text(encoding="utf-8") == "keep"
    elif kind == "existing_file":
        assert output.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("missing", [[], ["학력 본인 확인"]])
def test_eligible_case_generates_real_documents_with_read_only_state(case_input, postgrest, missing):
    from docx import Document
    from hermes_job_automation.case_build import build_case

    case_file, payload, output, settings = case_input
    payload["missing_information"] = missing
    save_case(case_file, payload)
    queue_posting(postgrest, payload)
    result = build_case(settings, case_file, output)
    assert result["status"] == ("needs_information" if missing else "ready_for_user_review")
    assert len(result["files"]) == 4
    for name in result["files"]:
        path = Path(name)
        assert path.is_file()
        if path.suffix == ".pdf":
            assert path.read_bytes().startswith(b"%PDF-")
        else:
            text = "\n".join(p.text for p in Document(str(path)).paragraphs)
            assert "Java" in text
    assert result["final_user_approved"] is False
    assert result["external_state_writes"] is False
    assert result["source"]["sha256_after"] == payload["source"]["sha256"]
    assert json.loads((output / "review.json").read_text(encoding="utf-8")) == result
    assert_one_get(postgrest, payload["posting_key"])


@pytest.mark.parametrize("scenario,reason", [
    ("education_missing", "hard_filter_review"),
    ("closed", "hard_filter_excluded"),
    ("low_score", "below_minimum_score"),
    ("stale", "observation_stale"),
])
def test_held_cases_do_not_generate_documents(case_input, postgrest, scenario, reason):
    from hermes_job_automation.case_build import build_case

    case_file, payload, output, settings = case_input
    if scenario == "education_missing":
        payload["posting_snapshot"]["education"] = None
    elif scenario == "closed":
        payload["posting_snapshot"]["deadline"] = "마감"
    elif scenario == "low_score":
        payload["evaluation"].update(technical_fit=10, total=60)
    else:
        payload["posting_observed_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    save_case(case_file, payload)
    queue_posting(postgrest, payload)
    result = build_case(settings, case_file, output)
    assert result["status"] == "held"
    assert reason in result["reasons"]
    assert result["files"] == []
    assert not (output / "documents").exists()
    assert_one_get(postgrest, payload["posting_key"])


@pytest.mark.parametrize("field,value", [("platform", "other"), ("platform_id", "999"),
    ("company", "different company"), ("title", "different role"),
    ("url", "https://example.invalid/jobs/999")])
def test_registered_identity_mismatch_fails_without_output(case_input, postgrest, field, value):
    from hermes_job_automation.case_build import build_case

    case_file, payload, output, settings = case_input
    save_case(case_file, payload)
    queue_posting(postgrest, payload, **{field: value})
    with pytest.raises(ValueError):
        build_case(settings, case_file, output)
    assert not output.exists()
    assert_one_get(postgrest, payload["posting_key"])


def test_unregistered_posting_fails_without_output(case_input, postgrest):
    from hermes_job_automation.case_build import build_case

    case_file, payload, output, settings = case_input
    save_case(case_file, payload)
    postgrest.replies.append((200, [], {}))
    with pytest.raises(ValueError):
        build_case(settings, case_file, output)
    assert not output.exists()
    assert_one_get(postgrest, payload["posting_key"])


def test_source_change_during_render_is_not_success(case_input, postgrest, monkeypatch):
    import hermes_job_automation.case_build as module

    case_file, payload, output, settings = case_input
    save_case(case_file, payload)
    queue_posting(postgrest, payload)
    def change_source(*args):
        (case_file.parent / payload["source"]["path"]).write_bytes(b"changed synthetic source")
        return []
    monkeypatch.setattr(module, "create_application_documents", change_source)
    with pytest.raises(ValueError):
        module.build_case(settings, case_file, output)
    assert not (output / "review.json").exists()


def test_cli_build_uses_actual_pipeline_without_printing_private_content(case_input, postgrest, monkeypatch, capsys):
    from hermes_job_automation.cli import main

    case_file, payload, output, settings = case_input
    payload["documents"]["cover_letter"] = "비공개 본문 private@example.invalid"
    save_case(case_file, payload)
    queue_posting(postgrest, payload)
    monkeypatch.setattr("hermes_job_automation.cli.Settings.load", lambda: settings)
    assert main(["build-case", "--file", str(case_file), "--output-dir", str(output)]) == 0
    printed = capsys.readouterr().out
    assert "private@example.invalid" not in printed
    summary = json.loads(printed)
    assert summary["documents_generated"] == 4
    assert summary["status"] == "ready_for_user_review"
    assert "evaluation" not in summary
    assert "profile" not in summary
    assert_one_get(postgrest, payload["posting_key"])


@pytest.mark.parametrize("flag", ["--execute", "--write-state"])
def test_cli_rejects_external_write_options_before_loading_settings(monkeypatch, flag):
    from hermes_job_automation.cli import main

    monkeypatch.setattr("hermes_job_automation.cli.Settings.load", lambda: pytest.fail("loaded settings"))
    with pytest.raises(SystemExit) as error:
        main(["build-case", "--file", "case.json", "--output-dir", "new", flag])
    assert error.value.code == 2


@pytest.mark.parametrize("value", [None, False, 0, "", [], {}])
def test_false_like_eligibility_is_rejected_before_network(case_input, monkeypatch, value):
    from hermes_job_automation.case_build import build_case

    case_file, payload, output, settings = case_input
    payload["evaluation"]["eligibility"] = value
    save_case(case_file, payload)
    monkeypatch.setattr("hermes_job_automation.case_build.create_state_store",
                        lambda *a, **k: pytest.fail("invalid eligibility reached network"))
    with pytest.raises(ValueError):
        build_case(settings, case_file, output)
    assert not output.exists()


@pytest.mark.parametrize("extension,content", [
    (".pdf", b"plain text renamed as PDF"),
    (".pdf", b"%PDF-1.7\nnot a PDF container\n%%EOF\n"),
    (".docx", b"plain text renamed as DOCX"),
])
def test_matching_hash_does_not_accept_invalid_source_format(case_input, monkeypatch, extension, content):
    from hermes_job_automation.case_build import build_case

    case_file, payload, output, settings = case_input
    source = case_file.parent / ("invalid" + extension)
    source.write_bytes(content)
    payload["source"].update(path=source.name, sha256=hashlib.sha256(content).hexdigest())
    save_case(case_file, payload)
    monkeypatch.setattr("hermes_job_automation.case_build.create_state_store",
                        lambda *a, **k: pytest.fail("invalid source reached network"))
    with pytest.raises(ValueError):
        build_case(settings, case_file, output)
    assert not output.exists()


@pytest.mark.parametrize("kind,label", [("portfolio", "포트폴리오 기반 신규 초안"),
                                      ("resume", "원본 이력서 기반 검토 초안")])
def test_both_documents_include_source_kind_and_draft_status(case_input, postgrest, kind, label):
    from docx import Document
    from hermes_job_automation.case_build import build_case

    case_file, payload, output, settings = case_input
    payload["source"]["kind"] = kind
    save_case(case_file, payload)
    queue_posting(postgrest, payload)
    result = build_case(settings, case_file, output)
    for name in result["files"]:
        if name.endswith(".docx"):
            text = "\n".join(p.text for p in Document(name).paragraphs)
            assert label in text
            assert "최종 제출본 아님" in text
