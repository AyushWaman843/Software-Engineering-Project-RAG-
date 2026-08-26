-- PART 6: unique personal/org subscription + write policies for activation
-- Run once in Supabase SQL Editor.

create unique index if not exists idx_truststack_sub_user_unique
  on public.truststack_subscriptions (user_id)
  where user_id is not null;

create unique index if not exists idx_truststack_sub_org_unique
  on public.truststack_subscriptions (org_id)
  where org_id is not null;

-- Allow authenticated users to manage their own personal subscription row
-- (service role still preferred for payment confirmation)
drop policy if exists "Users insert own subscription" on public.truststack_subscriptions;
create policy "Users insert own subscription"
  on public.truststack_subscriptions for insert
  with check (user_id = auth.uid() and org_id is null);

drop policy if exists "Users update own subscription" on public.truststack_subscriptions;
create policy "Users update own subscription"
  on public.truststack_subscriptions for update
  using (user_id = auth.uid() and org_id is null);
