import pytest


def test_local_playwright_form_is_filled_without_submission():
    pytest.importorskip("playwright")
    from hermes_job_automation.form_dry_run import run_local_form_dry_run

    result = run_local_form_dry_run()

    assert result["status"] == "ready_for_review"
    assert result["form_values_verified"] == "True"
    assert result["submission_occurred"] == "False"
