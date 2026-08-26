"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { useSessionReady } from "@/contexts/SessionReadyContext";
import { clientApiBase } from "@/lib/api";
import { fetchNavPremiumStatus } from "@/lib/quota";
import type { AppMeta } from "@/lib/types";

/** Whether user has Pilot / paid access (gold nav badge instead of Get Pilot). */
export function usePremiumNavStatus(): boolean {
  const { user, session, loading: authLoading } = useAuth();
  const { quota, truststackTier } = useSessionReady();
  const pathname = usePathname();
  const reportId = pathname.match(/^\/report\/([^/]+)/)?.[1];
  const [isPremium, setIsPremium] = useState(false);
  const accessToken = session?.access_token;

  const hasPilotFromQuota =
    truststackTier === "pilot" ||
    Boolean(quota?.has_pilot) ||
    quota?.tier === "pilot";

  useEffect(() => {
    if (authLoading) return;

    let cancelled = false;

    async function load() {
      try {
        const metaRes = await fetch(`${clientApiBase}/meta`, { credentials: "include" });
        const meta = (metaRes.ok ? await metaRes.json() : null) as AppMeta | null;

        if (meta?.premium_free_access || meta?.premium_enabled === false) {
          if (!cancelled) setIsPremium(true);
          return;
        }

        const premium = await fetchNavPremiumStatus(user?.id, reportId, accessToken);
        if (!cancelled) setIsPremium(premium);
      } catch {
        if (!cancelled) setIsPremium(false);
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [authLoading, user?.id, reportId, accessToken]);

  // Re-check after premium unlock (checkout reloads page; this covers soft updates).
  useEffect(() => {
    function onPremiumUpdated() {
      void fetchNavPremiumStatus(user?.id, reportId, accessToken).then(setIsPremium);
    }
    window.addEventListener("premium-status-updated", onPremiumUpdated);
    return () => window.removeEventListener("premium-status-updated", onPremiumUpdated);
  }, [user?.id, reportId, accessToken]);

  return isPremium || hasPilotFromQuota;
}
