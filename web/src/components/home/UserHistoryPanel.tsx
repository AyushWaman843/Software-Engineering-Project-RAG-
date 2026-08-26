"use client";

import { useCallback, useEffect, useState } from "react";
import { History, LogIn, ShieldCheck, UserPlus } from "lucide-react";
import { HistorySidebar } from "@/components/home/HistorySidebar";
import { SupabaseSetupNotice } from "@/components/home/SupabaseSetupNotice";
import { PageLoader } from "@/components/ui/PageLoader";
import { useAuth } from "@/contexts/AuthContext";
import { fetchUserScansClient } from "@/lib/supabase/scans";
import type { HistoryItem } from "@/lib/types";

function AccountRequiredPanel({
  onSignIn,
  onSignUp,
}: {
  onSignIn: () => void;
  onSignUp: () => void;
}) {
  return (
    <aside id="scan-history" className="panel h-fit min-w-0 scroll-mt-20 overflow-hidden md:scroll-mt-8">
      <header className="panel-header">
        <h2 className="flex items-center gap-2 font-display text-base font-bold tracking-tight text-[var(--color-text)]">
          <History className="h-4 w-4 text-mint" />
          Saved assessments
        </h2>
      </header>
      <div className="flex flex-col items-center px-6 py-10 text-center">
        <span className="mb-4 grid h-14 w-14 place-items-center rounded-2xl border border-mint/25 bg-mint/[0.08] text-mint-soft shadow-[0_0_28px_-8px_rgba(255,122,24,0.45)]">
          <ShieldCheck className="h-7 w-7" />
        </span>
        <p className="font-display text-base font-bold text-[var(--color-text)]">Account required</p>
        <p className="mt-2 max-w-[16rem] text-sm leading-relaxed text-[var(--color-text-muted)]">
          Sign in to save scans and view your personal assessment history across devices.
        </p>
        <div className="mt-6 flex w-full flex-col gap-2 sm:flex-row sm:justify-center">
          <button type="button" className="btn btn-primary gap-1.5 px-4 py-2 text-xs" onClick={onSignIn}>
            <LogIn className="h-3.5 w-3.5" />
            Sign in
          </button>
          <button type="button" className="btn btn-secondary gap-1.5 px-4 py-2 text-xs" onClick={onSignUp}>
            <UserPlus className="h-3.5 w-3.5" />
            Create account
          </button>
        </div>
      </div>
    </aside>
  );
}

export function UserHistoryPanel() {
  const { user, session, loading: authLoading, configured, openAuth } = useAuth();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [setupRequired, setSetupRequired] = useState(false);

  const loadHistory = useCallback(async () => {
    if (!configured || !user) {
      setItems([]);
      setSetupRequired(false);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const result = await fetchUserScansClient(user.id, session?.access_token);
      setItems(result.items);
      setSetupRequired(false);
    } catch {
      setItems([]);
      setSetupRequired(false);
    } finally {
      setLoading(false);
    }
  }, [user, configured, session?.access_token]);

  useEffect(() => {
    if (authLoading) return;
    void loadHistory();
  }, [authLoading, loadHistory]);

  useEffect(() => {
    if (!user) return undefined;
    const onRefresh = () => void loadHistory();
    window.addEventListener("scan-history-updated", onRefresh);
    window.addEventListener("supabase-setup-required", onRefresh);
    return () => {
      window.removeEventListener("scan-history-updated", onRefresh);
      window.removeEventListener("supabase-setup-required", onRefresh);
    };
  }, [loadHistory, user]);

  if (!configured) return null;

  if (authLoading || (user && loading && items.length === 0)) {
    return (
      <div className="panel overflow-hidden p-4">
        <PageLoader label="Loading history" sublabel="Fetching your saved assessments" compact />
      </div>
    );
  }

  if (!user) {
    return (
      <AccountRequiredPanel
        onSignIn={() => openAuth("signin")}
        onSignUp={() => openAuth("signup")}
      />
    );
  }

  return (
    <div id="scan-history" className="space-y-3 scroll-mt-20 md:scroll-mt-8">
      {setupRequired && <SupabaseSetupNotice />}
      <HistorySidebar
        items={items}
        title="Your saved scans"
        emptyMessage={
          setupRequired
            ? "After you run the Supabase schema, new scans will appear here."
            : "No saved assessments yet. Run a scan while signed in and it will appear here."
        }
      />
    </div>
  );
}
