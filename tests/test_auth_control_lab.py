"""Controller contracts only; these doubles are NOT PostgreSQL/Vault evidence."""
import copy
import json
from pathlib import Path
import runpy

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/auth_control_lab.py"


@pytest.fixture(autouse=True)
def prohibit_real_processes(monkeypatch):
    """The entire file is offline; individual process doubles may override this."""
    import subprocess
    attempts = []
    def deny(*args, **kwargs):
        attempts.append(True)
        pytest.fail("Real subprocess execution is forbidden in controller unit tests")
    monkeypatch.setattr(subprocess, "Popen", deny)
    monkeypatch.setattr(subprocess, "run", deny)
    yield
    assert not attempts, "A real process was attempted, even if its failure was redacted"


@pytest.fixture(scope="module")
def api():
    assert SCRIPT.is_file(), "Missing local SQL controller integration"
    return runpy.run_path(str(SCRIPT))


def test_local_sql_controller_exists_outside_operational_application():
    assert SCRIPT.is_file(), "Missing local SQL controller integration"


class ContractStore:
    def __init__(self):
        self.value = {"state": "ready", "version": 0, "fixture_generation": 0, "epoch": 1, "owner": None}
        self.begins = 0
        self.stages = 0
        self.blocks = 0
        self.reads = 0
        self.corrupt_barrier = False
        self.corrupt_final = False
        self.claim_lost_ack = False
        self.stage_lost_ack = False

    def snapshot(self):
        self.reads += 1
        result = dict(self.value)
        if self.corrupt_barrier and result["state"] == "in_flight":
            result["owner"] = "00000000-0000-0000-0000-000000000001"
        if self.corrupt_final and result["state"] == "pending_validation":
            result["fixture_generation"] = 0
        return result

    def begin(self, owner, version, epoch):
        self.begins += 1
        self.value.update(state="in_flight", owner=owner)
        if self.claim_lost_ack:
            raise RuntimeError("private error must not escape")
        return 0

    def stage(self, owner, version, epoch, generation):
        self.stages += 1
        self.value.update(state="pending_validation", version=version + 1, fixture_generation=generation)
        if self.stage_lost_ack:
            raise RuntimeError("private error must not escape")
        return version + 1

    def block(self, owner, version, epoch):
        self.blocks += 1
        self.value["state"] = "blocked"


def test_work_runs_only_after_committed_marker_readback_and_never_releases_ready(api):
    store = ContractStore()
    calls = []

    def work(generation):
        assert store.reads == 2
        assert store.value["state"] == "in_flight"
        calls.append(generation)
        return generation + 1

    report = api["run_once"](store, work)
    assert calls == [0]
    assert store.begins == 1 and store.stages == 1 and store.blocks == 0
    assert store.reads == 3
    assert report["status"] == "verified_local_metadata"
    assert report["state"] == "pending_validation"
    assert report["scope"] == {"local_metadata_only": True, "vault_verified": False,
                                "oauth_verified": False, "provider_called": False}


@pytest.mark.parametrize("state", ["in_flight", "pending_validation", "blocked"])
def test_nonready_state_never_starts_work_or_claims(api, state):
    store = ContractStore()
    store.value.update(state=state, owner="00000000-0000-0000-0000-000000000001")
    with pytest.raises(api["LabError"]):
        api["run_once"](store, lambda _: pytest.fail("work must not run"))
    assert store.begins == 0 and store.stages == 0


@pytest.mark.parametrize("field,value", [("version", True), ("epoch", 0), ("fixture_generation", -1),
                                        ("state", "unknown"), ("owner", "invalid")])
def test_malformed_state_fails_before_claim(api, field, value):
    store = ContractStore()
    store.value[field] = value
    with pytest.raises(api["LabError"]):
        api["run_once"](store, lambda _: pytest.fail("work must not run"))
    assert store.begins == 0


@pytest.mark.parametrize("failure", ["corrupt_barrier", "claim_lost_ack"])
def test_uncertain_claim_or_wrong_marker_never_reaches_work(api, failure):
    store = ContractStore()
    setattr(store, failure, True)
    with pytest.raises(api["LabError"]) as caught:
        api["run_once"](store, lambda _: pytest.fail("work must not run"))
    assert "private error" not in str(caught.value)
    assert store.begins == 1 and store.stages == 0
    assert store.value["state"] == "in_flight"


def test_work_failure_blocks_without_retry_and_redacts_exception(api):
    store = ContractStore()
    calls = []

    def fail(_):
        calls.append(1)
        raise RuntimeError("private diagnostic sentinel")

    with pytest.raises(api["LabError"]) as caught:
        api["run_once"](store, fail)
    assert "private diagnostic" not in str(caught.value)
    assert calls == [1] and store.blocks == 1 and store.stages == 0
    assert store.value["state"] == "blocked"


