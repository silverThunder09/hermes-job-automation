"""Opt-in real PostgreSQL lab: metadata only, never Vault/OAuth or a remote DB.

Uses an already-running local Docker container labeled com.hermes.job.auth-lab=true
with network mode none. No downloads, port publishing, real passwords, or DB deletion.
"""
import json
import os
import runpy
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "supabase/prototypes/auth_control.sql"
CONTAINER = os.getenv("JOB_ASSIST_TEST_AUTH_CONTAINER", "")
CLIENT = "job_auth_lab_client"
OWNER = "job_auth_lab_owner"
OUTSIDER = "job_auth_lab_outsider"


def test_auth_sql_prototype_is_not_an_automatic_migration():
    assert PROTOTYPE.is_file(), "Missing explicitly local auth SQL prototype"
    assert PROTOTYPE.parent.name == "prototypes"
    assert not (ROOT / "supabase/migrations" / PROTOTYPE.name).exists()


def test_prototype_requires_local_socket_before_global_ddl():
    source = PROTOTYPE.read_text(encoding="utf-8")
    guard = "if inet_client_addr() is not null then"
    assert guard in source
    assert "AUTH_LAB_LOCAL_SOCKET_REQUIRED" in source
    assert source.index(guard) < source.index("create role job_auth_lab_owner")


def test_prototype_rejects_membership_into_owner_role_before_schema_ddl():
    source = PROTOTYPE.read_text(encoding="utf-8")
    guard = "where r.rolname = 'job_auth_lab_owner'"
    assert guard in source
    assert "AUTH_LAB_ROLE_ATTRIBUTES_REQUIRED" in source
    assert source.index(guard) < source.index("create schema if not exists job_auth_lab_private")


@pytest.mark.parametrize("endpoint", [
    "npipe:////remote-host/pipe/docker_engine",
    "unix://remote-host/docker.sock",
    "tcp://127.0.0.1:2375",
])
def test_lab_rejects_remote_environment_before_any_docker_process(monkeypatch, endpoint):
    monkeypatch.setitem(globals(), "CONTAINER", "hermes-job-auth-lab-1714a1e028fa")
    monkeypatch.setenv("DOCKER_HOST", endpoint)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("unvalidated Docker call"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("unvalidated Docker child"))
    with pytest.raises(Exception, match="nonlocal_docker"):
        lab.__wrapped__()


@pytest.mark.parametrize("endpoint", [
    "npipe:////remote-host/pipe/docker_engine", "unix://remote-host/docker.sock",
])
def test_lab_rejects_remote_context_before_inspection_or_mutation(monkeypatch, endpoint):
    api = controller()
    calls = []

    def inspect_context(self, args):
        calls.append(args)
        assert args == ["context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]
        return endpoint

    monkeypatch.setitem(globals(), "CONTAINER", "hermes-job-auth-lab-1714a1e028fa")
    monkeypatch.setitem(globals(), "controller", lambda: api)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setattr(api["DockerLabStore"], "_run", inspect_context)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("unvalidated Docker call"))
    with pytest.raises(Exception, match="nonlocal_docker"):
        lab.__wrapped__()
    assert len(calls) == 1


def test_lab_pins_validated_endpoint_id_and_clean_environment_for_all_sql(monkeypatch):
    api = controller()
    endpoint = "npipe:////./pipe/docker_engine"
    container_id = "b" * 64
    metadata = {"id": container_id, "image": "postgres:16", "label": "true",
                "network": "none", "running": True, "privileged": False,
                "ports": {}, "bindings": {}, "binds": 0,
                "mounts": [{"type": "volume", "name": "a" * 64,
                            "destination": "/var/lib/postgresql/data", "driver": "local",
                            "rw": True, "mode": "", "propagation": ""}]}
    replies = [endpoint, json.dumps(metadata),
               json.dumps({"driver": "local", "scope": "local", "options": {}})]
    monkeypatch.setitem(globals(), "CONTAINER", "hermes-job-auth-lab-1714a1e028fa")
    monkeypatch.setitem(globals(), "controller", lambda: api)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setenv("PGHOST", "remote.invalid")
    monkeypatch.setenv("PGSERVICE", "untrusted-service")
    monkeypatch.setattr(api["DockerLabStore"], "_run", lambda self, args: replies.pop(0))
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        assert args[:3] == ["docker", "--host", endpoint]
        assert container_id in args and CONTAINER not in args
        assert "/usr/bin/env" in args and "-i" in args
        assert args[args.index("-h") + 1] == "/var/run/postgresql"
        assert "-X" in args and "-w" in args
        assert not {"DOCKER_HOST", "DOCKER_CONTEXT", "PGHOST", "PGSERVICE"} & kwargs["env"].keys()
        monkeypatch.setenv("DOCKER_HOST", "npipe:////remote-host/pipe/docker_engine")
        monkeypatch.setenv("DOCKER_CONTEXT", "untrusted-context")
        return SimpleNamespace(returncode=0, stderr="", stdout=(
            "160000" if "SHOW server_version_num" in kwargs.get("input", "") else ""))

    monkeypatch.setattr(subprocess, "run", run)
    target = lab.__wrapped__()
    target.run("SELECT 1;")
    assert not replies and len(calls) >= 5
    assert target.command == ("docker", "--host", endpoint)
    assert target.cli_environment["DOCKER_HOST"] == endpoint
    assert "DOCKER_CONTEXT" not in target.cli_environment


