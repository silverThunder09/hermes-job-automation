"""Synthetic collector results and local HTTP transcripts; no live writes."""
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from hermes_job_automation.collectors.base import CollectionResult
from hermes_job_automation.config import Settings
from hermes_job_automation.runner import run_pipeline


@pytest.fixture
def pipeline_settings(tmp_path, state_settings, monkeypatch):
    settings = replace(
        Settings.load(), project_root=tmp_path, data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs", timezone="Asia/Seoul",
        supabase_url=state_settings.supabase_url,
        supabase_secret_key=state_settings.supabase_secret_key,
        supabase_storage_bucket=state_settings.supabase_storage_bucket,
        openai_api_key="", openai_model="", google_sheet_id="",
        google_drive_parent_id="", telegram_bot_token="", telegram_chat_id="",
        saramin_api_approved=False, saramin_access_key="",
        auto_submit=False, form_autofill_enabled=False,
    )
    settings.ensure_directories()
    (tmp_path / "profile.example.json").write_text('{"skills": []}', encoding="utf-8")
    # Isolate the runner's process-global logging setup, not its real state adapter.
    monkeypatch.setattr("hermes_job_automation.runner._setup_logging",
                        lambda settings: settings.ensure_directories())
    return settings


def use_results(monkeypatch, results):
    collectors = [SimpleNamespace(platform=r.platform, collect=lambda r=r: r) for r in results]
    monkeypatch.setattr("hermes_job_automation.runner.all_collectors", lambda settings: collectors)


def queue_run(postgrest):
    postgrest.replies.extend([(201, None, {}), (204, None, {})])


def test_blocked_sources_are_not_a_successful_empty_run(pipeline_settings, postgrest, monkeypatch):
    use_results(monkeypatch, [CollectionResult("approved-api", "approval_required"),
                              CollectionResult("manual", "manual_only")])
    queue_run(postgrest)
    report = run_pipeline(pipeline_settings, collect_only=True, notify=False)
    assert report["status"] == "blocked"
    assert report["collected"] == 0
    assert report["zero_results_confirmed"] is False
    assert [call[0] for call in postgrest.calls] == ["POST", "PATCH"]
    assert postgrest.calls[-1][3]["status"] == "blocked"
    assert postgrest.calls[-1][3]["report_json"] == report
    assert not postgrest.replies


@pytest.mark.parametrize("states,status,confirmed", [
    ([], "blocked", False),
    (["credential_missing", "manual_only"], "blocked", False),
    (["error", "manual_only"], "failed", False),
    (["unrecognized"], "failed", False),
    (["success", "manual_only"], "completed", True),
    (["success"], "completed", True),
    (["partial", "manual_only"], "completed_with_gaps", False),
    (["success", "error"], "completed_with_gaps", False),
    (["success", "partial"], "completed_with_gaps", False),
])
def test_collection_outcome_distinguishes_confirmed_empty_from_incomplete(
    pipeline_settings, postgrest, monkeypatch, states, status, confirmed
):
    use_results(monkeypatch, [CollectionResult("source-{}".format(i), value)
                              for i, value in enumerate(states)])
    queue_run(postgrest)
    report = run_pipeline(pipeline_settings, collect_only=True, notify=False)
    assert report["status"] == status
    assert report["zero_results_confirmed"] is confirmed
    assert postgrest.calls[-1][3]["status"] == status
    assert postgrest.calls[-1][3]["report_json"]["status"] == status
    assert [call[0] for call in postgrest.calls] == ["POST", "PATCH"]
    assert not postgrest.replies


def test_empty_collection_does_not_read_private_profile(pipeline_settings, postgrest, monkeypatch):
    use_results(monkeypatch, [CollectionResult("source", "approval_required")])
    queue_run(postgrest)
    monkeypatch.setattr("hermes_job_automation.runner._load_profile",
                        lambda settings: pytest.fail("private profile was read without postings"))
    report = run_pipeline(pipeline_settings, collect_only=True, notify=False)
    assert report["status"] == "blocked"


