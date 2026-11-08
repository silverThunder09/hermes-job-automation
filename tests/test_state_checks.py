"""CLI/smoke through the actual HTTP adapter and scripted local contracts, not a fake DB."""
import json

import pytest

from hermes_job_automation.state_checks import run_state_smoke


def test_state_smoke_refuses_without_explicit_write_before_settings_load(monkeypatch, capsys):
    from hermes_job_automation.cli import main
    monkeypatch.setattr("hermes_job_automation.cli.Settings.load", lambda: pytest.fail("must not load configuration"))
    with pytest.raises(SystemExit) as error:
        main(["state-smoke"])
    assert error.value.code == 2
    assert "requires --explicit-write" in capsys.readouterr().err


def test_smoke_uses_unique_samples_and_preserves_state(postgrest, smoke_contract, state_settings):
    smoke_contract()
    first = run_state_smoke(state_settings, explicit_write=True)
    smoke_contract()
    second = run_state_smoke(state_settings, explicit_write=True)
    assert first["status"] == second["status"] == "verified"
    assert first["sample_key"] != second["sample_key"]
    assert first["run_id"] != second["run_id"]
    assert first["retained"] is True
    assert first["checks"] == {"save_get": True, "eligibility": True, "evaluation": True,
                               "dedupe": True, "application_unchanged": True, "run_readback": True}
    assert first["source_url"] == "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=55385305"
    inserts = [call[3] for call in postgrest.calls if call[1].endswith("/job_assist_save_posting")]
    assert inserts[0]["p_payload"]["url"] != inserts[3]["p_payload"]["url"]
    assert all("job_assist_smoke=" in row["p_url"] for row in inserts)
    assert not any("claim_submission" in c[1] or "finish_submission" in c[1] or c[0] == "DELETE" for c in postgrest.calls)
    assert not postgrest.replies
    assert not list(state_settings.data_dir.iterdir())


def test_state_health_cli_reports_missing_configuration_without_writes(monkeypatch, tmp_path, capsys):
    from dataclasses import replace
    from hermes_job_automation.cli import main
    from hermes_job_automation.config import Settings
    configured = replace(Settings.load(), data_dir=tmp_path / "data", log_dir=tmp_path / "logs")
    monkeypatch.setattr("hermes_job_automation.cli.Settings.load", lambda: configured)
    assert main(["state-health"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "missing_configuration"
    assert result["backend"] == "supabase"
    assert not list(tmp_path.iterdir())


def test_state_smoke_cli_uses_supabase_and_exact_readback(monkeypatch, capsys, state_settings, postgrest, smoke_contract):
    from hermes_job_automation.cli import main
    smoke_contract()
    monkeypatch.setattr("hermes_job_automation.cli.Settings.load", lambda: state_settings)
    assert main(["state-smoke", "--explicit-write"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["backend"] == "supabase"
    assert all(result["checks"].values())
    assert not postgrest.replies


def test_smoke_accepts_only_minimal_public_file_and_refuses_private_fields(tmp_path, state_settings, postgrest, smoke_contract):
    sample_file = tmp_path / "public.json"
    sample_file.write_text(json.dumps({"company": "Public fixture", "title": "Test role",
                                      "url": "https://example.invalid/public/123"}), encoding="utf-8")
    smoke_contract()
    result = run_state_smoke(state_settings, explicit_write=True, sample_file=sample_file)
    insert = next(c[3] for c in postgrest.calls if c[1].endswith("/job_assist_save_posting"))
    assert insert["p_payload"]["company"] == "Public fixture"
    assert result["source_url"] == "https://example.invalid/public/123"
    calls = len(postgrest.calls)
    sample_file.write_text(json.dumps({"company": "Public fixture", "title": "Test role",
                                      "url": "https://example.invalid/public/123", "candidate_email": "private@example.invalid"}), encoding="utf-8")
    with pytest.raises(ValueError, match="public-only"):
        run_state_smoke(state_settings, explicit_write=True, sample_file=sample_file)
    assert len(postgrest.calls) == calls


@pytest.mark.parametrize("corrupt,check", [("posting", "save/get"), ("run", "run read-back"),
                                            ("application_key", "sample application read-back"),
                                            ("run_id", "run read-back")])
def test_smoke_does_not_claim_success_for_inexact_readback(state_settings, smoke_contract, corrupt, check):
    smoke_contract(corrupt=corrupt)
    with pytest.raises(RuntimeError, match=check):
        run_state_smoke(state_settings, explicit_write=True)


def test_smoke_health_failure_precedes_all_writes(postgrest, state_settings):
    postgrest.replies.append((404, {"message": "schema absent"}, {}))
    with pytest.raises(RuntimeError, match="HTTP failure"):
        run_state_smoke(state_settings, explicit_write=True)
    assert len(postgrest.calls) == 1
    assert postgrest.calls[0][0] == "GET"
    assert not list(state_settings.data_dir.iterdir())


def test_smoke_missing_credentials_fails_before_http(postgrest, state_settings):
    state_settings.supabase_secret_key = ""
    with pytest.raises(ValueError, match="SUPABASE_SECRET_KEY"):
        run_state_smoke(state_settings, explicit_write=True)
    assert not postgrest.calls
    assert not list(state_settings.data_dir.iterdir())