@pytest.mark.parametrize("result", [True, "synthetic-private-value", -1, 2])
def test_non_incrementing_or_non_integer_work_result_is_not_staged(api, result):
    store = ContractStore()
    with pytest.raises(api["LabError"]):
        api["run_once"](store, lambda _: result)
    assert store.blocks == 1 and store.stages == 0


@pytest.mark.parametrize("failure", ["stage_lost_ack", "corrupt_final"])
def test_uncertain_stage_or_wrong_readback_never_retries_or_resets(api, failure):
    store = ContractStore()
    setattr(store, failure, True)
    with pytest.raises(api["LabError"]) as caught:
        api["run_once"](store)
    assert "private error" not in str(caught.value)
    assert store.stages == 1 and store.blocks == 0
    assert store.value["state"] == "pending_validation"
    before = copy.deepcopy(store.value)
    with pytest.raises(api["LabError"]):
        api["run_once"](store)
    assert store.value == before and store.begins == 1


@pytest.mark.parametrize("container,database", [
    ("not-a-lab", "job_auth_test_" + "a" * 32),
    ("hermes-job-auth-lab-1714a1e028fa", "postgres"),
    ("hermes-job-auth-lab-1714a1e028fa", "https://private.invalid/?sentinel"),
])
def test_adapter_rejects_unscoped_inputs_before_process_execution(api, monkeypatch, container, database):
    monkeypatch.setattr(api["subprocess"], "run", lambda *a, **kw: pytest.fail("no process expected"))
    with pytest.raises(api["LabError"]) as caught:
        api["DockerLabStore"](container, database)
    assert "private.invalid" not in str(caught.value)


def test_remote_docker_host_is_refused_before_running_docker(api, monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "ssh://private.invalid")
    monkeypatch.setattr(api["subprocess"], "run", lambda *a, **kw: pytest.fail("no process expected"))
    with pytest.raises(api["LabError"]):
        api["DockerLabStore"]("hermes-job-auth-lab-1714a1e028fa", "job_auth_test_" + "a" * 32)


def test_cli_bad_arguments_do_not_echo_input_or_load_operator_settings(api, capsys):
    assert api["main"](["--unexpected", "private-sentinel"]) == 2
    captured = capsys.readouterr()
    assert "private-sentinel" not in captured.out + captured.err
    assert json.loads(captured.out)["status"] == "error"


# These are adapter contract doubles only: no Docker or PostgreSQL is contacted.
LAB_CONTAINER = "hermes-job-auth-lab-1714a1e028fa"
LAB_DATABASE = "job_auth_test_" + "a" * 32
LAB_ID = "b" * 64


def adapter_double(api, monkeypatch, volume_info=None, **overrides):
    metadata = {"id": LAB_ID, "image": "postgres:16", "label": "true",
                "network": "none", "running": True, "privileged": False,
                "ports": {}, "bindings": {}, "binds": 0,
                "mounts": [{"type": "volume", "name": "a" * 64,
                            "destination": "/var/lib/postgresql/data", "driver": "local",
                            "rw": True, "mode": "", "propagation": ""}]}
    metadata.update(overrides)
    local_volume = {"driver": "local", "scope": "local", "options": {}}
    if volume_info is None:
        volume_info = local_volume
    calls = []
    responses = ["npipe:////./pipe/docker_engine", json.dumps(metadata), json.dumps(volume_info)]

    def command(self, args):
        calls.append(args)
        assert responses, "unexpected process"
        return responses.pop(0)

    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setattr(api["DockerLabStore"], "_run", command)
    return api["DockerLabStore"](LAB_CONTAINER, LAB_DATABASE), calls, responses


