"use client";

import { Crown } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useSessionReady } from "@/contexts/SessionReadyContext";
import { truststackSubscribeUrl } from "@/lib/truststack";

interface GetPilotButtonProps {
  isPremium?: boolean;
}

function accountLabel(user: { email?: string | null; user_metadata?: Record<string, unknown> }): string {
  const metaName =
    (typeof user.user_metadata?.full_name === "string" && user.user_metadata.full_name) ||
    (typeof user.user_metadata?.name === "string" && user.user_metadata.name) ||
    "";
  if (metaName.trim()) return metaName.trim();
  if (user.email) return user.email.split("@")[0] || user.email;
  return "Account";
}

/** Signed-in: email/name + active plan. */
export function GetPilotButton({ isPremium = false }: GetPilotButtonProps) {
  const { user } = useAuth();
  const { quota, truststackTier } = useSessionReady();

  const hasPilot =
    isPremium ||
    truststackTier === "pilot" ||
    Boolean(quota?.has_pilot) ||
    quota?.tier === "pilot";
  const planLabel = hasPilot ? "Pilot active" : "Free plan";

  if (user) {
    const label = accountLabel(user);
    return (
      <div
        className="flex min-w-0 max-w-[220px] flex-col items-end leading-tight"
        title={`${label} · ${planLabel}`}
      >
        <span className="truncate text-xs font-semibold text-[var(--color-text)]">{label}</span>
        <span
          className={`mt-0.5 text-[0.65rem] font-medium uppercase tracking-[0.12em] ${
            hasPilot ? "text-[var(--color-gold-light)]" : "text-[var(--color-text-faint)]"
          }`}
        >
          {planLabel}
        </span>
        {!hasPilot && (
          <a
            href={truststackSubscribeUrl()}
            className="mt-0.5 text-[0.65rem] font-semibold text-mint-soft underline-offset-2 hover:text-mint hover:underline"
          >
            Get Pilot
          </a>
        )}
      </div>
    );
  }

  return (
    <a
      href={truststackSubscribeUrl()}
      className="premium-tier-btn"
      aria-label="Get Pilot on TrustStack"
      title="Get Pilot"
    >
      <Crown className="h-4 w-4" strokeWidth={1.75} />
      <span className="hidden sm:inline">Get Pilot</span>
    </a>
  );
}
