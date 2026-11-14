"""Opt-in local SQL metadata lab; never an operational authentication adapter.

Only a synthetic integer is processed. Success deliberately leaves the SQL row
pending_validation: this module cannot verify Vault, OAuth or any provider.
Each SQL invocation is a separate psql process/connection in autocommit mode.
"""

import json
import os
import re
import subprocess
import sys
import threading
import uuid
from typing import Any, Callable, Dict, Optional, Protocol


_BIGINT_MAX = (1 << 63) - 1
_SCOPE = {"local_metadata_only": True, "vault_verified": False,
          "oauth_verified": False, "provider_called": False}
_CONTAINER = re.compile(r"hermes-job-auth-lab-[0-9a-f]{12}")
_DATABASE = re.compile(r"job_auth_test_[0-9a-f]{32}")
_FIELDS = {"state", "version", "fixture_generation", "epoch", "owner"}
_ERROR_CODES = frozenset({
    "invalid_arguments", "invalid_metadata", "not_ready", "claim_uncertain",
    "barrier_failed", "work_failed", "invalid_generation", "stage_uncertain",
    "validation_failed", "invalid_target", "nonlocal_docker", "docker_failed",
    "unsafe_container", "invalid_sql_value", "invalid_response", "interrupted",
})


class LabError(Exception):
    """Only fixed, nonsecret diagnostic codes may cross the public boundary."""

    def __init__(self, code: str = "invalid_response") -> None:
        self.code = code if type(code) is str and code in _ERROR_CODES else "invalid_response"
        super().__init__(self.code)


class Store(Protocol):
    def snapshot(self) -> Dict[str, Any]: ...
    def begin(self, owner: str, version: int, epoch: int) -> int: ...
    def stage(self, owner: str, version: int, epoch: int, generation: int) -> int: ...
    def block(self, owner: str, version: int, epoch: int) -> None: ...


def _integer(value: Any, minimum: int = 0, code: str = "invalid_metadata") -> int:
    if type(value) is not int or not minimum <= value <= _BIGINT_MAX:
        raise LabError(code)
    return value


def _owner(value: Any, code: str = "invalid_metadata") -> str:
    if type(value) is not str:
        raise LabError(code)
    try:
        valid = str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        raise LabError(code)
    return value


def _snapshot(value: Any) -> Dict[str, Any]:
    if type(value) is not dict or set(value) != _FIELDS:
        raise LabError("invalid_metadata")
    result = dict(value)
    state = result["state"]
    if type(state) is not str or state not in {"ready", "in_flight", "pending_validation", "blocked"}:
        raise LabError("invalid_metadata")
    for key in ("version", "fixture_generation"):
        _integer(result[key])
    _integer(result["epoch"], 1)
    if state == "ready":
        if result["owner"] is not None:
            raise LabError("invalid_metadata")
    else:
        _owner(result["owner"])
    return result


def integer_increment(generation: int) -> int:
    """Pure fixture work: not a credential operation."""
    return _integer(_integer(generation) + 1, code="invalid_generation")


def _block_once(store: Store, owner: str, version: int, epoch: int) -> None:
    # A block failure is also terminal. Never retry, reclaim, or reset.
    try:
        store.block(owner, version, epoch)
    except BaseException:
        pass


