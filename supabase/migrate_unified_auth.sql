-- ============================================================================
-- TrustStack Unified Authentication + Pilot Subscription System
-- Run in Supabase Dashboard → SQL Editor → New query
-- ============================================================================

-- ============================================================================
-- PART 1: USER PROFILES (extends auth.users)
-- ============================================================================

create table if not exists public.user_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  account_type text not null default 'individual' 
    check (account_type in ('individual', 'organization')),
  onboarding_completed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.user_profiles enable row level security;

-- Users can read and update their own profile
create policy "Users read own profile"
  on public.user_profiles for select
  using (auth.uid() = user_id);

create policy "Users update own profile"
  on public.user_profiles for update
  using (auth.uid() = user_id);

create policy "Users insert own profile"
  on public.user_profiles for insert
  with check (auth.uid() = user_id);

-- Auto-create profile on user signup
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.user_profiles (user_id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data->>'full_name', new.email));
  return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- ============================================================================
-- PART 2: ORGANIZATIONS
-- ============================================================================

create table if not exists public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text unique not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  logo_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_organizations_owner on public.organizations(owner_id);
create index if not exists idx_organizations_slug on public.organizations(slug);

alter table public.organizations enable row level security;

-- ============================================================================
-- PART 3: ORGANIZATION MEMBERS
-- ============================================================================

create table if not exists public.organization_members (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'member' 
    check (role in ('owner', 'admin', 'member')),
  invited_by uuid references auth.users(id) on delete set null,
  invited_at timestamptz not null default now(),
  joined_at timestamptz,
  unique(org_id, user_id)
);

create index if not exists idx_org_members_user on public.organization_members(user_id);
create index if not exists idx_org_members_org on public.organization_members(org_id);

alter table public.organization_members enable row level security;

-- RLS: Members can see their org's members
create policy "Members see org members"
  on public.organization_members for select
  using (
    user_id = auth.uid() or
    org_id in (
      select org_id from public.organization_members where user_id = auth.uid()
    )
  );

-- RLS: Owners/admins can manage members
create policy "Admins manage members"
  on public.organization_members for all
  using (
    org_id in (
      select org_id from public.organization_members 
      where user_id = auth.uid() and role in ('owner', 'admin')
    )
  );

-- RLS for organizations: members can see their org
create policy "Members see own org"
  on public.organizations for select
  using (
    owner_id = auth.uid() or
    id in (select org_id from public.organization_members where user_id = auth.uid())
  );

create policy "Owners manage org"
  on public.organizations for all
  using (owner_id = auth.uid());

