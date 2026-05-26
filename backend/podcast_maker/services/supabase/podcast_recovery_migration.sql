alter table public.podcasts
  add column if not exists task_id text,
  add column if not exists status text not null default 'completed',
  add column if not exists checkpoint text not null default 'completed',
  add column if not exists config jsonb not null default '{}'::jsonb,
  add column if not exists error text,
  add column if not exists created_at timestamptz not null default now(),
  add column if not exists updated_at timestamptz not null default now();

create unique index if not exists podcasts_task_id_key on public.podcasts (task_id);
create index if not exists podcasts_user_id_status_idx on public.podcasts (user_id, status);

create or replace function public.set_podcasts_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_podcasts_updated_at on public.podcasts;
create trigger set_podcasts_updated_at
  before update on public.podcasts
  for each row
  execute function public.set_podcasts_updated_at();