@pytest.fixture(scope="module")
def lab():
    if not CONTAINER:
        pytest.skip("opt-in isolated auth PostgreSQL lab not specified")
    name = "job_auth_test_" + uuid.uuid4().hex
    # Share the controller's strict local endpoint, container and volume checks.
    # Construction only inspects; pin its validated target before any SQL/DDL.
    target = controller()["DockerLabStore"](CONTAINER, name)
    command = ("docker", "--host", target._host)
    environment = dict(target._environment)
    container_id = target._container_id
    psql = (*command, "exec", "-i", container_id,
            "/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "LC_ALL=C", "HOME=/nonexistent",
            "PGPASSFILE=/dev/null", "PGSERVICEFILE=/dev/null", "PGSYSCONFDIR=/nonexistent",
            "PGCONNECT_TIMEOUT=5", "/usr/lib/postgresql/16/bin/psql",
            "-X", "-w", "-h", "/var/run/postgresql", "-p", "5432")

    def run(sql, user="postgres", database=name, check=True):
        result = subprocess.run(
            [*psql, "-U", user, "-d", database,
             "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1"],
            input=sql, encoding="utf-8", capture_output=True, timeout=30, env=environment,
        )
        if check:
            assert result.returncode == 0, result.stderr
        return result

    server_version = run("SHOW server_version_num;", database="postgres").stdout.strip()
    assert server_version.isdecimal() and 160000 <= int(server_version) < 170000
    run("CREATE DATABASE " + name + ";", database="postgres")
    run("""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='job_auth_lab_outsider') THEN
            CREATE ROLE job_auth_lab_outsider LOGIN PASSWORD NULL;
        END IF;
        END $$;
        CREATE TABLE public.auth_lab_business_sentinel (id integer PRIMARY KEY, value text);
        INSERT INTO public.auth_lab_business_sentinel VALUES (1, 'preserve');
        REVOKE ALL ON public.auth_lab_business_sentinel FROM PUBLIC;
    """)
    source = PROTOTYPE.read_text(encoding="utf-8")
    run(source)
    run(source)
    cli_environment = dict(environment, DOCKER_HOST=target._host)
    return SimpleNamespace(run=run, source=source, name=name, container_id=container_id,
                           command=command, psql=psql, environment=environment,
                           cli_environment=cli_environment)


@pytest.fixture
def fresh(lab):
    lab.run("""UPDATE job_auth_lab_private.control SET state='ready', version=0,
        fixture_generation=0, epoch=1, owner=NULL WHERE singleton;
    """)
    return lab


def begin(owner, version=0, epoch=1):
    return "SELECT job_auth_lab.begin_turn('{}'::uuid, {}, {});".format(owner, version, epoch)


def stage(owner, version=0, epoch=1, generation=1):
    return "SELECT job_auth_lab.stage_generation('{}'::uuid, {}, {}, {});".format(
        owner, version, epoch, generation,
    )


def snapshot(lab):
    return json.loads(lab.run("SELECT job_auth_lab.snapshot();", user=CLIENT).stdout)