@pytest.mark.parametrize("status", ["approval_required", "error", "success", "partial"])
def test_empty_collection_preserves_pending_review_queue(pipeline_settings, postgrest, monkeypatch, status):
    use_results(monkeypatch, [CollectionResult("source", status)])
    queue_run(postgrest)
    path = pipeline_settings.data_dir / "to-review.json"
    original = b'{"pending": ["synthetic-existing-review"]}'
    path.write_bytes(original)
    run_pipeline(pipeline_settings, collect_only=True, notify=False)
    assert path.read_bytes() == original


@pytest.mark.parametrize("status", ["error", "manual_only", "unrecognized"])
def test_unsuccessful_source_cannot_supply_postings(pipeline_settings, postgrest, monkeypatch, posting, status):
    use_results(monkeypatch, [CollectionResult("source", status, postings=[posting()])])
    queue_run(postgrest)
    report = run_pipeline(pipeline_settings, collect_only=True, notify=False)
    assert report["collected"] == report["new"] == 0
    assert [call[0] for call in postgrest.calls] == ["POST", "PATCH"]
    assert not any("save_posting" in call[1] for call in postgrest.calls)


@pytest.mark.parametrize("source_status,run_status,exit_code", [
    ("approval_required", "blocked", 1), ("error", "failed", 1),
    ("success", "completed", 0), ("partial", "completed_with_gaps", 0),
])
def test_cli_returns_failure_for_blocked_or_failed_runs(
    pipeline_settings, postgrest, monkeypatch, capsys, source_status, run_status, exit_code
):
    from hermes_job_automation.cli import main

    use_results(monkeypatch, [CollectionResult("source", source_status)])
    queue_run(postgrest)
    monkeypatch.setattr("hermes_job_automation.cli.Settings.load", lambda: pipeline_settings)
    assert main(["run", "--collect-only"]) == exit_code
    assert json.loads(capsys.readouterr().out)["status"] == run_status


def test_collector_exception_does_not_log_raw_secret_text(pipeline_settings, postgrest, monkeypatch, caplog):
    def fail():
        raise RuntimeError("SYNTHETIC_SECRET_NOT_FOR_LOGS")
    monkeypatch.setattr("hermes_job_automation.runner.all_collectors",
                        lambda settings: [SimpleNamespace(platform="source", collect=fail)])
    queue_run(postgrest)
    report = run_pipeline(pipeline_settings, collect_only=True, notify=False)
    assert report["status"] == "failed"
    assert report["sources"][0]["error"] == "RuntimeError"
    assert "SYNTHETIC_SECRET_NOT_FOR_LOGS" not in caplog.text


def test_blocked_notification_does_not_say_completed(pipeline_settings, postgrest, monkeypatch):
    use_results(monkeypatch, [CollectionResult("source", "approval_required")])
    queue_run(postgrest)
    messages = []
    monkeypatch.setattr("hermes_job_automation.runner.send_telegram",
                        lambda settings, message: messages.append(message) or {"status": "synthetic"})
    report = run_pipeline(pipeline_settings, collect_only=True, notify=True, dry_run=False)
    assert report["status"] == "blocked"
    assert messages and messages[0].startswith("채용공고 수집 차단")


def test_successful_new_posting_still_creates_hermes_review_queue(
    pipeline_settings, postgrest, monkeypatch, posting
):
    item = posting()
    use_results(monkeypatch, [CollectionResult("source", "success", postings=[item])])
    postgrest.replies.extend([(201, None, {}), (200, True, {}), (204, None, {})])
    report = run_pipeline(pipeline_settings, collect_only=True, notify=False)
    assert report["collected"] == report["new"] == 1
    assert report["status"] == "completed_with_gaps"
    assert report["zero_results_confirmed"] is False
    queue = json.loads((pipeline_settings.data_dir / "to-review.json").read_text(encoding="utf-8"))
    assert len(queue["postings"]) == 1
    assert queue["postings"][0]["posting"]["url"] == item.url
    assert [call[0] for call in postgrest.calls] == ["POST", "POST", "PATCH"]
    assert not postgrest.replies


