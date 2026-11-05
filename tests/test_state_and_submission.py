import pytest

from hermes_job_automation.application import authorize_submission
from hermes_job_automation.models import Evaluation
from hermes_job_automation.state import StateStore, normalize_url, posting_key


def test_tracking_parameters_do_not_create_a_second_posting():
    first = "https://example.invalid/jobs/123?utm_source=test&listno=1"
    second = "https://example.invalid/jobs/123?listno=7"

    assert normalize_url(first) == normalize_url(second)


def test_state_store_deduplicates_posting_urls(posting, temp_state_path):
    store = StateStore(temp_state_path)
    first = posting()
    duplicate = posting(url=first.url + "?utm_source=search")

    assert store.save_posting(first, {"status": "eligible"})
    assert not store.save_posting(duplicate, {"status": "eligible"})
    assert store.get_posting(posting_key(first))["company"] == first.company


def test_submission_remains_disabled_by_default(posting, submission_settings):
    evaluation = Evaluation(20, 20, 15, 5, 60, eligibility="eligible")

    with pytest.raises(RuntimeError, match="AUTO_SUBMIT_DISABLED"):
        authorize_submission(submission_settings, posting(), evaluation)


def test_submission_requires_matching_explicit_approval(
    posting, submission_settings
):
    submission_settings.auto_submit = True
    submission_settings.form_autofill_enabled = True
    evaluation = Evaluation(30, 25, 20, 8, 83, eligibility="eligible")

    with pytest.raises(RuntimeError, match="MATCHING_PLATFORM_AND_POSTING_APPROVAL_MISSING"):
        authorize_submission(submission_settings, posting(), evaluation, approvals=[])


def test_submission_attempt_cannot_be_claimed_twice(posting, temp_state_path):
    store = StateStore(temp_state_path)
    item = posting()
    key = posting_key(item)
    store.save_posting(item, {"status": "eligible"})
    store.claim_submission(key, "attempt-1", "2026-11-03T12:00:00+09:00")
    store.finish_submission(key, "unknown", "2026-11-03T12:01:00+09:00")

    with pytest.raises(RuntimeError, match="already attempted"):
        store.claim_submission(key, "attempt-2", "2026-11-03T12:02:00+09:00")
