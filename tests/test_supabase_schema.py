"""Opt-in real PostgreSQL tests in an already-running, network-isolated LOCAL Docker container.

JOB_ASSIST_TEST_POSTGRES_CONTAINER must name that container. No downloads or remote APIs.
Creates a unique test database; deliberately does not delete it afterward.
"""
import json
import os
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


CONTAINER = os.getenv("JOB_ASSIST_TEST_POSTGRES_CONTAINER", "")
pytestmark = pytest.mark.skipif(not CONTAINER, reason="opt-in local PostgreSQL container not specified")
MIGRATION = Path(__file__).resolve().parents[1] / "supabase/migrations/202611070001_job_assist_state.sql"


def sql_literal(value):
    return "'" + value.replace("'", "''") + "'"


@pytest.fixture(scope="module")
def database():
    context = subprocess.run(["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
                             check=True, capture_output=True, text=True).stdout.strip()
    assert context.startswith(("npipe:", "unix:")), "Refuse non-local Docker endpoint"
    mode = subprocess.run(["docker", "inspect", "--format", "{{.HostConfig.NetworkMode}}", CONTAINER],
                          check=True, capture_output=True, text=True).stdout.strip()
    assert mode == "none", "Use a network-isolated test container"
    name = "job_assist_test_" + uuid.uuid4().hex

    def run(sql, db=name, check=True):
        result = subprocess.run(["docker", "exec", "-i", CONTAINER, "psql", "-U", "postgres", "-d", db,
                                 "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1"],
                                input=sql, encoding="utf-8", capture_output=True)
        if check:
            assert result.returncode == 0, result.stderr
        return result

    run("create database " + name + ";", db="postgres")
    run("""do $$ begin
        if not exists (select 1 from pg_roles where rolname='anon') then create role anon nologin; end if;
        if not exists (select 1 from pg_roles where rolname='authenticated') then create role authenticated nologin; end if;
        if not exists (select 1 from pg_roles where rolname='service_role') then create role service_role nologin bypassrls; end if;
    end $$; grant usage on schema public to service_role, anon, authenticated;""")
    migration = MIGRATION.read_text(encoding="utf-8")
    run(migration)
    run(migration)  # Idempotency, including grants and CREATE OR REPLACE functions.
    return run


def save_sql(key, url, platform="fixture", platform_id="123", eligibility=None):
    args = [key, url, platform, platform_id, json.dumps({"company": "공개 테스트", "title": "fixture"}),
            json.dumps(eligibility or {"status": "eligible"}), "2026-11-07T00:00:00Z"]
    return "select public.job_assist_save_posting(" + ",".join(sql_literal(v) for v in args) + ");"


def test_migration_health_and_service_only_permissions(database):
    result = database("set role service_role; select public.job_assist_state_health();")
    probe = json.loads(result.stdout)
    assert probe["schema_version"] == 1
    assert probe["rls_enabled"] is True
    assert probe["tables"] == ["job_assist_applications", "job_assist_evaluations", "job_assist_postings",
                               "job_assist_runs", "job_assist_schema_versions"]
    assert database("""select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace
        where n.nspname='public' and c.relname like 'job_assist_%' and c.relkind='r'
        and (has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
          or has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
          or has_table_privilege('service_role',c.oid,'DELETE,TRUNCATE'));""").stdout.strip() == "0"
    assert database("""select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace
        where n.nspname='public' and p.proname like 'job_assist_%'
          and (p.prosecdef or has_function_privilege('anon',p.oid,'EXECUTE')
            or has_function_privilege('authenticated',p.oid,'EXECUTE')
            or not has_function_privilege('service_role',p.oid,'EXECUTE')
            or not ('search_path=""' = any(p.proconfig)));""").stdout.strip() == "0"
    denied = database("set role anon; select public.job_assist_state_health();", check=False)
    assert denied.returncode != 0
    assert "permission denied" in denied.stderr


@pytest.mark.parametrize("identity", ["key", "url", "platform"])
def test_concurrent_server_dedupe(database, identity):
    prefix = uuid.uuid4().hex

    def save(index):
        key = prefix if identity == "key" else prefix + "-" + str(index)
        url = "https://example.invalid/" + (prefix if identity == "url" else prefix + "/" + str(index))
        platform_id = prefix if identity == "platform" else prefix + "-" + str(index)
        return database("set role service_role; " + save_sql(key, url, platform_id=platform_id)).stdout.strip()

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(save, range(6)))
    assert results.count("t") == 1
    assert results.count("f") == 5