def test_lab_uses_real_non_admin_login_and_restricts_effective_privileges(fresh):
    assert fresh.run("SELECT session_user;", user=CLIENT).stdout.strip() == CLIENT
    attributes = json.loads(fresh.run("""SELECT json_build_array(
        rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls)
        FROM pg_roles WHERE rolname='job_auth_lab_client';""").stdout)
    assert attributes == [True, False, False, False, False, False]
    assert fresh.run("SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname='job_auth_lab_client');").stdout.strip() == "0"
    for query in (
        "SELECT * FROM job_auth_lab_private.control;",
        "UPDATE job_auth_lab_private.control SET state='ready';",
        "SELECT * FROM public.auth_lab_business_sentinel;",
        "SET ROLE job_auth_lab_owner;",
        "SET ROLE postgres;",
        "CREATE TABLE job_auth_lab.injected (id integer);",
    ):
        denied = fresh.run(query, user=CLIENT, check=False)
        assert denied.returncode != 0 and "permission denied" in denied.stderr
    assert fresh.run("SELECT value FROM public.auth_lab_business_sentinel WHERE id=1;").stdout.strip() == "preserve"


def test_facade_owner_search_path_and_non_public_execute(fresh):
    rows = json.loads(fresh.run("""SELECT json_agg(json_build_object(
        'definer', p.prosecdef, 'owner', r.rolname,
        'empty_path', 'search_path=""'=ANY(p.proconfig),
        'outsider', has_function_privilege('job_auth_lab_outsider',p.oid,'EXECUTE')))
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_roles r ON r.oid=p.proowner WHERE n.nspname='job_auth_lab';""").stdout)
    assert len(rows) == 4
    assert all(row == {"definer": True, "owner": OWNER, "empty_path": True, "outsider": False} for row in rows)
    denied = fresh.run("SELECT job_auth_lab.snapshot();", user=OUTSIDER, check=False)
    assert denied.returncode != 0 and "permission denied" in denied.stderr
    denied = fresh.run("SELECT job_auth_lab.snapshot();", check=False)
    assert denied.returncode != 0 and "AUTH_CALLER_REQUIRED" in denied.stderr


def test_concurrent_begin_is_single_winner_and_marker_survives_new_connections(fresh):
    owners = [str(uuid.uuid4()) for _ in range(6)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda owner: fresh.run(begin(owner), user=CLIENT, check=False), owners))
    assert sum(result.returncode == 0 for result in results) == 1
    winner = owners[next(i for i, result in enumerate(results) if result.returncode == 0)]
    assert snapshot(fresh) == {"state": "in_flight", "version": 0, "fixture_generation": 0, "epoch": 1, "owner": winner}
    assert fresh.run(begin(str(uuid.uuid4())), user=CLIENT, check=False).returncode != 0
    fresh.run(fresh.source)
    assert snapshot(fresh)["state"] == "in_flight"


def test_wrong_owner_version_and_epoch_cannot_stage(fresh):
    owner = str(uuid.uuid4())
    fresh.run(begin(owner), user=CLIENT)
    for sql in (stage(str(uuid.uuid4())), stage(owner, version=1), stage(owner, epoch=2)):
        denied = fresh.run(sql, user=CLIENT, check=False)
        assert denied.returncode != 0 and "AUTH_STATE_CONFLICT" in denied.stderr
    assert snapshot(fresh)["version"] == 0
    assert snapshot(fresh)["state"] == "in_flight"


def test_generation_staging_is_atomic_and_never_releases_ready(fresh):
    owner = str(uuid.uuid4())
    fresh.run(begin(owner), user=CLIENT)
    fresh.run(stage(owner), user=CLIENT)
    state = snapshot(fresh)
    assert (state["state"], state["version"], state["fixture_generation"]) == ("pending_validation", 1, 1)
    assert fresh.run(stage(owner), user=CLIENT, check=False).returncode != 0
    assert fresh.run(begin(str(uuid.uuid4()), version=1), user=CLIENT, check=False).returncode != 0
    assert fresh.run("SELECT job_auth_lab.finalize_turn();", user=CLIENT, check=False).returncode != 0


def test_rolled_back_stage_preserves_committed_barrier(fresh):
    owner = str(uuid.uuid4())
    fresh.run(begin(owner), user=CLIENT)
    fresh.run("BEGIN; " + stage(owner) + " ROLLBACK;", user=CLIENT)
    state = snapshot(fresh)
    assert (state["state"], state["version"], state["fixture_generation"]) == ("in_flight", 0, 0)
    assert fresh.run(begin(str(uuid.uuid4())), user=CLIENT, check=False).returncode != 0


