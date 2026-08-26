-- PART 3/5: Org RLS policies (non-recursive helpers)

-- Helper: check membership without recursive RLS
create or replace function public.is_org_member(p_org_id uuid)
returns boolean
language sql
security definer
stable
set search_path = public
as $$
  select exists (
    select 1 from public.organization_members
    where org_id = p_org_id and user_id = auth.uid()
  );
$$;

create or replace function public.is_org_admin(p_org_id uuid)
returns boolean
language sql
security definer
stable
set search_path = public
as $$
  select exists (
    select 1 from public.organization_members
    where org_id = p_org_id
      and user_id = auth.uid()
      and role in ('owner', 'admin')
  );
$$;

drop policy if exists "Members see own org" on public.organizations;
create policy "Members see own org"
  on public.organizations for select
  using (owner_id = auth.uid() or public.is_org_member(id));

drop policy if exists "Owners manage org" on public.organizations;
create policy "Owners manage org"
  on public.organizations for all
  using (owner_id = auth.uid());

drop policy if exists "Members see org members" on public.organization_members;
create policy "Members see org members"
  on public.organization_members for select
  using (user_id = auth.uid() or public.is_org_member(org_id));

drop policy if exists "Admins manage members" on public.organization_members;
create policy "Admins manage members"
  on public.organization_members for all
  using (public.is_org_admin(org_id));
