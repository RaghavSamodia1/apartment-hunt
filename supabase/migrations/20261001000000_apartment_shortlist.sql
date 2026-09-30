-- Shared shortlist for the apartment-hunt app.
-- Tables are closed to direct access; the browser only calls the three functions below,
-- each of which requires the shared passcode (stored as a bcrypt hash in apt_config).

create extension if not exists pgcrypto with schema extensions;

create table if not exists public.apt_config (
  id int primary key default 1 check (id = 1),
  passcode_hash text not null
);

create table if not exists public.apt_state (
  project_id text primary key check (char_length(project_id) <= 120),
  decision text check (decision in ('s', 'r')),          -- s = shortlisted, r = rejected, null = cleared
  note text check (char_length(note) <= 4000),
  updated_by text check (char_length(updated_by) <= 40),
  updated_at timestamptz not null default now()
);

alter table public.apt_config enable row level security;
alter table public.apt_state enable row level security;
revoke all on public.apt_config from anon, authenticated;
revoke all on public.apt_state from anon, authenticated;

drop function if exists public.apt_get(text);
drop function if exists public.apt_set(text, text, text, text, text);
drop function if exists public.apt_change_code(text, text);
drop function if exists public.apt_check(text);

create or replace function public.apt_check(p_code text)
returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from public.apt_config c
    where c.passcode_hash = extensions.crypt(coalesce(p_code, ''), c.passcode_hash)
  );
$$;
revoke all on function public.apt_check(text) from public, anon, authenticated;

-- Read everything (decisions + notes).
create or replace function public.apt_get(p_code text)
returns json
language plpgsql stable security definer set search_path = ''
as $$
begin
  if not public.apt_check(p_code) then
    perform pg_sleep(0.6);
    raise exception 'bad_code' using errcode = '28000';
  end if;
  return coalesce((
    select json_agg(json_build_object(
      'id', s.project_id, 'd', s.decision, 'n', s.note, 'by', s.updated_by, 'at', s.updated_at))
    from public.apt_state s
  ), '[]'::json);
end;
$$;

-- Set decision and/or note for one project. Pass null to leave a field alone, '' to clear it.
create or replace function public.apt_set(p_code text, p_pid text, p_decision text default null, p_note text default null, p_who text default null)
returns void
language plpgsql security definer set search_path = ''
as $$
begin
  if not public.apt_check(p_code) then
    perform pg_sleep(0.6);
    raise exception 'bad_code' using errcode = '28000';
  end if;
  if p_pid is null or char_length(p_pid) = 0 or char_length(p_pid) > 120 then
    raise exception 'bad_project' using errcode = '22023';
  end if;
  if p_decision is not null and p_decision not in ('s', 'r', '') then
    raise exception 'bad_decision' using errcode = '22023';
  end if;
  insert into public.apt_state as t (project_id, decision, note, updated_by, updated_at)
  values (p_pid, nullif(p_decision, ''), nullif(left(p_note, 4000), ''), left(p_who, 40), now())
  on conflict (project_id) do update set
    decision   = case when p_decision is null then t.decision else nullif(p_decision, '') end,
    note       = case when p_note is null then t.note else nullif(left(p_note, 4000), '') end,
    updated_by = coalesce(left(p_who, 40), t.updated_by),
    updated_at = now();
  -- drop rows that carry no information
  delete from public.apt_state where project_id = p_pid and decision is null and note is null;
end;
$$;

-- Rotate the passcode (needs the current one).
create or replace function public.apt_change_code(p_code text, p_new_code text)
returns void
language plpgsql security definer set search_path = ''
as $$
begin
  if not public.apt_check(p_code) then
    perform pg_sleep(0.6);
    raise exception 'bad_code' using errcode = '28000';
  end if;
  if p_new_code is null or char_length(p_new_code) < 8 then
    raise exception 'code_too_short' using errcode = '22023';
  end if;
  update public.apt_config set passcode_hash = extensions.crypt(p_new_code, extensions.gen_salt('bf'));
end;
$$;

revoke all on function public.apt_get(text), public.apt_set(text, text, text, text, text), public.apt_change_code(text, text) from public;
grant execute on function public.apt_get(text), public.apt_set(text, text, text, text, text), public.apt_change_code(text, text) to anon;