def test_block_is_fail_closed_without_a_reset_or_ttl_path(fresh):
    owner = str(uuid.uuid4())
    fresh.run(begin(owner), user=CLIENT)
    fresh.run("SELECT job_auth_lab.block_turn('{}'::uuid,0,1);".format(owner), user=CLIENT)
    assert snapshot(fresh)["state"] == "blocked"
    assert fresh.run(begin(str(uuid.uuid4())), user=CLIENT, check=False).returncode != 0
    fresh.run(fresh.source)
    assert snapshot(fresh)["state"] == "blocked"


def test_ordinary_database_is_rejected_before_objects_are_created(lab):
    denied = lab.run(lab.source, database="postgres", check=False)
    assert denied.returncode != 0 and "AUTH_LAB_DATABASE_REQUIRED" in denied.stderr
    assert lab.run("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'job_auth_lab%';", database="postgres").stdout.strip() == "0"


def test_missing_owner_or_stale_epoch_cannot_claim(fresh):
    for sql in (
        "SELECT job_auth_lab.begin_turn(NULL,0,1);",
        begin(str(uuid.uuid4()), version=1),
        begin(str(uuid.uuid4()), epoch=2),
    ):
        assert fresh.run(sql, user=CLIENT, check=False).returncode != 0
    assert snapshot(fresh)["state"] == "ready"


def test_unexpected_transaction_error_rolls_back_staging_not_committed_barrier(fresh):
    owner = str(uuid.uuid4())
    fresh.run(begin(owner), user=CLIENT)
    result = fresh.run("BEGIN; " + stage(owner) + " SELECT 1/0; COMMIT;", user=CLIENT, check=False)
    assert result.returncode != 0
    state = snapshot(fresh)
    assert (state["state"], state["version"], state["fixture_generation"]) == ("in_flight", 0, 0)


def test_lab_stores_only_control_metadata_not_an_oauth_bundle(fresh):
    columns = json.loads(fresh.run("""SELECT json_agg(column_name ORDER BY ordinal_position)
        FROM information_schema.columns
        WHERE table_schema='job_auth_lab_private' AND table_name='control';""").stdout)
    assert set(columns) == {"singleton", "version", "fixture_generation", "epoch", "state", "owner"}
    assert fresh.run("SELECT count(*) FROM pg_namespace WHERE nspname='vault';").stdout.strip() == "0"


def test_committed_marker_survives_restart_of_the_isolated_lab(fresh):
    owner = str(uuid.uuid4())
    fresh.run(begin(owner), user=CLIENT)
    subprocess.run([*fresh.command, "restart", "-t", "1", fresh.container_id], check=True,
                   capture_output=True, timeout=30, env=fresh.environment)
    for _ in range(30):
        ready = subprocess.run([*fresh.command, "exec", fresh.container_id,
                                "/usr/bin/env", "-i", "PATH=/usr/bin:/bin",
                                "pg_isready", "-h", "/var/run/postgresql", "-U", "postgres"],
                               capture_output=True, timeout=10, env=fresh.environment)
        if ready.returncode == 0:
            break
        time.sleep(0.2)
    else:
        pytest.fail("isolated PostgreSQL lab did not restart")
    state = snapshot(fresh)
    assert state["state"] == "in_flight" and state["owner"] == owner
    assert fresh.run(begin(str(uuid.uuid4())), user=CLIENT, check=False).returncode != 0


def test_reapplication_cannot_recreate_a_lost_control_row_as_ready(fresh):
    fresh.run(begin(str(uuid.uuid4())), user=CLIENT)
    try:
        fresh.run("DELETE FROM job_auth_lab_private.control;")
        missing = fresh.run("SELECT job_auth_lab.snapshot();", user=CLIENT, check=False)
        assert missing.returncode != 0 and "AUTH_STATE_MISSING" in missing.stderr
        rejected = fresh.run(fresh.source, check=False)
        assert rejected.returncode != 0 and "AUTH_STATE_MISSING" in rejected.stderr
        assert fresh.run("SELECT count(*) FROM job_auth_lab_private.control;").stdout.strip() == "0"
        assert fresh.run(begin(str(uuid.uuid4())), user=CLIENT, check=False).returncode != 0
    finally:
        # Explicit test-admin fixture repair, never a caller or installation reset path.
        fresh.run("INSERT INTO job_auth_lab_private.control (singleton) VALUES (true) ON CONFLICT DO NOTHING;")


