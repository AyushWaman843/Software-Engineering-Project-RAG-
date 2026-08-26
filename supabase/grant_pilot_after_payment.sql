-- One-time: grant Pilot after Razorpay payment succeeded but app activation failed.
-- Replace the email, then run in Supabase SQL Editor.

-- 1) Prefer update if a personal subscription row already exists
update public.truststack_subscriptions ts
set
  tier = 'pilot',
  status = 'active',
  price_paise = 99900,
  current_period_start = now(),
  current_period_end = now() + interval '1 month',
  updated_at = now()
from auth.users u
where ts.user_id = u.id
  and ts.org_id is null
  and lower(u.email) = lower('YOUR_EMAIL_HERE');

-- 2) If no row was updated, insert one
insert into public.truststack_subscriptions (
  user_id,
  tier,
  status,
  price_paise,
  current_period_start,
  current_period_end
)
select
  u.id,
  'pilot',
  'active',
  99900,
  now(),
  now() + interval '1 month'
from auth.users u
where lower(u.email) = lower('YOUR_EMAIL_HERE')
  and not exists (
    select 1
    from public.truststack_subscriptions ts
    where ts.user_id = u.id
      and ts.org_id is null
  );
