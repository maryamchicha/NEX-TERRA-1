create table if not exists public.simulation_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  field jsonb not null check (jsonb_typeof(field) = 'object'),
  inputs jsonb not null check (jsonb_typeof(inputs) = 'object'),
  result jsonb not null check (jsonb_typeof(result) = 'object'),
  created_at timestamptz not null default now(),
  consented_at timestamptz not null
);

create index if not exists simulation_runs_user_created_at_idx
  on public.simulation_runs (user_id, created_at desc);

alter table public.simulation_runs enable row level security;

revoke all on public.simulation_runs from anon, authenticated;
grant select, insert, delete on public.simulation_runs to authenticated;

drop policy if exists "Users can read their own simulation runs"
  on public.simulation_runs;
create policy "Users can read their own simulation runs"
  on public.simulation_runs for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users can create their own simulation runs"
  on public.simulation_runs;
create policy "Users can create their own simulation runs"
  on public.simulation_runs for insert to authenticated
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can delete their own simulation runs"
  on public.simulation_runs;
create policy "Users can delete their own simulation runs"
  on public.simulation_runs for delete to authenticated
  using ((select auth.uid()) = user_id);
