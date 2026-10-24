-- Run after migrate_unified_auth.sql (or its parts). The API service role alone
-- may mutate scan balances; each reservation is one database transaction.

create or replace function public.reserve_scan_slot(
  p_user_id uuid, p_slot text, p_limit integer default 1
) returns boolean
language plpgsql security definer set search_path = public as $$
declare claimed boolean;
begin
  if p_slot = 'pilot_daily' then
    if public.get_user_tier(p_user_id) <> 'pilot' then return false; end if;
    insert into public.daily_scan_usage (user_id, scan_date, scans_used)
    values (p_user_id, current_date, 1)
    on conflict (user_id, scan_date) do update
      set scans_used = daily_scan_usage.scans_used + 1
      where daily_scan_usage.scans_used < greatest(0, p_limit)
    returning true into claimed;
  elsif p_slot = 'pro' then
    if not exists (
      select 1 from public.subscriptions
      where user_id = p_user_id and tier = 'pro' and status = 'active'
        and (current_end is null or current_end > now())
    ) then return false; end if;
    insert into public.user_entitlements (user_id, pro_scans_used, pro_scans_reset_at)
    select p_user_id, 1, now() + interval '1 month' where p_limit > 0
    on conflict (user_id) do update
      set pro_scans_used = case
            when user_entitlements.pro_scans_reset_at is null
              or user_entitlements.pro_scans_reset_at <= now() then 1
            else user_entitlements.pro_scans_used + 1 end,
          pro_scans_reset_at = case
            when user_entitlements.pro_scans_reset_at is null
              or user_entitlements.pro_scans_reset_at <= now()
              then now() + interval '1 month'
            else user_entitlements.pro_scans_reset_at end
      where user_entitlements.pro_scans_reset_at is null
        or user_entitlements.pro_scans_reset_at <= now()
        or user_entitlements.pro_scans_used < greatest(0, p_limit)
    returning true into claimed;
  elsif p_slot = 'free' then
    insert into public.user_entitlements (user_id, free_scans_used)
    select p_user_id, 1 where p_limit > 0
    on conflict (user_id) do update
      set free_scans_used = user_entitlements.free_scans_used + 1
      where user_entitlements.free_scans_used < greatest(0, p_limit)
    returning true into claimed;
  elsif p_slot = 'prepaid' then
    update public.user_entitlements
      set scan_credits = scan_credits - 1
      where user_id = p_user_id and scan_credits > 0
      returning true into claimed;
  else
    return false;
  end if;
  return coalesce(claimed, false);
end;
$$;

create or replace function public.refund_scan_slot(
  p_user_id uuid, p_slot text, p_scan_date date default current_date
) returns boolean
language plpgsql security definer set search_path = public as $$
declare changed boolean;
begin
  if p_slot = 'pilot_daily' then
    update public.daily_scan_usage
      set scans_used = scans_used - 1
      where user_id = p_user_id and scan_date = p_scan_date and scans_used > 0
      returning true into changed;
  elsif p_slot = 'pro' then
    update public.user_entitlements
      set pro_scans_used = pro_scans_used - 1
      where user_id = p_user_id and pro_scans_used > 0
      returning true into changed;
  elsif p_slot = 'free' then
    update public.user_entitlements
      set free_scans_used = free_scans_used - 1
      where user_id = p_user_id and free_scans_used > 0
      returning true into changed;
  elsif p_slot = 'prepaid' then
    insert into public.user_entitlements (user_id, scan_credits)
    values (p_user_id, 1)
    on conflict (user_id) do update
      set scan_credits = user_entitlements.scan_credits + 1
    returning true into changed;
  else
    return false;
  end if;
  return coalesce(changed, false);
end;
$$;

create or replace function public.grant_prepaid_scan_credit(p_user_id uuid)
returns boolean language plpgsql security definer set search_path = public as $$
begin
  insert into public.user_entitlements (user_id, scan_credits)
  values (p_user_id, 1)
  on conflict (user_id) do update
    set scan_credits = user_entitlements.scan_credits + 1;
  return true;
end;
$$;

revoke all on function public.reserve_scan_slot(uuid, text, integer) from public, anon, authenticated;
revoke all on function public.refund_scan_slot(uuid, text, date) from public, anon, authenticated;
revoke all on function public.grant_prepaid_scan_credit(uuid) from public, anon, authenticated;
grant execute on function public.reserve_scan_slot(uuid, text, integer) to service_role;
grant execute on function public.refund_scan_slot(uuid, text, date) to service_role;
grant execute on function public.grant_prepaid_scan_credit(uuid) to service_role;