def run_once(store: Store, work: Callable[[int], int] = integer_increment) -> Dict[str, Any]:
    """Claim, independently read back, do fixture work, stage, and read back.

    Lost acknowledgements and cancellation never authorize another mutation.
    Only a failed work step (before stage is attempted) permits one block call.
    """
    try:
        initial = _snapshot(store.snapshot())
    except BaseException:
        raise LabError("invalid_metadata") from None
    if initial["state"] != "ready":
        raise LabError("not_ready")
    version, epoch = initial["version"], initial["epoch"]
    generation = initial["fixture_generation"]
    if version == _BIGINT_MAX or generation == _BIGINT_MAX:
        raise LabError("invalid_metadata")
    owner = str(uuid.uuid4())
    try:
        claimed = store.begin(owner, version, epoch)
        if _integer(claimed) != generation:
            raise LabError("claim_uncertain")
    except BaseException:
        raise LabError("claim_uncertain") from None
    marker = dict(initial, state="in_flight", owner=owner)
    try:
        if _snapshot(store.snapshot()) != marker:
            raise LabError("barrier_failed")
    except BaseException:
        raise LabError("barrier_failed") from None
    try:
        next_generation = work(generation)
    except BaseException:
        _block_once(store, owner, version, epoch)
        raise LabError("work_failed") from None
    if type(next_generation) is not int or next_generation != generation + 1 or next_generation > _BIGINT_MAX:
        _block_once(store, owner, version, epoch)
        raise LabError("invalid_generation")
    try:
        staged = store.stage(owner, version, epoch, next_generation)
        if _integer(staged) != version + 1:
            raise LabError("stage_uncertain")
    except BaseException:
        # The stage may have committed. No block/reset/retry is safe here.
        raise LabError("stage_uncertain") from None
    expected = dict(marker, state="pending_validation", version=version + 1,
                    fixture_generation=next_generation)
    try:
        final = _snapshot(store.snapshot())
        if final != expected:
            raise LabError("validation_failed")
    except BaseException:
        raise LabError("validation_failed") from None
    return {"status": "verified_local_metadata", **final, "scope": dict(_SCOPE)}


# Inspect only these metadata fields, never Config.Env, full inspect output,
# arbitrary labels, mount source paths, or image registry authentication.
_INSPECT = (
    '{"id":{{json .Id}},"image":{{json .Config.Image}},'
    '"label":{{json (index .Config.Labels "com.hermes.job.auth-lab")}},'
    '"network":{{json .HostConfig.NetworkMode}},'
    '"running":{{json .State.Running}},"privileged":{{json .HostConfig.Privileged}},'
    '"ports":{{json .NetworkSettings.Ports}},"bindings":{{json .HostConfig.PortBindings}},'
    '"mounts":[{{range $i, $m := .Mounts}}{{if $i}},{{end}}'
    '{"type":{{json $m.Type}},"name":{{json $m.Name}},'
    '"destination":{{json $m.Destination}},"driver":{{json $m.Driver}},'
    '"rw":{{json $m.RW}},"mode":{{json $m.Mode}},'
    '"propagation":{{json $m.Propagation}}}{{end}}],'
    '"binds":{{if .HostConfig.Binds}}{{len .HostConfig.Binds}}{{else}}0{{end}}}'
)

_VOLUME_INSPECT = '{"driver":{{json .Driver}},"scope":{{json .Scope}},"options":{{json .Options}}}'


def _local_endpoint(value: Any) -> str:
    if type(value) is not str or len(value) > 512:
        raise LabError("nonlocal_docker")
    # No TCP (even localhost), SSH, remote named-pipe servers, URI authority,
    # whitespace, query/fragment, or URL-encoded transport substitutions.
    unix = re.fullmatch(r"unix:///[-A-Za-z0-9_./]+", value)
    pipe = re.fullmatch(r"npipe:////\./pipe/[A-Za-z0-9_.-]+", value)
    if not (unix or pipe) or ".." in value.split("/"):
        raise LabError("nonlocal_docker")
    return value


def _process_environment() -> Dict[str, str]:
    # Docker's local context discovery needs the OS user-home location. No
    # .env/Settings/model/auth-file loader is imported or invoked here.
    allowed = {"PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE",
               "HOMEDRIVE", "HOMEPATH"}
    return {key: os.environ[key] for key in allowed if key in os.environ}


def _json(text: str) -> Any:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate")
            result[key] = value
        return result
    try:
        return json.loads(text, object_pairs_hook=unique)
    except (ValueError, TypeError, RecursionError):
        raise LabError("invalid_response") from None


