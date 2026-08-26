"use client";

import { Loader2 } from "lucide-react";
import type { QuotaInfo } from "@/lib/types";
import { truststackSubscribeUrl } from "@/lib/truststack";

interface ScanQuotaBannerProps {
  quota: QuotaInfo | null;
  loading?: boolean;
  proActivating?: boolean;
  onSignIn?: () => void;
  onPayForScan?: () => void;
  payForScanLoading?: boolean;
}

function CounterLine({
  count,
  detail,
}: {
  count: string;
  detail?: string;
}) {
  return (
    <div className="min-w-0 flex-1">
      <p className="scan-quota-banner__count">{count}</p>
      {detail ? <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{detail}</p> : null}
    </div>
  );
}

export function ScanQuotaBanner({
  quota,
  loading = false,
  proActivating = false,
  onSignIn,
  onPayForScan,
  payForScanLoading,
}: ScanQuotaBannerProps) {
  if (proActivating) {
    return (
      <div className="scan-quota-banner scan-quota-banner--activating" role="status" aria-live="polite">
        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-[var(--color-gold-light)]" aria-hidden />
        <div>
          <p className="scan-quota-banner__count">Activating Pilot…</p>
          <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
            Your 1 full scan per day will be ready shortly.
          </p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="scan-quota-banner scan-quota-banner--loading" role="status" aria-live="polite">
        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-mint" aria-hidden />
        <p>Loading scan balance…</p>
      </div>
    );
  }

  if (!quota || quota.premium_free_access) return null;

  const prepaid = quota.prepaid_scans ?? quota.scan_credits ?? 0;
  const hasPilot = quota.has_pilot ?? quota.tier === "pilot";
  const pilotRemaining = quota.pilot_scans_remaining ?? 0;
  const freeRemaining = quota.free_scans_remaining ?? 0;
  const freeLimit = quota.free_scans_limit ?? 1;
  const pilotHref = truststackSubscribeUrl();

  if (!quota.signed_in) {
    return (
      <div className="scan-quota-banner">
        <CounterLine
          count="Sign in to scan"
          detail="1 free preview scan per account (lifetime), then purchase a scan credit — or get Pilot."
        />
        {onSignIn && (
          <button type="button" className="scan-quota-banner__link shrink-0" onClick={onSignIn}>
            Sign in
          </button>
        )}
      </div>
    );
  }

  if (!quota.can_scan) {
    return (
      <div className="scan-quota-banner scan-quota-banner--warn">
        <CounterLine
          count={
            hasPilot
              ? "0 of 1 full scans remaining today"
              : "0 of 1 free preview scans remaining"
          }
          detail={
            hasPilot
              ? "Pilot daily scan used (doesn't stack). Purchase another full-scan credit, or come back tomorrow."
              : "Free preview used. Unlock a past report, purchase a new full-scan credit, or get Pilot."
          }
        />
        <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1">
          {onPayForScan && (
            <button
              type="button"
              className={`scan-quota-banner__link inline-flex items-center gap-1.5 ${payForScanLoading ? "animate-pulse opacity-80" : ""}`}
              onClick={() => void onPayForScan()}
              disabled={payForScanLoading}
            >
              {payForScanLoading && <Loader2 className="h-3 w-3 animate-spin" />}
              {payForScanLoading ? "Opening checkout…" : "Purchase scan credit"}
            </button>
          )}
          {!hasPilot && (
            <a href={pilotHref} className="scan-quota-banner__link">
              Get Pilot
            </a>
          )}
        </div>
      </div>
    );
  }

  // Pilot with daily slot — always surface prepaid extras when present
  if (hasPilot && pilotRemaining > 0) {
    return (
      <div className="scan-quota-banner">
        <CounterLine
          count={
            prepaid > 0
              ? `${pilotRemaining} of 1 Pilot today · +${prepaid} full-scan credit${prepaid > 1 ? "s" : ""}`
              : `${pilotRemaining} of 1 full scans remaining today`
          }
          detail={
            prepaid > 0
              ? `Pilot full report included · Credits are extra full scans (₹299 each if you buy more)`
              : `Pilot · full report included · Extra same-day scans are ₹299 each`
          }
        />
      </div>
    );
  }

  if (hasPilot && prepaid > 0) {
    return (
      <div className="scan-quota-banner">
        <CounterLine
          count={`${prepaid} paid full-scan credit${prepaid > 1 ? "s" : ""} ready`}
          detail={`Today's Pilot scan used · Full report included`}
        />
      </div>
    );
  }

  if (freeRemaining > 0 && !hasPilot) {
    return (
      <div className="scan-quota-banner">
        <CounterLine
          count={
            prepaid > 0
              ? `${freeRemaining} of ${freeLimit} free preview · +${prepaid} full-scan credit${prepaid > 1 ? "s" : ""}`
              : `${freeRemaining} of ${freeLimit} free preview scans remaining (lifetime)`
          }
          detail={`Preview scan · Unlock the full report for ₹299, or get Pilot (1 full scan/day)`}
        />
        <a href={pilotHref} className="scan-quota-banner__link shrink-0">
          Get Pilot
        </a>
      </div>
    );
  }

  if (prepaid > 0) {
    return (
      <div className="scan-quota-banner">
        <CounterLine
          count={`${prepaid} paid full-scan credit${prepaid > 1 ? "s" : ""} ready`}
          detail="Full report included with each credit"
        />
      </div>
    );
  }

  return (
    <div className="scan-quota-banner">
      <CounterLine count="Ready to scan" />
    </div>
  );
}
