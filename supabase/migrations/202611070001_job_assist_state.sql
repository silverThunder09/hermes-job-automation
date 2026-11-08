-- Additive/idempotent v1. Deploy as the database owner in Supabase SQL Editor.
-- No bucket creation, candidate data, destructive DROP, or generic execute-SQL RPC.
begin;

create table if not exists public.job_assist_schema_versions (
    version integer primary key,
    installed_at timestamptz not null default now()
);
create table if not exists public.job_assist_postings (
    posting_key text primary key,
    normalized_url text not null unique,
    platform text not null check (platform = lower(platform)),
    platform_id text,
    company text not null,
    title text not null,
    payload_json jsonb not null,
    eligibility_json jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null,
    last_seen_at timestamptz not null
);
create unique index if not exists job_assist_posting_platform_id
    on public.job_assist_postings(platform, platform_id) where platform_id is not null;
create table if not exists public.job_assist_evaluations (
    posting_key text primary key references public.job_assist_postings(posting_key),
    evaluation_json jsonb not null,
    updated_at timestamptz not null default now()
);
create table if not exists public.job_assist_applications (
    posting_key text primary key references public.job_assist_postings(posting_key),
    status text not null check (status in (
        'collected', 'manual_review', 'ready_for_approval', 'submitting',
        'submitted', 'unknown', 'failed_before_submit')),
    attempt_id text,
    submitted_at timestamptz,
    confirmation_evidence text,
    notes jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null
);
create table if not exists public.job_assist_runs (
    run_id text primary key,
    started_at timestamptz not null,
    finished_at timestamptz,
    status text not null,
    report_json jsonb not null default '{}'::jsonb
);

alter table public.job_assist_schema_versions enable row level security;
alter table public.job_assist_postings enable row level security;
alter table public.job_assist_evaluations enable row level security;
alter table public.job_assist_applications enable row level security;
alter table public.job_assist_runs enable row level security;

-- Concurrent INSERT ... ON CONFLICT waits on unique constraints; the following
-- statement sees the committed winner under READ COMMITTED. No client read/write race.
create or replace function public.job_assist_save_posting(
    p_key text, p_url text, p_platform text, p_platform_id text,
    p_payload jsonb, p_eligibility jsonb, p_now timestamptz
) returns boolean language plpgsql security invoker set search_path = '' as $$
declare
    inserted_count integer;
    match_count integer;
begin
    insert into public.job_assist_postings (
        posting_key, normalized_url, platform, platform_id, company, title,
        payload_json, eligibility_json, first_seen_at, last_seen_at
    ) values (
        p_key, p_url, p_platform, p_platform_id, p_payload->>'company', p_payload->>'title',
        p_payload, p_eligibility, p_now, p_now
    ) on conflict do nothing;
    get diagnostics inserted_count = row_count;
    if inserted_count = 1 then return true; end if;
    select count(*) into match_count from public.job_assist_postings
    where posting_key = p_key or normalized_url = p_url
       or (platform = p_platform and platform_id = p_platform_id);
    if match_count <> 1 then
        raise exception 'Conflicting posting identities; manual reconciliation required';
    end if;
    update public.job_assist_postings set last_seen_at = greatest(last_seen_at, p_now)
    where posting_key = p_key or normalized_url = p_url
       or (platform = p_platform and platform_id = p_platform_id);
    -- Original payload, eligibility, evaluations, application status and notes survive.
    return false;
end;
$$;

create or replace function public.job_assist_record_application(
    p_key text, p_status text, p_now timestamptz
) returns void language plpgsql security invoker set search_path = '' as $$
begin
    if p_status not in ('manual_review', 'ready_for_approval') then
        raise exception 'Unsupported non-submission application status';
    end if;
    insert into public.job_assist_applications(posting_key, status, updated_at)
    values (p_key, p_status, p_now) on conflict (posting_key) do nothing;
end;
$$;

create or replace function public.job_assist_claim_submission(
    p_key text, p_attempt_id text, p_now timestamptz
) returns void language plpgsql security invoker set search_path = '' as $$
declare changed integer;
begin
    insert into public.job_assist_applications(posting_key, status, attempt_id, updated_at)
    values (p_key, 'submitting', p_attempt_id, p_now)
    on conflict (posting_key) do update
    set status = 'submitting', attempt_id = excluded.attempt_id, updated_at = excluded.updated_at
    where public.job_assist_applications.status not in ('submitting', 'submitted', 'unknown');
    get diagnostics changed = row_count;
    if changed <> 1 then
        raise exception 'Submission already attempted; manual reconciliation is required';
    end if;
end;
$$;

create or replace function public.job_assist_finish_submission(
    p_key text, p_status text, p_now timestamptz, p_evidence text
) returns void language plpgsql security invoker set search_path = '' as $$
declare changed integer;
begin
    if p_status not in ('submitted', 'unknown', 'failed_before_submit', 'manual_review') then
        raise exception 'Unsupported submission status';
    end if;
    update public.job_assist_applications
    set status = p_status, submitted_at = case when p_status = 'submitted' then p_now else null end,
        confirmation_evidence = p_evidence, updated_at = p_now
    where posting_key = p_key and status = 'submitting';
    get diagnostics changed = row_count;
    if changed <> 1 then raise exception 'No active submission claim'; end if;
end;
$$;

-- Fixed, read-only schema probe. SECURITY INVOKER; no SQL text accepted from clients.
create or replace function public.job_assist_state_health()
returns jsonb language sql stable security invoker set search_path = '' as $$
    select jsonb_build_object(
        'schema_version', (select max(version) from public.job_assist_schema_versions),
        'tables', (select jsonb_agg(c.relname order by c.relname)
            from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind = 'r' and c.relname in (
                'job_assist_schema_versions', 'job_assist_postings', 'job_assist_evaluations',
                'job_assist_applications', 'job_assist_runs')),
        'rls_enabled', (select bool_and(c.relrowsecurity)
            from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind = 'r' and c.relname in (
                'job_assist_schema_versions', 'job_assist_postings', 'job_assist_evaluations',
                'job_assist_applications', 'job_assist_runs'))
    );
$$;

revoke all on table public.job_assist_schema_versions, public.job_assist_postings,
    public.job_assist_evaluations, public.job_assist_applications, public.job_assist_runs
    from public, anon, authenticated;
-- Restrict inherited/default service grants too: no delete/truncate privileges.
revoke all on table public.job_assist_schema_versions, public.job_assist_postings,
    public.job_assist_evaluations, public.job_assist_applications, public.job_assist_runs
    from service_role;
grant select on public.job_assist_schema_versions to service_role;
grant select, insert, update on public.job_assist_postings, public.job_assist_evaluations,
    public.job_assist_applications, public.job_assist_runs to service_role;

revoke all on function public.job_assist_save_posting(text,text,text,text,jsonb,jsonb,timestamptz),
    public.job_assist_record_application(text,text,timestamptz),
    public.job_assist_claim_submission(text,text,timestamptz),
    public.job_assist_finish_submission(text,text,timestamptz,text),
    public.job_assist_state_health() from public, anon, authenticated;
grant execute on function public.job_assist_save_posting(text,text,text,text,jsonb,jsonb,timestamptz),
    public.job_assist_record_application(text,text,timestamptz),
    public.job_assist_claim_submission(text,text,timestamptz),
    public.job_assist_finish_submission(text,text,timestamptz,text),
    public.job_assist_state_health() to service_role;

insert into public.job_assist_schema_versions(version) values (1) on conflict do nothing;
notify pgrst, 'reload schema';
commit;