def test_existing_test_role_with_password_is_rejected_without_changing_it(fresh):
    query = "SELECT rolpassword IS NULL FROM pg_authid WHERE rolname='job_auth_lab_client';"
    assert fresh.run(query).stdout.strip() == "t"
    try:
        fresh.run("ALTER ROLE job_auth_lab_client PASSWORD 'synthetic-auth-lab-only';")
        rejected = fresh.run(fresh.source, check=False)
        assert rejected.returncode != 0 and "AUTH_LAB_ROLE_ATTRIBUTES_REQUIRED" in rejected.stderr
        assert fresh.run(query).stdout.strip() == "f"
    finally:
        # Restore only the synthetic role whose initial NULL state was checked above.
        fresh.run("ALTER ROLE job_auth_lab_client PASSWORD NULL;")


def test_owner_role_membership_is_rejected_and_test_membership_is_restored(fresh):
    membership = "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid " \
                 "WHERE r.rolname='job_auth_lab_owner' AND m.member=(SELECT oid FROM pg_roles " \
                 "WHERE rolname='job_auth_lab_outsider');"
    assert fresh.run(membership).stdout.strip() == "0"
    fresh.run("GRANT job_auth_lab_owner TO job_auth_lab_outsider;")
    try:
        rejected = fresh.run(fresh.source, check=False)
        assert rejected.returncode != 0 and "AUTH_LAB_ROLE_ATTRIBUTES_REQUIRED" in rejected.stderr
        assert fresh.run(membership).stdout.strip() == "1"
    finally:
        fresh.run("REVOKE job_auth_lab_owner FROM job_auth_lab_outsider;")
    assert fresh.run(membership).stdout.strip() == "0"


def test_partial_install_is_not_treated_as_a_fresh_database(lab):
    name = "job_auth_test_" + uuid.uuid4().hex
    lab.run("CREATE DATABASE " + name + ";", database="postgres")
    lab.run("CREATE SCHEMA job_auth_lab_private;", database=name)
    rejected = lab.run(lab.source, database=name, check=False)
    assert rejected.returncode != 0 and "AUTH_STATE_MISSING" in rejected.stderr
    assert lab.run("SELECT to_regclass('job_auth_lab_private.control') IS NULL;", database=name).stdout.strip() == "t"


def controller():
    return runpy.run_path(str(ROOT / "scripts/auth_control_lab.py"))


def test_controller_runs_work_only_after_real_committed_marker(fresh):
    api = controller()
    store = api["DockerLabStore"](fresh.container_id, fresh.name)
    calls = []

    def work(generation):
        marker = snapshot(fresh)
        assert marker["state"] == "in_flight"
        assert marker["fixture_generation"] == generation == 0
        calls.append(generation)
        return generation + 1

    result = api["run_once"](store, work)
    assert calls == [0]
    assert result["status"] == "verified_local_metadata"
    assert result["state"] == "pending_validation"
    assert result["scope"]["provider_called"] is False
    assert {key: result[key] for key in snapshot(fresh)} == snapshot(fresh)


def test_controller_work_failure_blocks_real_sql_without_replay(fresh):
    api = controller()
    store = api["DockerLabStore"](fresh.container_id, fresh.name)
    calls = []

    def fail(_):
        calls.append(1)
        raise RuntimeError("synthetic failure")

    with pytest.raises(api["LabError"]):
        api["run_once"](store, fail)
    assert calls == [1] and snapshot(fresh)["state"] == "blocked"
    with pytest.raises(api["LabError"]):
        api["run_once"](store, lambda _: pytest.fail("no work replay"))


def test_controller_lost_claim_ack_preserves_real_barrier_without_work(fresh):
    api = controller()

    class LostAck(api["DockerLabStore"]):
        def begin(self, owner, version, epoch):
            super().begin(owner, version, epoch)
            raise api["LabError"]("claim_uncertain")

    with pytest.raises(api["LabError"]):
        api["run_once"](LostAck(fresh.container_id, fresh.name), lambda _: pytest.fail("no work"))
    assert snapshot(fresh)["state"] == "in_flight"


