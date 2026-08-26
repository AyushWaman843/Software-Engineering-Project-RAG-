import { createClient, supabaseConfigured } from "@/lib/supabase/client";

export type TrustStackTier = "free" | "pilot";

export interface TrustStackEntitlements {
  tier: TrustStackTier;
  /** Prepaid full-scan credits (user_entitlements.scan_credits). */
  prepaidScans: number;
}

/** Same source of truth as TrustStack SubscriptionContext (+ prepaid credits). */
export async function fetchTrustStackEntitlements(
  userId: string,
  accessToken?: string,
): Promise<TrustStackEntitlements> {
  if (!userId || !supabaseConfigured()) {
    return { tier: "free", prepaidScans: 0 };
  }

  let tier: TrustStackTier = "free";
  let prepaidScans = 0;

  try {
    // Prefer Next server route (service role) so RLS cannot hide credits.
    if (accessToken && typeof window !== "undefined") {
      const res = await fetch(`${window.location.origin}/scanner/api/me/entitlements`, {
        headers: { Authorization: `Bearer ${accessToken}` },
        credentials: "include",
        cache: "no-store",
      });
      if (res.ok) {
        const data = (await res.json()) as {
          tier?: string;
          prepaid_scans?: number;
          scan_credits?: number;
        };
        if (data.tier === "pilot" || data.tier === "free") tier = data.tier;
        prepaidScans = Math.max(0, Number(data.prepaid_scans ?? data.scan_credits) || 0);
        if (tier === "pilot" || prepaidScans > 0) {
          return { tier, prepaidScans };
        }
      }
    }

    const supabase = createClient();

    const [{ data: tierData, error: tierError }, prepaidRpc, entRes] = await Promise.all([
      supabase.rpc("get_user_tier", { p_user_id: userId }),
      supabase.rpc("get_my_prepaid_scans"),
      supabase
        .from("user_entitlements")
        .select("scan_credits")
        .eq("user_id", userId)
        .maybeSingle(),
    ]);

    if (!tierError && (tierData === "pilot" || tierData === "free")) {
      tier = tierData;
    } else {
      const { data: subData } = await supabase
        .from("truststack_subscriptions")
        .select("tier, status, current_period_end")
        .eq("user_id", userId)
        .in("status", ["active", "trialing"])
        .limit(1)
        .maybeSingle();

      if (subData?.tier === "pilot") {
        const end = subData.current_period_end
          ? new Date(subData.current_period_end).getTime()
          : null;
        if (!end || end > Date.now()) tier = "pilot";
      }
    }

    const fromRpc =
      !prepaidRpc.error && prepaidRpc.data !== null && prepaidRpc.data !== undefined
        ? Math.max(0, Number(prepaidRpc.data) || 0)
        : 0;
    const fromTable = Math.max(0, Number(entRes.data?.scan_credits) || 0);
    prepaidScans = Math.max(fromRpc, fromTable, prepaidScans);
  } catch {
    /* fall through */
  }

  return { tier, prepaidScans };
}

/** @deprecated Prefer fetchTrustStackEntitlements */
export async function fetchTrustStackTier(userId: string): Promise<TrustStackTier> {
  const { tier } = await fetchTrustStackEntitlements(userId);
  return tier;
}
