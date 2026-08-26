-- PART 5/5: Helper functions

create or replace function public.get_user_tier(p_user_id uuid)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_tier text := 'free';
  v_org_tier text;
begin
  select tier into v_tier
  from public.truststack_subscriptions
  where user_id = p_user_id
    and status in ('active', 'trialing')
    and (current_period_end is null or current_period_end > now())
  order by case tier when 'pilot' then 1 else 2 end
  limit 1;

  if v_tier = 'pilot' then
    return v_tier;
  end if;

  select ts.tier into v_org_tier
  from public.truststack_subscriptions ts
  join public.organization_members om on om.org_id = ts.org_id
  where om.user_id = p_user_id
    and ts.status in ('active', 'trialing')
    and (ts.current_period_end is null or ts.current_period_end > now())
  order by case ts.tier when 'pilot' then 1 else 2 end
  limit 1;

  if v_org_tier = 'pilot' then
    return v_org_tier;
  end if;

  return coalesce(v_tier, 'free');
end;
$$;

create or replace function public.can_user_scan(p_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_tier text;
  v_scans_today integer;
  v_free_preview_used boolean;
  v_scan_credits integer;
begin
  v_tier := public.get_user_tier(p_user_id);

  if v_tier = 'pilot' then
    select coalesce(scans_used, 0) into v_scans_today
    from public.daily_scan_usage
    where user_id = p_user_id and scan_date = current_date;

    if coalesce(v_scans_today, 0) < 1 then
      return jsonb_build_object(
        'can_scan', true,
        'tier', v_tier,
        'scan_type', 'pilot_daily',
        'scans_remaining', 1 - coalesce(v_scans_today, 0)
      );
    end if;

    select coalesce(scan_credits, 0) into v_scan_credits
    from public.user_entitlements
    where user_id = p_user_id;

    if coalesce(v_scan_credits, 0) > 0 then
      return jsonb_build_object(
        'can_scan', true,
        'tier', v_tier,
        'scan_type', 'prepaid',
        'scans_remaining', v_scan_credits,
        'message', 'Today''s Pilot scan used — using a paid full-scan credit.'
      );
    end if;

    return jsonb_build_object(
      'can_scan', false,
      'tier', v_tier,
      'reason', 'daily_limit_reached',
      'message', 'Today''s Pilot scan used. Buy an extra full scan for ₹299 or come back tomorrow.',
      'scans_remaining', 0
    );
  end if;

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
    'message', 'Pay ₹299 per scan or upgrade to Pilot for daily scans.',
    'scans_remaining', 0
  );
end;
$$;

create or replace function public.record_scan_usage(p_user_id uuid, p_scan_type text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
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
$$;
