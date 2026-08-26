-- Allow signed-in users to read their own prepaid scan credits (for scanner UI).
-- Run in Supabase SQL Editor.

drop policy if exists "Users read own entitlements" on public.user_entitlements;
create policy "Users read own entitlements"
  on public.user_entitlements
  for select
  using (auth.uid() = user_id);

-- Also expose via RPC (works even if table policies are tight elsewhere)
create or replace function public.get_my_prepaid_scans()
returns integer
language sql
security definer
set search_path = public
stable
as $$
  select coalesce(
    (select scan_credits from public.user_entitlements where user_id = auth.uid()),
    0
  );
$$;

grant execute on function public.get_my_prepaid_scans() to authenticated;
grant execute on function public.get_my_prepaid_scans() to anon;
