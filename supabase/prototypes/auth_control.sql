-- LOCAL TEST PROTOTYPE ONLY. Not a Supabase migration or a Vault adapter.
-- No tokens, passwords, decrypted secret view, network, or provider calls.
-- The only stored payload is a synthetic integer generation plus control metadata.
begin;

do $$
begin
    if current_database() !~ '^job_auth_test_[0-9a-f]{32}$' or session_user <> 'postgres' then
        raise exception 'AUTH_LAB_DATABASE_REQUIRED';
    end if;
    -- Refuse TCP sessions, including loopback: only a server-local Unix socket is accepted.
    if inet_client_addr() is not null then
        raise exception 'AUTH_LAB_LOCAL_SOCKET_REQUIRED';
    end if;
    -- Existing lab namespace without its control relation is a partial/lost installation.
    if (pg_catalog.to_regnamespace('job_auth_lab_private') is not null
        or pg_catalog.to_regnamespace('job_auth_lab') is not null)
        and pg_catalog.to_regclass('job_auth_lab_private.control') is null then
        raise exception 'AUTH_STATE_MISSING';
    end if;
    if not exists (select 1 from pg_roles where rolname = 'job_auth_lab_owner') then
        create role job_auth_lab_owner nologin nosuperuser nocreatedb nocreaterole
            noreplication nobypassrls noinherit;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'job_auth_lab_client') then
        create role job_auth_lab_client login password null nosuperuser nocreatedb
            nocreaterole noreplication nobypassrls noinherit;
    end if;
    if exists (
        select 1 from pg_roles where rolname in ('job_auth_lab_owner', 'job_auth_lab_client')
        and (rolsuper or rolcreatedb or rolcreaterole or rolreplication or rolbypassrls
             or rolinherit or (rolname = 'job_auth_lab_owner' and rolcanlogin)
             or (rolname = 'job_auth_lab_client' and not rolcanlogin))
    ) or exists (
        select 1 from pg_auth_members m join pg_roles r on r.oid = m.member
        where r.rolname in ('job_auth_lab_owner', 'job_auth_lab_client')
    ) or exists (
        -- No other role may SET ROLE to the protected owner.
        select 1 from pg_auth_members m join pg_roles r on r.oid = m.roleid
        where r.rolname = 'job_auth_lab_owner'
    ) or exists (
        -- Check only NULL status in the isolated lab; never return a password verifier.
        select 1 from pg_authid where rolname in ('job_auth_lab_owner', 'job_auth_lab_client')
            and rolpassword is not null
    ) then
        raise exception 'AUTH_LAB_ROLE_ATTRIBUTES_REQUIRED';
    end if;
end;
$$;

create schema if not exists job_auth_lab_private authorization job_auth_lab_owner;
create schema if not exists job_auth_lab authorization job_auth_lab_owner;
revoke all on schema job_auth_lab_private, job_auth_lab from public, job_auth_lab_client;
grant usage on schema job_auth_lab to job_auth_lab_client;

do $$
begin
    if pg_catalog.to_regclass('job_auth_lab_private.control') is null then
        create table job_auth_lab_private.control (
            singleton boolean primary key default true check (singleton),
            version bigint not null default 0 check (version >= 0),
            fixture_generation bigint not null default 0 check (fixture_generation >= 0),
            epoch bigint not null default 1 check (epoch > 0),
            state text not null default 'ready'
                check (state in ('ready', 'in_flight', 'pending_validation', 'blocked')),
            owner uuid,
            check ((state = 'ready' and owner is null) or (state <> 'ready' and owner is not null))
        );
        insert into job_auth_lab_private.control (singleton) values (true);
    elsif not exists (select 1 from job_auth_lab_private.control where singleton) then
        raise exception 'AUTH_STATE_MISSING';
    end if;
end;
$$;
alter table job_auth_lab_private.control owner to job_auth_lab_owner;
alter table job_auth_lab_private.control enable row level security;
revoke all on all tables in schema job_auth_lab_private from public, job_auth_lab_client;
-- Existing state is never seeded/reset during reapplication, including missing rows.

