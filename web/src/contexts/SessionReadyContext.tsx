"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "@/contexts/AuthContext";
import { fetchQuotaClient } from "@/lib/quota";
import { fetchTrustStackEntitlements } from "@/lib/supabase/tier";
import type { QuotaInfo } from "@/lib/types";

interface RefreshQuotaOptions {
  /** When false, refresh in the background without blocking the workspace gate. Default: true on first load only. */
  blocking?: boolean;
}

interface SessionReadyContextValue {
  ready: boolean;
  authLoading: boolean;
  quotaLoading: boolean;
  proActivating: boolean;
  quota: QuotaInfo | null;
  /** TrustStack tier from Supabase (same source as TrustStack header). */
  truststackTier: "free" | "pilot";
  refreshQuota: (options?: RefreshQuotaOptions) => Promise<void>;
}

const SessionReadyContext = createContext<SessionReadyContextValue | null>(null);

function mergeEntitlementsIntoQuota(
  snap: QuotaInfo | null,
  tier: "free" | "pilot",
  prepaidFromSupabase: number,
): QuotaInfo | null {
  const prepaidFromSnap = snap?.prepaid_scans ?? snap?.scan_credits ?? 0;
  const prepaid = Math.max(prepaidFromSnap, prepaidFromSupabase);

  if (!snap) {
    if (tier !== "pilot" && prepaid <= 0) return null;
    return {
      signed_in: true,
      tier: tier === "pilot" ? "pilot" : "free",
      free_scans_limit: 1,
      free_scans_used: 0,
      free_scans_remaining: tier === "pilot" ? 0 : 1,
      prepaid_scans: prepaid,
      scan_credits: prepaid,
      pilot_scans_remaining: tier === "pilot" ? 1 : 0,
      has_pilot: tier === "pilot",
      has_pro: false,
      can_scan: tier === "pilot" || prepaid > 0,
      requires_sign_in: false,
      message:
        tier === "pilot"
          ? prepaid > 0
            ? `Pilot: 1 full scan today · ${prepaid} extra credit${prepaid > 1 ? "s" : ""}.`
            : "Pilot: 1 full scan remaining today."
          : prepaid > 0
            ? `${prepaid} paid full-scan credit${prepaid > 1 ? "s" : ""} ready.`
            : "1 free preview scan remaining.",
    };
  }

  const hasPilot = tier === "pilot" || Boolean(snap.has_pilot) || snap.tier === "pilot";
  const pilotRemaining = hasPilot ? (snap.pilot_scans_remaining ?? 1) : 0;

  return {
    ...snap,
    signed_in: true,
    tier: hasPilot ? "pilot" : snap.tier ?? "free",
    has_pilot: hasPilot,
    pilot_scans_remaining: pilotRemaining,
    prepaid_scans: prepaid,
    scan_credits: prepaid,
    can_scan: Boolean(snap.can_scan) || hasPilot || prepaid > 0,
    requires_sign_in: false,
    message:
      hasPilot && prepaid > 0
        ? `Pilot: ${pilotRemaining} of 1 today · ${prepaid} extra full-scan credit${prepaid > 1 ? "s" : ""}.`
        : hasPilot
          ? snap.message?.includes("Pilot")
            ? snap.message
            : "Pilot: 1 full scan remaining today."
          : prepaid > 0
            ? `${prepaid} paid full-scan credit${prepaid > 1 ? "s" : ""} ready.`
            : snap.message,
  };
}

export function SessionReadyProvider({ children }: { children: ReactNode }) {
  const { user, session, loading: authLoading } = useAuth();
  const [quota, setQuota] = useState<QuotaInfo | null>(null);
  const [truststackTier, setTruststackTier] = useState<"free" | "pilot">("free");
  const [quotaLoading, setQuotaLoading] = useState(true);
  const [proActivating, setProActivating] = useState(false);
  const hasLoadedQuota = useRef(false);
  const lastUser = useRef(user?.id);

  const refreshQuota = useCallback(
    async (options?: RefreshQuotaOptions) => {
      const blocking = options?.blocking ?? !hasLoadedQuota.current;
      if (blocking) setQuotaLoading(true);

      try {
        const [snap, ents] = await Promise.all([
          fetchQuotaClient(user?.id, session?.access_token),
          user?.id
            ? fetchTrustStackEntitlements(user.id, session?.access_token)
            : Promise.resolve({ tier: "free" as const, prepaidScans: 0 }),
        ]);
        setTruststackTier(ents.tier);
        setQuota(mergeEntitlementsIntoQuota(snap, ents.tier, ents.prepaidScans));
        hasLoadedQuota.current = true;
      } finally {
        if (blocking) setQuotaLoading(false);
      }
    },
    [user?.id, session?.access_token],
  );

  useEffect(() => {
    if (authLoading) {
      setQuotaLoading(true);
      return;
    }

    const userChanged = lastUser.current !== user?.id;
    lastUser.current = user?.id;

    void refreshQuota({ blocking: !hasLoadedQuota.current || userChanged });
  }, [authLoading, user?.id, refreshQuota]);

  useEffect(() => {
    function onPremiumUpdated() {
      if (!authLoading) void refreshQuota({ blocking: false });
    }
    function onProActivationStarted() {
      setProActivating(true);
    }
    function onProActivationComplete() {
      setProActivating(false);
    }
    window.addEventListener("premium-status-updated", onPremiumUpdated);
    window.addEventListener("pro-activation-started", onProActivationStarted);
    window.addEventListener("pro-activation-complete", onProActivationComplete);
    return () => {
      window.removeEventListener("premium-status-updated", onPremiumUpdated);
      window.removeEventListener("pro-activation-started", onProActivationStarted);
      window.removeEventListener("pro-activation-complete", onProActivationComplete);
    };
  }, [authLoading, refreshQuota]);

  const ready = !authLoading && !quotaLoading;

  const value = useMemo(
    () => ({
      ready,
      authLoading,
      quotaLoading,
      proActivating,
      quota,
      truststackTier,
      refreshQuota,
    }),
    [ready, authLoading, quotaLoading, proActivating, quota, truststackTier, refreshQuota],
  );

  return <SessionReadyContext.Provider value={value}>{children}</SessionReadyContext.Provider>;
}

export function useSessionReady() {
  const ctx = useContext(SessionReadyContext);
  if (!ctx) throw new Error("useSessionReady must be used within SessionReadyProvider");
  return ctx;
}
