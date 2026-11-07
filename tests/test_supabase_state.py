"""Local HTTP contract fixtures only: these tests do not contact Supabase."""
import json
from types import SimpleNamespace

import pytest

from hermes_job_automation.state import create_state_store, posting_key




def settings(tmp_path, **overrides):
    values = dict(state_backend="supabase", data_dir=tmp_path,
                  supabase_url="https://fixture.supabase.co", supabase_secret_key="sb_secret_test_only",
                  supabase_storage_bucket="job-artifacts")
    values.update(overrides)
    return SimpleNamespace(**values)


def test_postgrest_save_get_dedupe_and_json_contract(postgrest, posting, tmp_path):
    store = create_state_store(settings(tmp_path))
    item = posting()
    eligibility = {"status": "eligible", "reasons": ["공개 샘플"]}
    postgrest.replies.extend([(200, True, {}), (200, [{"payload_json": item.to_dict()}], {}),
                            (200, False, {}), (200, [{"eligibility_json": eligibility}], {})])
    assert store.save_posting(item, eligibility) is True
    assert store.get_posting(posting_key(item)) == item.to_dict()
    assert store.save_posting(posting(url=item.url + "?utm_source=search"), eligibility) is False
    assert store.get_eligibility(posting_key(item)) == eligibility
    first = postgrest.calls[0]
    assert first[1] == "/rest/v1/rpc/job_assist_save_posting"
    assert first[3]["p_payload"] == item.to_dict()
    assert first[3]["p_eligibility"] == eligibility
    assert first[2]["Apikey"] == "sb_secret_test_only"
    assert "Authorization" not in first[2]
    assert not (tmp_path / "state.sqlite3").exists()


def test_settings_backend_and_redacted_status(monkeypatch):
    from hermes_job_automation.config import Settings
    monkeypatch.setattr("hermes_job_automation.config._load_dotenv", lambda: None)
    monkeypatch.setenv("JOB_ASSIST_STATE_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://fixture.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_never_print_this_fixture")
    monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", "job-artifacts")
    configured = Settings.load()
    assert configured.state_backend == "supabase"
    assert "sb_secret_never_print_this_fixture" not in repr(configured)
    assert "sb_secret_never_print_this_fixture" not in json.dumps(configured.public_status())
    assert configured.public_status()["state_backend"] == "supabase"


def test_read_only_health_checks_schema_and_private_bucket(postgrest, tmp_path):
    store = create_state_store(settings(tmp_path), read_only=True)
    tables = ["job_assist_applications", "job_assist_evaluations", "job_assist_postings",
              "job_assist_runs", "job_assist_schema_versions"]
    postgrest.replies.extend([(200, {"schema_version": 1, "tables": tables, "rls_enabled": True}, {})]
                            + [(200, [], {})] * 5
                            + [(200, {"id": "job-artifacts", "public": False}, {})])
    assert store.health() == {"backend": "supabase", "status": "ready", "schema_version": 1,
                              "tables": tables, "bucket": "job-artifacts", "bucket_private": True}
    assert len(postgrest.calls) == 7
    assert all(call[0] == "GET" for call in postgrest.calls)


def test_read_only_health_rejects_public_bucket(postgrest, tmp_path):
    store = create_state_store(settings(tmp_path), read_only=True)
    tables = ["job_assist_applications", "job_assist_evaluations", "job_assist_postings",
              "job_assist_runs", "job_assist_schema_versions"]
    postgrest.replies.extend([(200, {"schema_version": 1, "tables": tables, "rls_enabled": True}, {})]
                            + [(200, [], {})] * 5
                            + [(200, {"id": "job-artifacts", "public": True}, {})])
    with pytest.raises(RuntimeError, match="private"):
        store.health()


