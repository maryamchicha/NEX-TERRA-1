create table if not exists public.farm_profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  field jsonb not null check (jsonb_typeof(field) = 'object'),
  baseline jsonb not null check (jsonb_typeof(baseline) = 'object'),
  updated_at timestamptz not null default now(),
  consented_at timestamptz not null
);

alter table public.farm_profiles enable row level security;

revoke all on public.farm_profiles from anon, authenticated;
grant select, insert, update on public.farm_profiles to authenticated;

drop policy if exists "Users can read their own farm profile"
  on public.farm_profiles;
create policy "Users can read their own farm profile"
  on public.farm_profiles for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users can create their own farm profile"
  on public.farm_profiles;
create policy "Users can create their own farm profile"
  on public.farm_profiles for insert to authenticated
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can update their own farm profile"
  on public.farm_profiles;
create policy "Users can update their own farm profile"
  on public.farm_profiles for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