@pytest.mark.parametrize("status", ["manual_review", "ready_for_approval", "submitting", "submitted", "unknown"])
def test_refresh_and_record_preserve_all_application_fields(database, status):
    key = "preserve-" + uuid.uuid4().hex
    url = "https://example.invalid/" + key
    database(save_sql(key, url, platform_id=key))
    database("""set role service_role;
        insert into public.job_assist_applications(posting_key,status,attempt_id,confirmation_evidence,notes,updated_at)
        values (%s,%s,'fixture-attempt','public-evidence','{"review":"keep"}','2026-11-07T00:00:00Z');
        insert into public.job_assist_evaluations(posting_key,evaluation_json) values (%s,'{"total":70}');
        """ % (sql_literal(key), sql_literal(status), sql_literal(key)))
    before = database("select row_to_json(a) from public.job_assist_applications a where posting_key=" + sql_literal(key)).stdout
    assert database("set role service_role; " + save_sql(key, url, platform_id=key, eligibility={"status": "excluded"})).stdout.strip() == "f"
    database("set role service_role; select public.job_assist_record_application(" + sql_literal(key) + ",'manual_review',now());")
    after = database("select row_to_json(a) from public.job_assist_applications a where posting_key=" + sql_literal(key)).stdout
    assert json.loads(after) == json.loads(before)
    assert database("select eligibility_json->>'status' from public.job_assist_postings where posting_key=" + sql_literal(key)).stdout.strip() == "eligible"
    assert database("select evaluation_json->>'total' from public.job_assist_evaluations where posting_key=" + sql_literal(key)).stdout.strip() == "70"


def test_concurrent_claim_is_single_winner_and_cannot_be_reset(database):
    key = "claim-" + uuid.uuid4().hex
    database(save_sql(key, "https://example.invalid/" + key, platform_id=key))

    def claim(index):
        return database("set role service_role; select public.job_assist_claim_submission(" +
                        sql_literal(key) + "," + sql_literal("attempt-" + str(index)) + ",now());", check=False)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(claim, range(6)))
    assert sum(result.returncode == 0 for result in results) == 1
    assert all("already attempted" in result.stderr for result in results if result.returncode)
    database("set role service_role; select public.job_assist_finish_submission(" + sql_literal(key) + ",'unknown',now(),'');")
    database("set role service_role; select public.job_assist_record_application(" + sql_literal(key) + ",'manual_review',now());")
    assert claim(99).returncode != 0
    reset = database("set role service_role; select public.job_assist_finish_submission(" + sql_literal(key) + ",'manual_review',now(),'');", check=False)
    assert reset.returncode != 0
    assert "No active submission claim" in reset.stderr


def test_exact_posting_evaluation_run_roundtrip_and_finish_requires_claim(database):
    """Real SQL complement to the HTTP transcript: no in-memory persistence substitute."""
    key = "roundtrip-" + uuid.uuid4().hex
    run_id = "run-" + key
    payload = {"company": "공개 테스트", "title": "fixture"}
    evaluation = {"total": 70, "rationale": ["public fixture"]}
    report = {"sample_key": key, "checks": {"save_get": True}}
    assert database("set role service_role; " + save_sql(key, "https://example.invalid/" + key,
                                                       platform_id=key)).stdout.strip() == "t"
    row = json.loads(database("set role service_role; select row_to_json(p) from public.job_assist_postings p where posting_key="
                              + sql_literal(key)).stdout)
    assert row["payload_json"] == payload
    assert row["eligibility_json"] == {"status": "eligible"}
    missing = database("set role service_role; select public.job_assist_finish_submission(" + sql_literal(key)
                       + ",'unknown',now(),'');", check=False)
    assert missing.returncode != 0
    assert "No active submission claim" in missing.stderr
    database("set role service_role; insert into public.job_assist_evaluations(posting_key,evaluation_json) values ("
             + sql_literal(key) + "," + sql_literal(json.dumps(evaluation)) + ");"
             + "insert into public.job_assist_runs(run_id,started_at,status) values (" + sql_literal(run_id)
             + ",now(),'running'); update public.job_assist_runs set status='completed',finished_at=now(),report_json="
             + sql_literal(json.dumps(report)) + " where run_id=" + sql_literal(run_id) + ";")
    assert json.loads(database("set role service_role; select evaluation_json from public.job_assist_evaluations where posting_key="
                               + sql_literal(key)).stdout) == evaluation
    run = json.loads(database("set role service_role; select row_to_json(r) from public.job_assist_runs r where run_id="
                              + sql_literal(run_id)).stdout)
    assert run["run_id"] == run_id
    assert run["status"] == "completed"
    assert run["report_json"] == report