-- ============================================================================
-- PART 4: UNIFIED SUBSCRIPTIONS (replaces scanner's old system)
-- ============================================================================

create table if not exists public.truststack_subscriptions (
  id uuid primary key default gen_random_uuid(),
  -- Either user or org owns the subscription (not both, enforced below)
  user_id uuid references auth.users(id) on delete cascade,
  org_id uuid references public.organizations(id) on delete cascade,
  
  -- Subscription details
  tier text not null default 'free' check (tier in ('free', 'pilot')),
  status text not null default 'active' 
    check (status in ('active', 'cancelled', 'expired', 'trialing', 'past_due')),
  
  -- Payment info
  razorpay_subscription_id text unique,
  razorpay_customer_id text,
  razorpay_order_id text,
  price_paise integer not null default 0,
  
  -- Billing period
  current_period_start timestamptz,
  current_period_end timestamptz,
  trial_end timestamptz,
  cancelled_at timestamptz,
  
  -- Metadata
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  
  -- Constraint: must have either user_id or org_id
  constraint subscription_owner check (
    (user_id is not null and org_id is null) or
    (user_id is null and org_id is not null)
  )
);

create index if not exists idx_truststack_sub_user on public.truststack_subscriptions(user_id);
create index if not exists idx_truststack_sub_org on public.truststack_subscriptions(org_id);
create index if not exists idx_truststack_sub_status on public.truststack_subscriptions(status);

alter table public.truststack_subscriptions enable row level security;

-- RLS: Users see their own or their org's subscription
create policy "Users see own subscription"
  on public.truststack_subscriptions for select
  using (
    user_id = auth.uid() or
    org_id in (select org_id from public.organization_members where user_id = auth.uid())
  );

-- ============================================================================
-- PART 5: DAILY SCAN USAGE (for Pilot's 1 scan/day limit)
-- ============================================================================

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

create policy "Users see own scan usage"
  on public.daily_scan_usage for select
  using (user_id = auth.uid());

-- ============================================================================
-- PART 6: HELPER FUNCTIONS
-- ============================================================================

-- Get user's effective tier (checks personal + org subscriptions)
create or replace function public.get_user_tier(p_user_id uuid)
returns text as $$
declare
  v_tier text := 'free';
  v_org_tier text;
begin
  -- Check personal subscription first
  select tier into v_tier
  from public.truststack_subscriptions
  where user_id = p_user_id
    and status in ('active', 'trialing')
    and (current_period_end is null or current_period_end > now())
  order by 
    case tier when 'pilot' then 1 else 2 end
  limit 1;
  
  if v_tier = 'pilot' then
    return v_tier;
  end if;
  
  -- Check org subscriptions
  select ts.tier into v_org_tier
  from public.truststack_subscriptions ts
  join public.organization_members om on om.org_id = ts.org_id
  where om.user_id = p_user_id
    and ts.status in ('active', 'trialing')
    and (ts.current_period_end is null or ts.current_period_end > now())
  order by 
    case ts.tier when 'pilot' then 1 else 2 end
  limit 1;
  
  if v_org_tier = 'pilot' then
    return v_org_tier;
  end if;
  
  return coalesce(v_tier, 'free');
end;
$$ language plpgsql security definer;

-- Check if user can scan today (Pilot: 1/day, Free: check credits)
create or replace function public.can_user_scan(p_user_id uuid)
returns jsonb as $$
declare
  v_tier text;
  v_scans_today integer;
  v_free_preview_used boolean;
  v_scan_credits integer;
begin
  v_tier := public.get_user_tier(p_user_id);
  
  if v_tier = 'pilot' then
    -- Pilot: check daily usage (1 per day, non-stackable)
    select coalesce(scans_used, 0) into v_scans_today
    from public.daily_scan_usage
    where user_id = p_user_id and scan_date = current_date;
    
    if coalesce(v_scans_today, 0) >= 1 then
      return jsonb_build_object(
        'can_scan', false,
        'tier', v_tier,
        'reason', 'daily_limit_reached',
        'message', 'You have used your daily scan. Come back tomorrow!',
        'scans_remaining', 0
      );
    end if;
    
    return jsonb_build_object(
      'can_scan', true,
      'tier', v_tier,
      'scan_type', 'pilot_daily',
      'scans_remaining', 1 - coalesce(v_scans_today, 0)
    );
  end if;
  
  -- Free tier: check if preview used, then require payment
  select 
    coalesce(free_scans_used, 0) >= 1,
    coalesce(scan_credits, 0)
  into v_free_preview_used, v_scan_credits
  from public.user_entitlements
  where user_id = p_user_id;
  
  if not coalesce(v_free_preview_used, false) then
    return jsonb_build_object(
      'can_scan', true,
      'tier', 'free',
      'scan_type', 'free_preview',
      'message', 'This is your free preview scan. Results will be limited.',
      'scans_remaining', 1
    );
  end if;
  
  if coalesce(v_scan_credits, 0) > 0 then
    return jsonb_build_object(
      'can_scan', true,
      'tier', 'free',
      'scan_type', 'prepaid',
      'scans_remaining', v_scan_credits
    );
  end if;
  
  return jsonb_build_object(
    'can_scan', false,
    'tier', 'free',
    'reason', 'payment_required',
    'message', 'Pay ₹299 per scan or upgrade to Pilot for unlimited daily scans.',
    'scans_remaining', 0
  );
end;
$$ language plpgsql security definer;

-- Record scan usage
create or replace function public.record_scan_usage(p_user_id uuid, p_scan_type text)
returns boolean as $$
begin
  if p_scan_type = 'pilot_daily' then
    insert into public.daily_scan_usage (user_id, scan_date, scans_used)
    values (p_user_id, current_date, 1)
    on conflict (user_id, scan_date) 
    do update set scans_used = daily_scan_usage.scans_used + 1;
    return true;
  end if;
  
  if p_scan_type = 'free_preview' then
    update public.user_entitlements
    set free_scans_used = coalesce(free_scans_used, 0) + 1
    where user_id = p_user_id;
    
    if not found then
      insert into public.user_entitlements (user_id, free_scans_used, scan_credits)
      values (p_user_id, 1, 0);
    end if;
    return true;
  end if;
  
  if p_scan_type = 'prepaid' then
    update public.user_entitlements
    set scan_credits = greatest(0, coalesce(scan_credits, 0) - 1)
    where user_id = p_user_id;
    return true;
  end if;
  
  return false;
end;
$$ language plpgsql security definer;

-- ============================================================================
-- PART 7: CLEANUP / MIGRATION HELPERS
-- ============================================================================

-- Create free subscription for existing users who don't have one
-- (Run manually if needed)
-- insert into public.truststack_subscriptions (user_id, tier, status)
-- select id, 'free', 'active'
-- from auth.users u
-- where not exists (
--   select 1 from public.truststack_subscriptions ts where ts.user_id = u.id
-- );

-- ============================================================================
-- DONE! New tables created:
-- - user_profiles
-- - organizations  
-- - organization_members
-- - truststack_subscriptions
-- - daily_scan_usage
--
-- Helper functions:
-- - get_user_tier(user_id) → 'free' | 'pilot'
-- - can_user_scan(user_id) → jsonb with scan permission details
-- - record_scan_usage(user_id, scan_type) → boolean
-- ============================================================================