def test_adapter_pins_local_endpoint_and_immutable_id_and_uses_fixed_socket_role(api, monkeypatch):
    store, calls, responses = adapter_double(api, monkeypatch)
    ready = ContractStore().value
    responses.extend([json.dumps(ready), "0", "1", ""])
    assert store.snapshot() == ready
    owner = "00000000-0000-0000-0000-000000000001"
    assert store.begin(owner, 0, 1) == 0
    assert store.stage(owner, 0, 1, 1) == 1
    store.block(owner, 0, 1)
    assert calls[0] == ["context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]
    assert calls[1][:2] == ["--host", "npipe:////./pipe/docker_engine"]
    assert calls[1][2:4] == ["inspect", "--type"]
    assert calls[2] == ["--host", "npipe:////./pipe/docker_engine", "volume", "inspect",
                        "--format", api["_VOLUME_INSPECT"], "a" * 64]
    for args in calls[3:]:
        assert args[:2] == ["--host", "npipe:////./pipe/docker_engine"]
    for args in calls[3:]:
        assert LAB_ID in args and LAB_CONTAINER not in args
        assert "/usr/bin/env" in args and args[args.index("/usr/bin/env") + 1] == "-i"
        assert "PGPASSFILE=/dev/null" in args
        assert "PGSERVICEFILE=/dev/null" in args
        assert "PGSYSCONFDIR=/nonexistent" in args
        assert "PGOPTIONS=-c statement_timeout=4000 -c lock_timeout=2000" in args
        assert args[args.index("-U") + 1] == "job_auth_lab_client"
        assert args[args.index("-h") + 1] == "/var/run/postgresql"
        assert args[args.index("-p") + 1] == "5432"
        assert "-X" in args and "-w" in args
        assert args[args.index("-d") + 1] == LAB_DATABASE


@pytest.mark.parametrize("overrides", [
    {"id": "not-an-id"}, {"image": "postgres:latest"}, {"label": "false"},
    {"network": "bridge"}, {"running": False}, {"privileged": True},
    {"ports": {"5432/tcp": [{"HostPort": "5432"}]}},
    {"bindings": {"5432/tcp": [{"HostPort": "5432"}]}},
    {"mounts": []}, {"mounts": [{"type": "bind", "name": "",
        "destination": "/var/run/docker.sock", "driver": "", "rw": True,
        "mode": "", "propagation": ""}]},
    {"mounts": [{"type": "volume", "name": "a" * 64,
        "destination": "/var/run/docker.sock", "driver": "local", "rw": True,
        "mode": "", "propagation": ""}]},
    {"binds": 1},
])
def test_adapter_refuses_unsafe_container_metadata(api, monkeypatch, overrides):
    with pytest.raises(api["LabError"]):
        adapter_double(api, monkeypatch, **overrides)


@pytest.mark.parametrize("volume_info", [
    {"driver": "nfs", "scope": "local", "options": {}},
    {"driver": "local", "scope": "global", "options": {}},
    {"driver": "local", "scope": "local", "options": {"type": "none", "device": "/host"}},
])
def test_adapter_rejects_nonlocal_or_custom_data_volume(api, monkeypatch, volume_info):
    with pytest.raises(api["LabError"]):
        adapter_double(api, monkeypatch, volume_info=volume_info)


@pytest.mark.parametrize("host", ["tcp://127.0.0.1:2375", "ssh://private.invalid", "https://private.invalid"])
def test_all_remote_docker_transports_refused_without_process(api, monkeypatch, host):
    monkeypatch.setenv("DOCKER_HOST", host)
    monkeypatch.setattr(api["subprocess"], "Popen", lambda *a, **k: pytest.fail("process forbidden"))
    with pytest.raises(api["LabError"]) as caught:
        api["DockerLabStore"](LAB_CONTAINER, LAB_DATABASE)
    assert "private.invalid" not in str(caught.value)


def test_remote_active_context_refused_before_inspecting_container(api, monkeypatch):
    calls = []
    monkeypatch.delenv("DOCKER_HOST", raising=False)

    def command(self, args):
        calls.append(args)
        return "ssh://private.invalid"

    monkeypatch.setattr(api["DockerLabStore"], "_run", command)
    with pytest.raises(api["LabError"]):
        api["DockerLabStore"](LAB_CONTAINER, LAB_DATABASE)
    assert len(calls) == 1


@pytest.mark.parametrize("owner,version,epoch,generation", [
    ("BAD-UUID", 0, 1, 1), ("00000000-0000-0000-0000-000000000001", True, 1, 1),
    ("00000000-0000-0000-0000-000000000001", 0, 0, 1),
    ("00000000-0000-0000-0000-000000000001", 0, 1, 2 ** 63),
])
def test_sql_facade_rejects_untyped_values_before_process(api, monkeypatch, owner, version, epoch, generation):
    store, calls, responses = adapter_double(api, monkeypatch)
    before = len(calls)
    with pytest.raises(api["LabError"]):
        store.stage(owner, version, epoch, generation)
    assert len(calls) == before


@pytest.mark.parametrize("phase", ["begin", "barrier", "work", "stage", "final"])
def test_cancellation_is_terminal_and_never_resets_or_retries(api, phase):
    store = ContractStore()
    work = api["integer_increment"]
    if phase in {"begin", "stage"}:
        original_mutation = getattr(store, phase)
        def cancel(*args):
            original_mutation(*args)
            raise KeyboardInterrupt("private-cancel-sentinel")
        setattr(store, phase, cancel)
    if phase in {"barrier", "final"}:
        original = store.snapshot
        def snapshot():
            if store.reads == (1 if phase == "barrier" else 2):
                raise KeyboardInterrupt("private-cancel-sentinel")
            return original()
        store.snapshot = snapshot
    if phase == "work":
        def work(_):
            raise KeyboardInterrupt("private-cancel-sentinel")
    with pytest.raises(api["LabError"]) as caught:
        api["run_once"](store, work)
    assert "private-cancel-sentinel" not in str(caught.value)
    assert store.blocks == (1 if phase == "work" else 0)
    assert store.value["state"] != "ready"


@pytest.mark.parametrize("field,value", [
    ("version", 1), ("epoch", 2), ("fixture_generation", 1), ("state", "blocked"),
])
def test_every_claim_marker_field_must_match_before_work(api, field, value):
    store = ContractStore()
    original = store.snapshot
    def snapshot():
        result = original()
        if store.reads == 2:
            result[field] = value
        return result
    store.snapshot = snapshot
    with pytest.raises(api["LabError"]):
        api["run_once"](store, lambda _: pytest.fail("work forbidden"))
    assert store.begins == 1 and store.stages == store.blocks == 0


@pytest.mark.parametrize("field,value", [
    ("version", 2 ** 63 - 1), ("fixture_generation", 2 ** 63 - 1),
    ("version", 2 ** 63), ("epoch", True),
    ("owner", "00000000-0000-0000-0000-000000000001"),
])
def test_invalid_or_overflowing_ready_metadata_cannot_claim(api, field, value):
    store = ContractStore()
    store.value[field] = value
    with pytest.raises(api["LabError"]):
        api["run_once"](store)
    assert store.begins == store.stages == store.blocks == 0


def test_process_environment_drops_credentials_and_transport_overrides(api, monkeypatch):
    for key in ("MODEL", "SUPABASE_KEY", "PGPASSWORD", "PGSERVICE", "PGOPTIONS",
                "DOCKER_CONFIG", "DOCKER_HOST", "DOCKER_TLS_VERIFY", "OPENAI_API_KEY"):
        monkeypatch.setenv(key, "private-environment-sentinel")
    environment = api["_process_environment"]()
    assert "private-environment-sentinel" not in environment.values()
    assert not any(k.startswith(("PG", "DOCKER", "SUPABASE", "MODEL", "OPENAI")) for k in environment)


@pytest.mark.parametrize("mode", ["success", "stdout_overflow", "stderr_overflow", "timeout", "nonzero", "spawn_failure", "thread_start_failure"])
def test_subprocess_limits_cleanup_and_redacted_diagnostics_without_real_process(api, monkeypatch, mode):
    import io
    subprocess = api["subprocess"]
    events = []
    class Process:
        def __init__(self):
            self.stdout = io.BytesIO(b"ok\n" if mode != "stdout_overflow" else b"x" * 32769)
            self.stderr = io.BytesIO(b"private-error-sentinel" if mode != "stderr_overflow" else b"x" * 32769)
            self.killed = False
        def wait(self, timeout):
            events.append(("wait", timeout))
            if mode == "timeout" and not self.killed:
                raise subprocess.TimeoutExpired("private-error-sentinel", timeout)
            return 1 if mode == "nonzero" else 0
        def poll(self):
            return 0 if self.killed or mode != "timeout" else None
        def kill(self):
            self.killed = True
            events.append(("kill", None))
    process = Process()
    def popen(args, **kwargs):
        assert args == ["docker", "synthetic-command"]
        assert kwargs["env"] == {"PATH": "synthetic-path"}
        assert kwargs["shell"] is False
        assert kwargs["stdin"] == subprocess.DEVNULL
        if mode == "spawn_failure":
            raise OSError("private-error-sentinel")
        return process
    monkeypatch.setattr(subprocess, "Popen", popen)
    if mode == "thread_start_failure":
        def fail_start(self):
            raise RuntimeError("private-error-sentinel")
        monkeypatch.setattr(api["threading"].Thread, "start", fail_start)
    store = object.__new__(api["DockerLabStore"])
    store._environment = {"PATH": "synthetic-path"}
    if mode == "success":
        assert store._run(["synthetic-command"]) == "ok"
    else:
        with pytest.raises(api["LabError"]) as caught:
            store._run(["synthetic-command"])
        assert str(caught.value) == "docker_failed"
        assert "private-error-sentinel" not in str(caught.value)
    if mode in {"timeout", "stdout_overflow", "stderr_overflow"}:
        assert process.killed
    if mode != "spawn_failure":
        assert process.stdout.closed and process.stderr.closed


@pytest.mark.parametrize("argv", [[], ["--help"], ["--container", LAB_CONTAINER, "--container", LAB_CONTAINER],
                                  ["--container", LAB_CONTAINER, "--database", "postgres"],
                                  ["--database", LAB_DATABASE, "--unexpected", "private-sentinel"]])
def test_cli_argument_failures_never_spawn_or_echo(api, monkeypatch, capsys, argv):
    monkeypatch.setattr(api["subprocess"], "Popen", lambda *a, **k: pytest.fail("process forbidden"))
    assert api["main"](argv) == 2
    output = capsys.readouterr()
    assert output.err == "" and "private-sentinel" not in output.out
    assert json.loads(output.out)["status"] == "error"
