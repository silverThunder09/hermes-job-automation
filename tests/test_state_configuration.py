"""Supabase-only selection, without operator configuration or remote calls."""
import pytest

from hermes_job_automation.config import Settings
from hermes_job_automation.state import create_state_store
from hermes_job_automation.supabase_state import SupabaseStateStore


def test_supabase_is_default_and_missing_credentials_never_create_local_storage(tmp_path):
    from dataclasses import replace
    configured = replace(Settings.load(), data_dir=tmp_path / "unused")
    assert configured.state_backend == "supabase"
    assert Settings.__dataclass_fields__["state_backend"].default == "supabase"
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        create_state_store(configured)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("backend", ["sqlite", "", "SUPABASE", "bogus"])
def test_settings_reject_removed_or_unknown_backend(monkeypatch, backend):
    monkeypatch.setenv("JOB_ASSIST_STATE_BACKEND", backend)
    with pytest.raises(ValueError, match="only supabase"):
        Settings.load()


def test_factory_defaults_to_supabase_when_backend_attribute_is_absent(tmp_path):
    from types import SimpleNamespace
    configured = SimpleNamespace(supabase_url="https://fixture.supabase.co",
                                 supabase_secret_key="sb_secret_test_only",
                                 supabase_storage_bucket="job-artifacts", data_dir=tmp_path)
    assert isinstance(create_state_store(configured), SupabaseStateStore)
    assert not list(tmp_path.iterdir())


def test_health_reports_missing_configuration_without_creating_directories(tmp_path):
    from dataclasses import replace
    from hermes_job_automation.runner import get_health
    from hermes_job_automation.state_checks import state_health
    configured = replace(Settings.load(), data_dir=tmp_path / "data", log_dir=tmp_path / "logs")
    expected = {"backend": "supabase", "status": "missing_configuration",
                "missing": ["SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_STORAGE_BUCKET"]}
    assert state_health(configured) == expected
    health = get_health(configured)
    assert health["state"] == expected
    assert "sqlite" not in health
    assert not list(tmp_path.iterdir())
