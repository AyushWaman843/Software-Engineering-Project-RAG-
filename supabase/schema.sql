-- Run in Supabase SQL Editor (Dashboard → SQL → New query)
--
-- Already set up premium_grants + user_scans only?
-- Run supabase/migrate_missing_tables.sql instead (adds missing tables + backfill).
--
-- Fresh project? Run this entire file once.

-- Premium payment grants (browser visitor_id)
create table if not exists public.premium_grants (
  id uuid primary key default gen_random_uuid(),
  visitor_id text not null,
  payment_id text not null unique,
  order_id text not null,
  amount_paise integer not null default 0,
  currency text not null default 'INR',
  created_at timestamptz not null default now(),
  expires_at timestamptz
);

create index if not exists idx_premium_grants_visitor
  on public.premium_grants (visitor_id);

alter table public.premium_grants enable row level security;

-- User scan history (linked to Supabase Auth)
create table if not exists public.user_scans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  report_id text not null,
  url text not null,
  score integer not null default 0,
  verdict text not null default '',
  scanned_at timestamptz not null default now(),
  unique (user_id, report_id)
);

create index if not exists idx_user_scans_user_scanned
  on public.user_scans (user_id, scanned_at desc);

alter table public.user_scans enable row level security;

create policy "Users read own scans"
  on public.user_scans for select
  using (auth.uid() = user_id);

create policy "Users insert own scans"
  on public.user_scans for insert
  with check (auth.uid() = user_id);

create policy "Users update own scans"
  on public.user_scans for update
  using (auth.uid() = user_id);

create policy "Users delete own scans"
  on public.user_scans for delete
  using (auth.uid() = user_id);

-- Per-user scan quotas (free tier: 1 lifetime preview scan)
-- scan_credits stores prepaid pay-before-scan slots (₹299), not bonus credits from unlocks.
-- pro_scans_used tracks scans consumed from Pro subscription (resets monthly).
create table if not exists public.user_entitlements (
  user_id uuid primary key references auth.users(id) on delete cascade,
  free_scans_used integer not null default 0 check (free_scans_used >= 0),
  scan_credits integer not null default 0 check (scan_credits >= 0),
  pro_scans_used integer not null default 0 check (pro_scans_used >= 0),
  pro_scans_reset_at timestamptz,
  updated_at timestamptz not null default now()
);

alter table public.user_entitlements enable row level security;

-- Anonymous visitor scan counts (before sign-in)
create table if not exists public.visitor_scans (
  visitor_id text primary key,
  scan_count integer not null default 0 check (scan_count >= 0),
  claimed_by_user_id uuid references auth.users(id) on delete set null,
  updated_at timestamptz not null default now()
);

-- Per-report one-time unlocks (pay-per-report, ₹299)
create table if not exists public.report_unlocks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  report_id text not null,
  payment_id text not null,
  order_id text not null,
  amount_paise integer not null default 0,
  currency text not null default 'INR',
  unlocked_at timestamptz not null default now(),
  unique (user_id, report_id)
);

-- One Razorpay payment unlocks at most one report (replay defense).
-- Exclude backfill placeholders that are not real Razorpay ids.
create unique index if not exists idx_report_unlocks_payment_id
  on public.report_unlocks (payment_id)
  where payment_id is not null
    and payment_id <> ''
    and payment_id <> 'synced-from-file';

create index if not exists idx_report_unlocks_user_report
  on public.report_unlocks (user_id, report_id);

alter table public.report_unlocks enable row level security;

create policy "Users read own report unlocks"
  on public.report_unlocks for select
  using (auth.uid() = user_id);

-- Pro subscription tier (₹999/month recurring)
-- Grants 5 full-report scans per month. Scans reset on the 1st.
create table if not exists public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  tier text not null default 'pro' check (tier in ('pro', 'enterprise')),
  razorpay_subscription_id text unique,
  razorpay_plan_id text,
  status text not null default 'created' check (status in ('created', 'authenticated', 'active', 'paused', 'halted', 'cancelled', 'completed', 'expired')),
  current_start timestamptz,
  current_end timestamptz,
  charge_at timestamptz,
  ended_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, tier)
);

create index if not exists idx_subscriptions_user_status
  on public.subscriptions (user_id, status);

create index if not exists idx_subscriptions_razorpay
  on public.subscriptions (razorpay_subscription_id);

alter table public.subscriptions enable row level security;

create policy "Users read own subscriptions"
  on public.subscriptions for select
  using (auth.uid() = user_id);

-- Durable report/job storage (Render free tier has ephemeral disk)
create table if not exists public.scan_reports (
  report_id text primary key,
  payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_scan_reports_updated
  on public.scan_reports (updated_at desc);

alter table public.scan_reports enable row level security;

create table if not exists public.scan_jobs (
  job_id text primary key,
  payload jsonb not null,
  status text not null default 'running',
  updated_at timestamptz not null default now()
);

create index if not exists idx_scan_jobs_status
  on public.scan_jobs (status);

alter table public.scan_jobs enable row level security;

-- Enable email/password auth in Supabase Dashboard → Authentication → Providers → Email