def test_postgrest_evaluation_application_and_run_contract(postgrest, posting, tmp_path):
    store = create_state_store(settings(tmp_path))
    item = posting()
    key = posting_key(item)
    evaluation = {"total": 70, "rationale": ["fixture, not a live score"]}
    postgrest.replies.extend([(204, None, {}), (200, [{"evaluation_json": evaluation}], {}),
                            (204, None, {}), (200, [{"status": "submitted"}], {}),
                            (200, None, {}), (200, None, {}), (201, None, {}), (204, None, {})])
    store.save_evaluation(item, evaluation)
    assert store.get_evaluation(key) == evaluation
    store.record_application(key, "manual_review", item.collected_at)
    assert store.application_status(key) == "submitted"
    store.claim_submission(key, "fixture-attempt", item.collected_at)
    store.finish_submission(key, "unknown", item.collected_at)
    store.create_run("fixture-run", item.collected_at)
    store.finish_run("fixture-run", item.collected_at, "completed", {"public_fixture": True})
    assert postgrest.calls[0][3]["evaluation_json"] == evaluation
    assert postgrest.calls[0][2]["Prefer"] == "resolution=merge-duplicates,return=minimal"
    assert postgrest.calls[2][1] == "/rest/v1/rpc/job_assist_record_application"
    assert postgrest.calls[4][1] == "/rest/v1/rpc/job_assist_claim_submission"
    assert postgrest.calls[5][3]["p_status"] == "unknown"
    assert postgrest.calls[7][0] == "PATCH"


@pytest.mark.parametrize("backend", ["sqlite", "", "SUPABASE", "bogus"])
def test_backend_selection_fails_closed(tmp_path, backend):
    with pytest.raises(ValueError, match="JOB_ASSIST_STATE_BACKEND"):
        create_state_store(settings(tmp_path, state_backend=backend))
    assert not (tmp_path / "state.sqlite3").exists()


@pytest.mark.parametrize("overrides", [
    {"supabase_url": "http://fixture.supabase.co"},
    {"supabase_url": "https://fixture.supabase.co.evil.invalid"},
    {"supabase_url": "https://user:password@fixture.supabase.co"},
    {"supabase_url": "https://fixture.supabase.co/rest/v1"},
    {"supabase_url": "https://fixture.supabase.co:443"},
    {"supabase_secret_key": ""}, {"supabase_secret_key": "sb_publishable_fixture"},
    {"supabase_storage_bucket": ""}, {"supabase_storage_bucket": "../private"},
])
def test_remote_configuration_fails_closed(tmp_path, overrides):
    with pytest.raises(ValueError):
        create_state_store(settings(tmp_path, **overrides))
    assert not (tmp_path / "state.sqlite3").exists()


def test_no_redirect_or_secret_leak(postgrest, tmp_path):
    secret = "sb_secret_test_only"
    store = create_state_store(settings(tmp_path))
    postgrest.replies.append((302, {"message": secret}, {"Location": "https://attacker.invalid/"}))
    with pytest.raises(RuntimeError, match="redirect") as error:
        store.get_posting("test:123")
    assert secret not in str(error.value)
    assert len(postgrest.calls) == 1


@pytest.mark.parametrize("reply", [(401, {"message": "sb_secret_test_only"}, {}),
                                   (200, "sb_secret_test_only", {})])
def test_error_bodies_are_not_exposed(postgrest, tmp_path, reply):
    store = create_state_store(settings(tmp_path))
    postgrest.replies.append(reply)
    with pytest.raises(RuntimeError) as error:
        store.get_posting("test:123")
    assert "sb_secret_test_only" not in str(error.value)


def test_network_exception_is_redacted_without_chaining(postgrest, tmp_path, monkeypatch):
    from urllib.error import URLError
    store = create_state_store(settings(tmp_path))

    def fail(*args, **kwargs):
        raise URLError("network diagnostic with sb_secret_test_only")

    monkeypatch.setattr(store._opener, "open", fail)
    with pytest.raises(RuntimeError) as error:
        store.get_posting("fixture:123")
    assert "sb_secret_test_only" not in str(error.value)
    assert error.value.__suppress_context__ is True
    assert not postgrest.calls


def test_read_only_store_refuses_writes_before_http(postgrest, posting, tmp_path):
    store = create_state_store(settings(tmp_path), read_only=True)
    with pytest.raises(RuntimeError, match="read-only"):
        store.save_posting(posting(), {"status": "review"})
    assert not postgrest.calls