class DockerLabStore:
    """Fixed facade over an existing, scoped, isolated PostgreSQL 16 lab.

    Construction only discovers/inspects; it never creates, starts, restarts,
    mounts, downloads, installs SQL, or changes Docker/user configuration.
    """

    _TIMEOUT = 15
    _OUTPUT_LIMIT = 32768

    def __init__(self, container: str, database: str) -> None:
        if (type(container) is not str or not _CONTAINER.fullmatch(container)
                or type(database) is not str or not _DATABASE.fullmatch(database)):
            raise LabError("invalid_target")
        host = os.environ.get("DOCKER_HOST")
        # Validate an explicit transport before any child process is possible.
        if host is not None:
            host = _local_endpoint(host)
        self._environment = _process_environment()
        context = os.environ.get("DOCKER_CONTEXT")
        if host is None and context is not None:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", context):
                raise LabError("nonlocal_docker")
            self._environment["DOCKER_CONTEXT"] = context
        if host is None:
            host = _local_endpoint(self._run([
                "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"
            ]))
        # Pin the endpoint; never let later environment/context changes choose it.
        self._environment.pop("DOCKER_CONTEXT", None)
        self._host = host
        metadata = _json(self._run([
            "--host", host, "inspect", "--type", "container", "--format", _INSPECT, container
        ]))
        self._check_container(metadata)
        volume = _json(self._run([
            "--host", host, "volume", "inspect", "--format", _VOLUME_INSPECT,
            metadata["mounts"][0]["name"],
        ]))
        self._check_volume(volume)
        self._container_id = metadata["id"]
        self._database = database

    @staticmethod
    def _check_volume(volume: Any) -> None:
        if type(volume) is not dict or set(volume) != {"driver", "scope", "options"}:
            raise LabError("unsafe_container")
        options = volume["options"]
        if (volume["driver"] != "local" or volume["scope"] != "local"
                or not (options is None or (type(options) is dict and not options))):
            raise LabError("unsafe_container")

    @staticmethod
    def _check_container(metadata: Any) -> None:
        fields = {"id", "image", "label", "network", "running", "privileged",
                  "ports", "bindings", "mounts", "binds"}
        if type(metadata) is not dict or set(metadata) != fields:
            raise LabError("unsafe_container")
        if (type(metadata["id"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", metadata["id"])
                or metadata["image"] != "postgres:16" or metadata["label"] != "true"
                or metadata["network"] != "none" or metadata["running"] is not True
                or metadata["privileged"] is not False):
            raise LabError("unsafe_container")
        ports, bindings = metadata["ports"], metadata["bindings"]
        if ports is not None and (type(ports) is not dict or any(v is not None and v != [] for v in ports.values())):
            raise LabError("unsafe_container")
        if bindings is not None and (type(bindings) is not dict or bindings):
            raise LabError("unsafe_container")
        mounts, binds = metadata["mounts"], metadata["binds"]
        expected_mount_fields = {"type", "name", "destination", "driver", "rw", "mode", "propagation"}
        if type(mounts) is not list or len(mounts) != 1 or type(mounts[0]) is not dict:
            raise LabError("unsafe_container")
        mount = mounts[0]
        if (set(mount) != expected_mount_fields or mount["type"] != "volume"
                or type(mount["name"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", mount["name"])
                or mount["destination"] != "/var/lib/postgresql/data"
                or mount["driver"] != "local" or mount["rw"] is not True
                or mount["mode"] != "" or mount["propagation"] != ""
                or type(binds) is not int or binds != 0):
            raise LabError("unsafe_container")

    def _run(self, args: list) -> str:
        """Bound both pipes during execution, discard stderr, redact all failures."""
        process = None
        readers = []
        unstarted_streams = []
        failed = threading.Event()
        output = bytearray()

        def drain(stream, keep: bool) -> None:
            count = 0
            try:
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > self._OUTPUT_LIMIT:
                        failed.set()
                        process.kill()
                        break
                    if keep:
                        output.extend(chunk)
            except BaseException:
                failed.set()
                try:
                    process.kill()
                except BaseException:
                    pass
            finally:
                try:
                    stream.close()
                except BaseException:
                    failed.set()

        try:
            process = subprocess.Popen(
                ["docker", *args], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=dict(self._environment), shell=False, close_fds=True,
            )
            unstarted_streams = [process.stdout, process.stderr]
            for stream, keep in ((process.stdout, True), (process.stderr, False)):
                thread = threading.Thread(target=drain, args=(stream, keep), daemon=True)
                readers.append(thread)
                thread.start()
                unstarted_streams.remove(stream)
            code = process.wait(timeout=self._TIMEOUT)
            for thread in readers:
                thread.join(timeout=1)
            if code != 0 or failed.is_set() or any(t.is_alive() for t in readers):
                raise LabError("docker_failed")
            return output.decode("utf-8", errors="strict").strip()
        except BaseException:
            raise LabError("docker_failed") from None
        finally:
            if process is not None:
                try:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=1)
                except BaseException:
                    pass
            for thread in readers:
                try:
                    if thread.ident is not None:
                        thread.join(timeout=1)
                except BaseException:
                    pass
            for stream in unstarted_streams:
                try:
                    stream.close()
                except BaseException:
                    pass

    def _sql(self, statement: str) -> str:
        # env -i removes *container* PG*/service/options/password environment,
        # not just the host's. No rc, password/service file, host/URI, or role
        # override can bypass the fixed socket-only direct LOGIN connection.
        return self._run([
            "--host", self._host, "exec", "-i", self._container_id,
            "/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "LC_ALL=C", "HOME=/nonexistent",
            "PGPASSFILE=/dev/null", "PGSERVICEFILE=/dev/null", "PGSYSCONFDIR=/nonexistent",
            "PGCONNECT_TIMEOUT=5",
            # Server deadlines must expire before the 15s Docker CLI fallback:
            # killing docker exec alone does not cancel its PostgreSQL backend.
            "PGOPTIONS=-c statement_timeout=4000 -c lock_timeout=2000",
            "/usr/lib/postgresql/16/bin/psql",
            "-X", "-w", "-h", "/var/run/postgresql", "-p", "5432",
            "-U", "job_auth_lab_client", "-d", self._database,
            "-A", "-t", "-q", "-v", "ON_ERROR_STOP=1", "-c", statement,
        ])

    @staticmethod
    def _arguments(owner: str, version: int, epoch: int) -> str:
        owner = _owner(owner, "invalid_sql_value")
        version = _integer(version, code="invalid_sql_value")
        epoch = _integer(epoch, 1, "invalid_sql_value")
        return "'{}'::uuid,{}::bigint,{}::bigint".format(owner, version, epoch)

    @staticmethod
    def _number(text: str) -> int:
        if type(text) is not str or not re.fullmatch(r"0|[1-9][0-9]{0,18}", text):
            raise LabError("invalid_response")
        return _integer(int(text), code="invalid_response")

    def snapshot(self) -> Dict[str, Any]:
        return _snapshot(_json(self._sql("select job_auth_lab.snapshot();")))

    def begin(self, owner: str, version: int, epoch: int) -> int:
        args = self._arguments(owner, version, epoch)
        return self._number(self._sql("select job_auth_lab.begin_turn({});".format(args)))

    def stage(self, owner: str, version: int, epoch: int, generation: int) -> int:
        args = self._arguments(owner, version, epoch)
        generation = _integer(generation, code="invalid_sql_value")
        return self._number(self._sql(
            "select job_auth_lab.stage_generation({},{}::bigint);".format(args, generation)
        ))

    def block(self, owner: str, version: int, epoch: int) -> None:
        args = self._arguments(owner, version, epoch)
        if self._sql("select job_auth_lab.block_turn({});".format(args)) != "":
            raise LabError("invalid_response")


def main(argv: Optional[list] = None) -> int:
    """Only --container and --database are accepted; errors never echo input."""
    try:
        values = sys.argv[1:] if argv is None else argv
        if type(values) is not list or len(values) != 4 or any(type(v) is not str for v in values):
            raise LabError("invalid_arguments")
        options = {}
        for index in (0, 2):
            key, value = values[index:index + 2]
            if key not in {"--container", "--database"} or key in options:
                raise LabError("invalid_arguments")
            options[key] = value
        if set(options) != {"--container", "--database"}:
            raise LabError("invalid_arguments")
        report = run_once(DockerLabStore(options["--container"], options["--database"]))
        print(json.dumps(report, sort_keys=True))
        return 0
    except LabError as error:
        print(json.dumps({"status": "error", "code": error.code, "scope": dict(_SCOPE)}, sort_keys=True))
        return 2 if error.code in {"invalid_arguments", "invalid_target"} else 1
    except BaseException:
        print(json.dumps({"status": "error", "code": "interrupted", "scope": dict(_SCOPE)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
