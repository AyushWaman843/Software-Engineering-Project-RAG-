"use client";

import { Crown, Download, Lock, Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { clientApiBase } from "@/lib/api";
import { usePremiumCheckout } from "@/hooks/usePremiumCheckout";

interface PremiumPdfButtonProps {
  reportId: string;
  unlocked?: boolean;
}

export function PremiumPdfButton({ reportId, unlocked = false }: PremiumPdfButtonProps) {
  const { user, openAuth } = useAuth();
  const { checkout, loading, error, SummaryModal } = usePremiumCheckout(reportId);

  if (unlocked) {
    return (
      <a
        href={`${clientApiBase}/report/${reportId}/pdf`}
        className="btn btn-primary group gap-2"
      >
        <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/40 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
        <Download className="h-4 w-4" />
        Download PDF Report
      </a>
    );
  }

  async function handleClick() {
    if (!user) {
      openAuth("signin");
      return;
    }
    await checkout();
  }

  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        className={`btn btn-premium group gap-2.5 ${loading ? 'animate-pulse opacity-80' : ''}`}
        onClick={() => void handleClick()}
        disabled={loading}
        title="Unlock premium to download PDF report"
      >
        <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-amber-100/30 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin opacity-90" />
        ) : (
          <Download className="h-4 w-4 opacity-90" />
        )}
        <span>{loading ? "Opening checkout…" : "Unlock full report"}</span>
        <span className="premium-pill">
          <Crown className="h-3 w-3" />
          Premium
        </span>
        <Lock className="ml-0.5 h-3.5 w-3.5 opacity-70" aria-hidden />
      </button>
      {error && <p className="text-xs text-rose-soft">{error}</p>}
      {SummaryModal}
    </div>
  );
}
