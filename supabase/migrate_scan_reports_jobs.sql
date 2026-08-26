-- Free-tier persistence: keep scan reports + job status in Supabase so
-- Render ephemeral disk wipes do not lose paid results.
-- Run once in Supabase Dashboard → SQL → New query.

create table if not exists public.scan_reports (
  report_id text primary key,
  payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_scan_reports_updated
  on public.scan_reports (updated_at desc);

alter table public.scan_reports enable row level security;
-- Service role (API) bypasses RLS. No anon/authenticated policies on purpose.

create table if not exists public.scan_jobs (
  job_id text primary key,
  payload jsonb not null,
  status text not null default 'running',
  updated_at timestamptz not null default now()
);

create index if not exists idx_scan_jobs_status
  on public.scan_jobs (status);

alter table public.scan_jobs enable row level security;
