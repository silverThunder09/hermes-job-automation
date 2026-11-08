"""Submission policy plus actual adapter contracts; persistence invariants also run in PostgreSQL."""
import pytest

from hermes_job_automation.application import authorize_submission
from hermes_job_automation.models import Evaluation
from hermes_job_automation.state import create_state_store, normalize_url, posting_key


def test_tracking_parameters_do_not_create_a_second_posting():
    first = "https://example.invalid/jobs/123?utm_source=test&listno=1"
    second = "https://example.invalid/jobs/123?listno=7"
    assert normalize_url(first) == normalize_url(second)


def test_state_store_deduplicates_posting_urls(posting, postgrest, state_settings):
    store = create_state_store(state_settings)
    first = posting()
    duplicate = posting(url=first.url + "?utm_source=search")
    postgrest.replies.extend([(200, True, {}), (200, False, {}),
                            (200, [{"payload_json": first.to_dict()}], {})])
    assert store.save_posting(first, {"status": "eligible"})
    assert not store.save_posting(duplicate, {"status": "eligible"})
    assert store.get_posting(posting_key(first)) == first.to_dict()
    assert postgrest.calls[0][3]["p_url"] == postgrest.calls[1][3]["p_url"]
    assert not list(state_settings.data_dir.iterdir())


@pytest.mark.parametrize("status", ["manual_review", "ready_for_approval", "submitting", "submitted", "unknown"])
def test_collection_and_recording_preserve_existing_application(posting, postgrest, state_settings, status):
    store = create_state_store(state_settings)
    item = posting()
    key = posting_key(item)
    before = {"posting_key": key, "status": status, "attempt_id": "attempt-1",
              "submitted_at": None, "confirmation_evidence": "public-test-only",
              "notes": {"review": "preserve"}, "updated_at": item.collected_at}
    postgrest.replies.extend([(200, [before], {}), (200, False, {}), (200, None, {}),
                            (200, [before], {})])
    assert store.get_application(key) == before
    assert not store.save_posting(item, {"status": "excluded"})
    store.record_application(key, "manual_review", item.collected_at)
    assert store.get_application(key) == before
    assert postgrest.calls[2][1] == "/rest/v1/rpc/job_assist_record_application"
    assert postgrest.calls[2][3] == {"p_key": key, "p_status": "manual_review", "p_now": item.collected_at}


def test_submission_remains_disabled_by_default(posting, submission_settings):
    evaluation = Evaluation(20, 20, 15, 5, 60, eligibility="eligible")
    with pytest.raises(RuntimeError, match="AUTO_SUBMIT_DISABLED"):
        authorize_submission(submission_settings, posting(), evaluation)


def test_submission_requires_matching_explicit_approval(posting, submission_settings):
    submission_settings.auto_submit = True
    submission_settings.form_autofill_enabled = True
    evaluation = Evaluation(30, 25, 20, 8, 83, eligibility="eligible")
    with pytest.raises(RuntimeError, match="MATCHING_PLATFORM_AND_POSTING_APPROVAL_MISSING"):
        authorize_submission(submission_settings, posting(), evaluation, approvals=[])


def test_finished_submission_cannot_be_reclassified_without_a_claim(posting, postgrest, state_settings):
    store = create_state_store(state_settings)
    item = posting()
    key = posting_key(item)
    before = {"posting_key": key, "status": "submitted", "confirmation_evidence": "public fixture"}
    postgrest.replies.extend([(409, {"message": "No active submission claim"}, {}),
                            (200, [before], {}), (409, {"message": "No active submission claim"}, {}),
                            (200, [before], {})])
    with pytest.raises(RuntimeError, match=r"HTTP failure \(409\)"):
        store.finish_submission(key, "unknown", item.collected_at)
    assert store.get_application(key) == before
    with pytest.raises(RuntimeError, match=r"HTTP failure \(409\)"):
        store.finish_submission(key, "manual_review", item.collected_at)
    assert store.get_application(key) == before
    assert postgrest.calls[0][1] == postgrest.calls[2][1] == "/rest/v1/rpc/job_assist_finish_submission"


def test_submission_attempt_cannot_be_claimed_twice(posting, postgrest, state_settings):
    store = create_state_store(state_settings)
    item = posting()
    key = posting_key(item)
    postgrest.replies.extend([(200, None, {}), (200, None, {}),
                            (409, {"message": "Submission already attempted"}, {})])
    store.claim_submission(key, "attempt-1", item.collected_at)
    store.finish_submission(key, "unknown", item.collected_at)
    with pytest.raises(RuntimeError, match=r"HTTP failure \(409\)"):
        store.claim_submission(key, "attempt-2", item.collected_at)
    assert postgrest.calls[2][3]["p_attempt_id"] == "attempt-2"


@pytest.mark.parametrize("status", ["submitted", "submitting", "unknown", "bogus"])
def test_non_submission_status_guard_precedes_http(postgrest, state_settings, status):
    store = create_state_store(state_settings)
    with pytest.raises(ValueError, match="non-submission"):
        store.record_application("fixture:123", status, "2026-11-07T00:00:00Z")
    assert not postgrest.calls