def test_controller_lost_stage_ack_preserves_real_pending_result(fresh):
    api = controller()

    class LostAck(api["DockerLabStore"]):
        def stage(self, owner, version, epoch, generation):
            super().stage(owner, version, epoch, generation)
            raise api["LabError"]("stage_uncertain")

    with pytest.raises(api["LabError"]):
        api["run_once"](LostAck(fresh.container_id, fresh.name))
    state = snapshot(fresh)
    assert (state["state"], state["version"], state["fixture_generation"]) == ("pending_validation", 1, 1)
    with pytest.raises(api["LabError"]):
        api["run_once"](api["DockerLabStore"](fresh.container_id, fresh.name))
    assert snapshot(fresh) == state


def test_cli_harness_passes_original_immutable_id_before_starting_child(monkeypatch):
    class PinnedCommand(Exception):
        pass

    original_id = "b" * 64
    monkeypatch.setitem(globals(), "CONTAINER", "hermes-job-auth-lab-1714a1e028fa")
    target = SimpleNamespace(name="job_auth_test_" + "a" * 32,
                             container_id=original_id, cli_environment={})

    def inspect_command(args, **kwargs):
        assert args[args.index("--container") + 1] == original_id
        raise PinnedCommand

    monkeypatch.setattr(subprocess, "run", inspect_command)
    with pytest.raises(PinnedCommand):
        test_controller_cli_executes_real_sql_once_and_refuses_second_run(target)


def test_controller_cli_executes_real_sql_once_and_refuses_second_run(fresh):
    command = [sys.executable, str(ROOT / "scripts/auth_control_lab.py"),
               "--container", fresh.container_id, "--database", fresh.name]
    result = subprocess.run(command, text=True, encoding="utf-8", capture_output=True,
                            timeout=90, env=fresh.cli_environment)
    assert result.returncode == 0, result.stdout
    report = json.loads(result.stdout)
    assert report["status"] == "verified_local_metadata"
    assert report["state"] == snapshot(fresh)["state"] == "pending_validation"
    again = subprocess.run(command, text=True, encoding="utf-8", capture_output=True,
                           timeout=90, env=fresh.cli_environment)
    assert again.returncode == 1
    assert json.loads(again.stdout)["code"] == "not_ready"
    assert snapshot(fresh)["version"] == 1


@pytest.mark.parametrize("row_lock", [True, False], ids=["row-lock", "long-statement"])
def test_controller_server_deadlines_leave_no_background_backend(fresh, row_lock):
    api = controller()
    store = api["DockerLabStore"](fresh.container_id, fresh.name)
    store._TIMEOUT = 7  # Faster outer fallback; server deadlines must win.
    holder = None
    try:
        if row_lock:
            holder = subprocess.Popen(
                [*fresh.psql, "-U", "postgres", "-d", fresh.name, "-X", "-q", "-t", "-A",
                 "-v", "ON_ERROR_STOP=1", "-c", "SET application_name='job-auth-lock-holder'; "
                 "BEGIN; SELECT singleton FROM "
                 "job_auth_lab_private.control FOR UPDATE; SELECT pg_sleep(25); ROLLBACK;"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=dict(fresh.environment),
            )
            for _ in range(40):
                locked = fresh.run("SELECT count(*) FROM pg_stat_activity WHERE "
                                   "datname=current_database() AND "
                                   "application_name='job-auth-lock-holder' AND wait_event='PgSleep';")
                if locked.stdout.strip() == "1":
                    break
                time.sleep(0.1)
            else:
                pytest.fail("local lock holder did not reach pg_sleep")
        with pytest.raises(api["LabError"]):
            if row_lock:
                api["run_once"](store, lambda _: pytest.fail("no work after blocked claim"))
            else:
                store._sql("SELECT pg_sleep(12);")
        remaining = fresh.run("SELECT count(*) FROM pg_stat_activity WHERE "
                              "datname=current_database() AND usename='job_auth_lab_client';")
        assert remaining.stdout.strip() == "0", "query backend survived controller return"
        assert snapshot(fresh)["state"] == "ready"
    finally:
        # Only this test module's new, isolated database and synthetic roles.
        fresh.run("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE "
                  "datname=current_database() AND usename='job_auth_lab_client';")
        if holder is not None:
            fresh.run("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE "
                      "datname=current_database() AND application_name='job-auth-lock-holder';")
            holder.wait(timeout=10)
