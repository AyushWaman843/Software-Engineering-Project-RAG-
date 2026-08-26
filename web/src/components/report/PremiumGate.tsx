"use client";

import { Crown, Lock, Sparkles, Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { usePremiumCheckout } from "@/hooks/usePremiumCheckout";

interface PremiumGateProps {
  reportId: string;
  priceDisplay?: number;
  currency?: string;
  title?: string;
  description?: string;
  skeletonRows?: number;
  className?: string;
}

export function PremiumGate({
  reportId,
  title = "Full Report",
  description = "Unlock all indicators, AI analysis, policy excerpts, remediation plan, and a professional PDF for this assessment.",
  skeletonRows = 4,
  className = "",
}: PremiumGateProps) {
  const { user, openAuth } = useAuth();
  const { checkout, loading, verifying, error, SummaryModal } = usePremiumCheckout(reportId);

  async function handleUnlock() {
    if (!user) {
      openAuth("signin");
      return;
    }
    await checkout();
  }

  return (
    <div className={`premium-gate ${className}`}>
      <div className="premium-gate__blur" aria-hidden>
        <div className="space-y-3 p-6">
          {Array.from({ length: skeletonRows }).map((_, i) => (
            <div
              key={i}
              className="h-14 rounded-xl bg-white/[0.04]"
              style={{ opacity: 1 - i * 0.15 }}
            />
          ))}
        </div>
      </div>
      <div className="premium-gate__overlay">
        <div className="premium-gate__content">
          <div className="premium-gate__badge" aria-hidden>
            <Sparkles className="h-3 w-3" />
            One-Time Report
          </div>
          <div className="premium-gate__icon" aria-hidden>
            <Crown className="h-8 w-8" strokeWidth={1.5} />
            <Lock className="premium-gate__lock h-4 w-4" />
          </div>
          <div className="premium-gate__copy">
            <h3 className="premium-gate__title">{title}</h3>
            <p className="premium-gate__desc">{description}</p>
          </div>
          <div className="premium-gate__actions">
            <button
              type="button"
              className={`btn btn-premium gap-2 ${loading ? 'animate-pulse opacity-80' : ''}`}
              onClick={() => void handleUnlock()}
              disabled={loading}
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Crown className="h-4 w-4" />
              )}
              {loading ? (verifying ? "Verifying payment…" : "Opening checkout…") : "Unlock full report"}
            </button>
            {error && <p className="premium-gate__hint text-rose-soft">{error}</p>}
            <p className="premium-gate__hint">
              One-time unlock per report · Permanent access · Secure via Razorpay
            </p>
          </div>
        </div>
      </div>
      {SummaryModal}
    </div>
  );
}
