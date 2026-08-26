-- FULL DEMO RESET — deletes all app data and all auth accounts.
-- Run once in Supabase Dashboard → SQL Editor.
-- Irreversible. Re-sign-up required after this.

-- App tables (order: children before parents where needed)
truncate table public.report_unlocks restart identity cascade;
truncate table public.user_scans restart identity cascade;
truncate table public.user_entitlements restart identity cascade;
truncate table public.visitor_scans restart identity cascade;
truncate table public.premium_grants restart identity cascade;

-- All Supabase Auth users (cascades to tables above via FK)
delete from auth.users;
