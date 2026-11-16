"""CLI dispatch contracts only; writer persistence is tested separately."""
import json
import sys
from types import ModuleType

import pytest

from hermes_job_automation import cli


def test_cloud_validate_does_not_load_operational_settings(monkeypatch, capsys, tmp_path):
    module = ModuleType("hermes_job_automation.cloud_collection")
    calls = []

    def validate(path):
        calls.append(path)
        return [object()]

    module.load_cloud_batch = validate
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(cli.Settings, "load", lambda: (_ for _ in ()).throw(AssertionError("settings loaded")))
    path = tmp_path / "batch.json"
    assert cli.main(["cloud-validate", "--file", str(path)]) == 0
    assert calls == [path]
    assert json.loads(capsys.readouterr().out) == {
        "status": "validated", "count": 1,
        "database_writes": 0, "collection_performed": False,
    }


def test_cloud_save_requires_explicit_write_before_settings(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli.Settings, "load", lambda: (_ for _ in ()).throw(AssertionError("settings loaded")))
    with pytest.raises(SystemExit) as error:
        cli.main(["cloud-save", "--file", str(tmp_path / "batch.json"),
                  "--receipt", str(tmp_path / "receipt.json")])
    assert error.value.code == 2
    assert "cloud-save requires --explicit-write" in capsys.readouterr().err


def test_cloud_save_reports_unverified_writer_result_as_failure(monkeypatch, capsys, tmp_path):
    module = ModuleType("hermes_job_automation.cloud_collection")
    module.load_cloud_batch = lambda path: [object()]
    module.save_cloud_batch = lambda *args, **kwargs: {"status": "unknown"}
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(cli.Settings, "load", lambda: object())
    assert cli.main(["cloud-save", "--file", str(tmp_path / "batch.json"),
                     "--receipt", str(tmp_path / "receipt.json"), "--explicit-write"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "unknown"


def test_invalid_batch_never_loads_settings_or_prints_exception_text(monkeypatch, capsys, tmp_path):
    module = ModuleType("hermes_job_automation.cloud_collection")
    marker = "private-input-marker-not-a-real-secret"

    def reject(path):
        raise ValueError(marker)

    module.load_cloud_batch = reject
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(cli.Settings, "load", lambda: (_ for _ in ()).throw(AssertionError("settings loaded")))
    assert cli.main(["cloud-save", "--file", str(tmp_path / "batch.json"),
                     "--receipt", str(tmp_path / "receipt.json"), "--explicit-write"]) == 1
    output = capsys.readouterr().out
    assert marker not in output
    assert json.loads(output)["error"] == "ValueError"


def test_existing_receipt_is_preserved_before_settings_load(monkeypatch, capsys, tmp_path):
    module = ModuleType("hermes_job_automation.cloud_collection")
    module.load_cloud_batch = lambda path: [object()]
    module.save_cloud_batch = lambda *args, **kwargs: pytest.fail("writer called")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(cli.Settings, "load", lambda: pytest.fail("settings loaded"))
    receipt = tmp_path / "receipt.json"
    receipt.write_text("preserved", encoding="utf-8")
    assert cli.main(["cloud-save", "--file", str(tmp_path / "batch.json"),
                     "--receipt", str(receipt), "--explicit-write"]) == 1
    assert receipt.read_text(encoding="utf-8") == "preserved"
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_cloud_save_passes_explicit_scope_to_writer(monkeypatch, capsys, tmp_path):
    module = ModuleType("hermes_job_automation.cloud_collection")
    module.load_cloud_batch = lambda path: [object()]
    settings = object()
    calls = []

    def save(actual_settings, path, **kwargs):
        calls.append((actual_settings, path, kwargs))
        return {"status": "verified", "count": 1}

    module.save_cloud_batch = save
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(cli.Settings, "load", lambda: settings)
    source, receipt = tmp_path / "batch.json", tmp_path / "receipt.json"
    assert cli.main(["cloud-save", "--file", str(source),
                     "--receipt", str(receipt), "--explicit-write"]) == 0
    assert calls == [(settings, source, {"explicit_write": True, "receipt_path": receipt})]
    assert json.loads(capsys.readouterr().out)["status"] == "verified"


def test_cloud_validate_uses_real_batch_validator_without_settings(monkeypatch, capsys, tmp_path):
    from datetime import datetime, timezone
    from hermes_job_automation.models import Posting

    stamp = datetime.now(timezone.utc).isoformat()
    posting = Posting(platform="점핏", platform_id="123", company="합성 CLI 계약회사",
                      title="Spring 백엔드 신입", url="https://jumpit.saramin.co.kr/position/123",
                      deadline="상시채용", location="서울", experience="신입", education="학력무관",
                      employment_type="정규직", skills=["Spring"], requirements="Spring 백엔드 개발",
                      collected_at=stamp, source_kind="agent_researched_public")
    source = tmp_path / "batch.json"
    source.write_text(json.dumps({"schema_version": 1, "source": "jumpit_public_browser",
                                 "collected_at": stamp, "postings": [posting.to_dict()]},
                                ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(cli.Settings, "load", lambda: pytest.fail("settings loaded"))
    assert cli.main(["cloud-validate", "--file", str(source)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "validated", "count": 1, "database_writes": 0,
        "collection_performed": False,
    }
