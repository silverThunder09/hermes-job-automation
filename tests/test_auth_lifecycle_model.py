"""Executable design model only: no OAuth, credentials or remote adapters."""
from pathlib import Path
import runpy

import pytest


MODEL = Path(__file__).resolve().parents[1] / "scripts/auth_lifecycle_model.py"


def model():
    assert MODEL.is_file(), "Missing secret-free authentication lifecycle model"
    return runpy.run_path(str(MODEL))["LifecycleModel"]()


def test_roundtrip_requires_a_fresh_consumer_before_reuse():
    flow = model()
    flow.begin("run-a", trusted=True, lease=True)
    flow.client_finished("ok", refreshed=True)
    flow.write_back("ack")
    assert flow.state == "pending_validation"
    assert flow.credentials_generation == 1
    assert flow.model_calls == 1
    flow.verify_roundtrip(observed_generation=1, exact_match=True, fresh_consumer=True)
    assert flow.state == "ready"
    assert flow.release_allowed


@pytest.mark.parametrize("trusted,lease", [(False, True), (True, False), ("true", True)])
def test_rejected_start_never_reaches_model(trusted, lease):
    flow = model()
    with pytest.raises(RuntimeError):
        flow.begin("run-a", trusted=trusted, lease=lease)
    assert flow.model_calls == 0
    assert flow.credentials_generation == 0


def test_an_inflight_marker_blocks_a_second_owner_and_crash_replay():
    flow = model()
    flow.begin("run-a", trusted=True, lease=True)
    with pytest.raises(RuntimeError):
        flow.begin("run-b", trusted=True, lease=True)
    assert flow.owner == "run-a"
    assert flow.model_calls == 1
    assert not flow.release_allowed


@pytest.mark.parametrize("result,persisted", [("failed", 0), ("unknown_before", 0), ("unknown_after", 1)])
def test_failed_or_uncertain_write_never_reuses_old_seed(result, persisted):
    flow = model()
    flow.begin("run-a", trusted=True, lease=True)
    flow.client_finished("ok", refreshed=True)
    flow.write_back(result)
    assert flow.state == "blocked"
    assert flow.credentials_generation == persisted
    assert not flow.release_allowed
    with pytest.raises(RuntimeError):
        flow.begin("run-b", trusted=True, lease=True)
    assert flow.model_calls == 1


@pytest.mark.parametrize("observed,exact,fresh", [(0, True, True), (1, False, True), (1, True, False)])
def test_metadata_ack_or_stale_consumer_is_not_value_verification(observed, exact, fresh):
    flow = model()
    flow.begin("run-a", trusted=True, lease=True)
    flow.client_finished("ok", refreshed=True)
    flow.write_back("ack")
    with pytest.raises(RuntimeError):
        flow.verify_roundtrip(observed_generation=observed, exact_match=exact, fresh_consumer=fresh)
    assert flow.state == "blocked"
    assert not flow.release_allowed


@pytest.mark.parametrize("outcome,final_state", [("quota", "paused_quota"), ("job_failed", "paused_error")])
def test_non_auth_job_failure_preserves_refreshed_auth_without_retry(outcome, final_state):
    flow = model()
    flow.begin("run-a", trusted=True, lease=True)
    flow.client_finished(outcome, refreshed=True)
    flow.write_back("ack")
    flow.verify_roundtrip(observed_generation=1, exact_match=True, fresh_consumer=True)
    assert flow.credentials_generation == 1
    assert flow.state == final_state
    assert flow.model_calls == 1
    with pytest.raises(RuntimeError):
        flow.begin("run-b", trusted=True, lease=True)


@pytest.mark.parametrize("outcome", ["auth_failed", "cancelled", "unknown"])
def test_auth_failure_cancellation_and_unknown_result_require_human_recovery(outcome):
    flow = model()
    flow.begin("run-a", trusted=True, lease=True)
    flow.client_finished(outcome, refreshed=True)
    assert flow.state == "blocked"
    assert flow.credentials_generation == 0
    assert not flow.release_allowed
    with pytest.raises(RuntimeError):
        flow.write_back("ack")


def test_pending_validation_blocks_normal_consumers():
    flow = model()
    flow.begin("run-a", trusted=True, lease=True)
    flow.client_finished("ok", refreshed=True)
    flow.write_back("ack")
    with pytest.raises(RuntimeError):
        flow.begin("run-b", trusted=True, lease=True)
    assert flow.state == "pending_validation"
    assert flow.model_calls == 1


def test_illegal_transition_never_publishes_a_candidate():
    flow = model()
    with pytest.raises(RuntimeError):
        flow.write_back("ack")
    with pytest.raises(RuntimeError):
        flow.verify_roundtrip(observed_generation=0, exact_match=True, fresh_consumer=True)
    assert flow.model_calls == 0
    assert flow.state == "ready"


def test_no_refresh_still_requires_exact_roundtrip_and_allows_next_generation():
    flow = model()
    for owner in ("run-a", "run-b"):
        flow.begin(owner, trusted=True, lease=True)
        flow.client_finished("ok", refreshed=False)
        flow.write_back("ack")
        assert flow.state == "pending_validation"
        flow.verify_roundtrip(observed_generation=0, exact_match=True, fresh_consumer=True)
    assert flow.model_calls == 2
    assert flow.credentials_generation == 0
