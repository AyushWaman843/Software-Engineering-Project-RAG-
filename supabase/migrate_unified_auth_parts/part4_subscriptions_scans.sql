-- PART 4/5: Subscriptions + daily scan usage

create table if not exists public.truststack_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  org_id uuid references public.organizations(id) on delete cascade,
  tier text not null default 'free' check (tier in ('free', 'pilot')),
  status text not null default 'active'
    check (status in ('active', 'cancelled', 'expired', 'trialing', 'past_due')),
  razorpay_subscription_id text unique,
  razorpay_customer_id text,
  razorpay_order_id text,
  price_paise integer not null default 0,
  current_period_start timestamptz,
  current_period_end timestamptz,
  trial_end timestamptz,
  cancelled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint subscription_owner check (
    (user_id is not null and org_id is null) or
    (user_id is null and org_id is not null)
  )
);

create index if not exists idx_truststack_sub_user on public.truststack_subscriptions(user_id);
create index if not exists idx_truststack_sub_org on public.truststack_subscriptions(org_id);
create index if not exists idx_truststack_sub_status on public.truststack_subscriptions(status);

alter table public.truststack_subscriptions enable row level security;

drop policy if exists "Users see own subscription" on public.truststack_subscriptions;
create policy "Users see own subscription"
  on public.truststack_subscriptions for select
  using (
    user_id = auth.uid()
    or public.is_org_member(org_id)
  );

create table if not exists public.daily_scan_usage (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  scan_date date not null default current_date,
  scans_used integer not null default 0,
  created_at timestamptz not null default now(),
  unique(user_id, scan_date)
);

create index if not exists idx_daily_scan_user_date
  on public.daily_scan_usage(user_id, scan_date desc);

alter table public.daily_scan_usage enable row level security;

drop policy if exists "Users see own scan usage" on public.daily_scan_usage;
create policy "Users see own scan usage"
  on public.daily_scan_usage for select
  using (user_id = auth.uid());
