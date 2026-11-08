"""Public runtime-check contracts; success tests execute real offline Chromium."""
import json

import pytest


EXPECTED_CHECKS = {
    "korean_dom", "javascript", "form_fill", "no_submission", "no_page_requests",
}
EXPECTED_SCOPE = {
    "synthetic_html": True,
    "offline_context": True,
    "external_requests_blocked": True,
    "live_site_verified": False,
    "model_verified": False,
    "authentication_verified": False,
    "database_verified": False,
    "schedule_verified": False,
}


def test_runtime_check_cli_uses_real_browser_without_loading_settings(monkeypatch, capsys):
    from hermes_job_automation.cli import main

    def forbidden():
        pytest.fail("runtime-check must not load Settings or .env")

    monkeypatch.setattr("hermes_job_automation.cli.Settings.load", forbidden)
    monkeypatch.setattr("hermes_job_automation.config._load_dotenv", forbidden)
    for name, value in {
        "JOB_ASSIST_STATE_BACKEND": "invalid-backend",
        "MINIMUM_SCORE": "invalid-integer",
        "SUPABASE_URL": "https://private.example.invalid",
        "SUPABASE_SECRET_KEY": "synthetic-secret-must-not-appear",
        "GOOGLE_APPLICATION_CREDENTIALS": "private-credentials-must-not-be-read.json",
        "AUTO_SUBMIT": "true",
        "FORM_AUTOFILL_ENABLED": "true",
    }.items():
        monkeypatch.setenv(name, value)

    assert main(["runtime-check"]) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert output.err == ""
    assert result["schema_version"] == 1
    assert result["status"] == "verified"
    assert result["browser"]["engine"] == "chromium"
    assert result["browser"]["version"]
    assert result["browser"]["headless"] is True
    assert set(result["checks"]) == EXPECTED_CHECKS
    assert all(value is True for value in result["checks"].values())
    assert result["page_network_requests"] == 0
    assert type(result["page_network_requests"]) is int
    assert result["submission_occurred"] is False
    assert result["scope"] == EXPECTED_SCOPE
    assert "synthetic-secret" not in output.out
    assert "private-credentials" not in output.out


@pytest.mark.parametrize("through_cli", [False, True])
def test_runtime_failure_is_sanitized_and_has_no_unobserved_success(monkeypatch, capsys, through_cli):
    from hermes_job_automation.cli import main
    from hermes_job_automation.runtime_check import run_runtime_check

    def unavailable():
        raise RuntimeError("synthetic-secret C:/private/profile.json https://private.invalid/token")

    monkeypatch.setattr("playwright.sync_api.sync_playwright", unavailable)
    monkeypatch.setattr("hermes_job_automation.cli.Settings.load", lambda: pytest.fail("no settings"))
    if through_cli:
        assert main(["runtime-check"]) == 1
        output = capsys.readouterr()
        assert output.err == ""
        result = json.loads(output.out)
    else:
        result = run_runtime_check()
    assert result["status"] == "error"
    assert result["schema_version"] == 1
    assert result["error"] == {"type": "RuntimeError", "message": "Offline browser diagnostic could not complete."}
    assert set(result["checks"]) == EXPECTED_CHECKS
    assert all(value is False for value in result["checks"].values())
    assert result["browser"]["version"] is None
    assert result["page_network_requests"] is None
    assert result["submission_occurred"] is None
    assert result["scope"]["offline_context"] is False
    assert result["scope"]["external_requests_blocked"] is False
    assert all(result["scope"][name] is False for name in EXPECTED_SCOPE if name.endswith("_verified"))
    encoded = json.dumps(result)
    assert "synthetic-secret" not in encoded
    assert "C:/private" not in encoded
    assert "https://private" not in encoded


@pytest.mark.parametrize("through_cli", [False, True])
def test_real_browser_counts_blocked_page_requests_and_refuses_success(monkeypatch, capsys, through_cli):
    from hermes_job_automation import runtime_check
    from hermes_job_automation.cli import main

    html = runtime_check._SYNTHETIC_HTML.replace(
        "</html>", '<img src="https://example.invalid/runtime-check-blocked.png"></html>',
    )
    monkeypatch.setattr(runtime_check, "_SYNTHETIC_HTML", html)
    if through_cli:
        assert main(["runtime-check"]) == 1
        result = json.loads(capsys.readouterr().out)
    else:
        result = runtime_check.run_runtime_check()
    assert result["status"] == "failed"
    assert result["page_network_requests"] == 1
    assert result["checks"]["no_page_requests"] is False
    assert all(result["checks"][name] is True for name in EXPECTED_CHECKS - {"no_page_requests"})
    assert result["scope"] == EXPECTED_SCOPE
    assert result["submission_occurred"] is False


def test_real_browser_bad_dom_is_not_reported_as_verified(monkeypatch, capsys):
    from hermes_job_automation import runtime_check
    from hermes_job_automation.cli import main

    monkeypatch.setattr(runtime_check, "_SYNTHETIC_HTML", runtime_check._SYNTHETIC_HTML.replace(
        "한국어 브라우저 확인", "합성 DOM 오류",
    ))
    assert main(["runtime-check"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed"
    assert result["checks"]["korean_dom"] is False
    assert result["page_network_requests"] == 0


@pytest.mark.parametrize("args", [["--url", "https://example.invalid"], ["--profile", "private.json"]])
def test_runtime_check_refuses_user_urls_and_profiles(args):
    from hermes_job_automation.cli import main

    with pytest.raises(SystemExit) as error:
        main(["runtime-check"] + args)
    assert error.value.code == 2


def test_health_does_not_claim_an_uninspected_schedule(capsys):
    from hermes_job_automation.cli import main

    assert main(["health"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["next_run_schedule"] is None
    assert result["schedule_status"] == "not_verified"
    assert "04:00" not in json.dumps(result)