def test_valid_empty_manual_import_is_distinct_from_blocked_sources(
    pipeline_settings, postgrest, monkeypatch, tmp_path
):
    use_results(monkeypatch, [CollectionResult("source", "manual_only")])
    path = tmp_path / "reviewed-empty.json"
    path.write_text("[]", encoding="utf-8")
    queue_run(postgrest)
    report = run_pipeline(pipeline_settings, manual_files=[path], collect_only=True, notify=False)
    assert report["status"] == "completed"
    assert report["zero_results_confirmed"] is True
    assert report["sources"][-1]["platform"] == "manual-import"


def test_invalid_manual_import_is_failed_not_confirmed_empty(
    pipeline_settings, postgrest, monkeypatch, tmp_path
):
    use_results(monkeypatch, [])
    path = tmp_path / "invalid.json"
    path.write_text("{", encoding="utf-8")
    queue_run(postgrest)
    report = run_pipeline(pipeline_settings, manual_files=[path], collect_only=True, notify=False)
    assert report["status"] == "failed"
    assert report["zero_results_confirmed"] is False


@pytest.mark.parametrize("model_configured", [False, True])
def test_normal_run_with_hard_filter_review_is_incomplete(
    pipeline_settings, postgrest, monkeypatch, posting, model_configured
):
    settings = replace(pipeline_settings, openai_api_key="synthetic" if model_configured else "",
                       openai_model="synthetic" if model_configured else "")
    item = posting(education=None)
    use_results(monkeypatch, [CollectionResult("source", "success", postings=[item])])
    postgrest.replies.extend([(201, None, {}), (200, True, {}), (204, None, {})])
    monkeypatch.setattr("hermes_job_automation.runner.OpenAIScorer.evaluate",
                        lambda *args: pytest.fail("hard-filter review reached model API"))
    report = run_pipeline(settings, collect_only=False, notify=False)
    assert report["review"] == 1
    assert report["evaluated"] == 0
    assert report["status"] == "completed_with_gaps"
    assert postgrest.calls[-1][3]["status"] == "completed_with_gaps"
    assert not postgrest.replies


def test_normal_run_with_model_review_is_incomplete(
    pipeline_settings, postgrest, monkeypatch, posting
):
    from hermes_job_automation.models import Evaluation

    settings = replace(pipeline_settings, openai_api_key="synthetic", openai_model="synthetic")
    use_results(monkeypatch, [CollectionResult("source", "success", postings=[posting()])])
    postgrest.replies.extend([(201, None, {}), (200, True, {}),
                              (201, None, {}), (204, None, {})])
    evaluation = Evaluation(30, 25, 20, 5, 80, eligibility="review", model="synthetic")
    monkeypatch.setattr("hermes_job_automation.runner.OpenAIScorer.evaluate",
                        lambda *args: evaluation)
    monkeypatch.setattr("hermes_job_automation.runner.OpenAIWriter.draft",
                        lambda *args: pytest.fail("review evaluation produced final documents"))
    report = run_pipeline(settings, collect_only=False, notify=False)
    assert report["evaluated"] == 1
    assert report["status"] == "completed_with_gaps"
    assert postgrest.calls[-1][3]["status"] == "completed_with_gaps"
    assert not postgrest.replies


def test_normal_run_with_only_excluded_postings_can_complete(
    pipeline_settings, postgrest, monkeypatch, posting
):
    use_results(monkeypatch, [CollectionResult("source", "success", postings=[posting(education="대졸↑")])])
    postgrest.replies.extend([(201, None, {}), (200, True, {}), (204, None, {})])
    report = run_pipeline(pipeline_settings, collect_only=False, notify=False)
    assert report["excluded"] == 1
    assert report["status"] == "completed"
