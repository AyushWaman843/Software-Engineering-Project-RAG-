-- One-time: restore prepaid scan credits burned by interrupted Render free-tier scans.
-- Replace the email if needed, then run in Supabase SQL Editor.

update public.user_entitlements ue
set
  scan_credits = coalesce(ue.scan_credits, 0) + 2,
  updated_at = now()
from auth.users u
where ue.user_id = u.id
  and lower(u.email) = lower('ayushvwaman@gmail.com');

-- If no entitlements row exists yet:
insert into public.user_entitlements (user_id, free_scans_used, scan_credits)
select u.id, 0, 2
from auth.users u
where lower(u.email) = lower('ayushvwaman@gmail.com')
  and not exists (
    select 1 from public.user_entitlements e where e.user_id = u.id
  );