create or replace function job_auth_lab.snapshot()
returns jsonb language plpgsql security definer set search_path = '' as $$
declare result jsonb;
begin
    -- Direct local LOGIN identity only. This is NOT a proven Supavisor identity contract.
    if session_user <> 'job_auth_lab_client' then
        raise exception 'AUTH_CALLER_REQUIRED';
    end if;
    select jsonb_build_object('state', state, 'version', version,
        'fixture_generation', fixture_generation, 'epoch', epoch, 'owner', owner)
    into result from job_auth_lab_private.control where singleton;
    if not found then raise exception 'AUTH_STATE_MISSING'; end if;
    return result;
end;
$$;

create or replace function job_auth_lab.begin_turn(
    p_owner uuid, p_expected_version bigint, p_expected_epoch bigint
) returns bigint language plpgsql security definer set search_path = '' as $$
declare result bigint;
begin
    if session_user <> 'job_auth_lab_client' then
        raise exception 'AUTH_CALLER_REQUIRED';
    end if;
    if p_owner is null then raise exception 'AUTH_OWNER_REQUIRED'; end if;
    update job_auth_lab_private.control set state = 'in_flight', owner = p_owner
    where singleton and state = 'ready' and owner is null
        and version = p_expected_version and epoch = p_expected_epoch
    returning fixture_generation into result;
    if not found then raise exception 'AUTH_STATE_CONFLICT'; end if;
    return result;
end;
$$;

create or replace function job_auth_lab.stage_generation(
    p_owner uuid, p_expected_version bigint, p_expected_epoch bigint, p_generation bigint
) returns bigint language plpgsql security definer set search_path = '' as $$
declare result bigint;
begin
    if session_user <> 'job_auth_lab_client' then
        raise exception 'AUTH_CALLER_REQUIRED';
    end if;
    update job_auth_lab_private.control
    set fixture_generation = p_generation, version = version + 1, state = 'pending_validation'
    where singleton and state = 'in_flight' and owner = p_owner
        and version = p_expected_version and epoch = p_expected_epoch
        and p_generation = fixture_generation + 1
    returning version into result;
    if not found then raise exception 'AUTH_STATE_CONFLICT'; end if;
    return result;
end;
$$;

create or replace function job_auth_lab.block_turn(
    p_owner uuid, p_expected_version bigint, p_expected_epoch bigint
) returns void language plpgsql security definer set search_path = '' as $$
begin
    if session_user <> 'job_auth_lab_client' then
        raise exception 'AUTH_CALLER_REQUIRED';
    end if;
    update job_auth_lab_private.control set state = 'blocked'
    where singleton and state in ('in_flight', 'pending_validation') and owner = p_owner
        and version = p_expected_version and epoch = p_expected_epoch;
    if not found then raise exception 'AUTH_STATE_CONFLICT'; end if;
end;
$$;

alter function job_auth_lab.snapshot() owner to job_auth_lab_owner;
alter function job_auth_lab.begin_turn(uuid, bigint, bigint) owner to job_auth_lab_owner;
alter function job_auth_lab.stage_generation(uuid, bigint, bigint, bigint) owner to job_auth_lab_owner;
alter function job_auth_lab.block_turn(uuid, bigint, bigint) owner to job_auth_lab_owner;
revoke all on all functions in schema job_auth_lab from public, job_auth_lab_client;
grant execute on function job_auth_lab.snapshot(), job_auth_lab.begin_turn(uuid, bigint, bigint),
    job_auth_lab.stage_generation(uuid, bigint, bigint, bigint),
    job_auth_lab.block_turn(uuid, bigint, bigint) to job_auth_lab_client;
alter default privileges for role postgres in schema job_auth_lab revoke execute on functions from public;
alter default privileges for role job_auth_lab_owner in schema job_auth_lab revoke execute on functions from public;
-- No client finalize/reset/TTL takeover operation: real credential-value verification is absent.
commit;
