"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import type { ConfidenceLabel } from "@/components/report/ConfidenceBadge";

interface ConfidenceUpsellBannerProps {
  reportId: string;
  label: "medium" | "low";
}

const BANNER_STYLES: Record<
  "medium" | "low",
  { box: string; text: string }
> = {
  medium: {
    box: "border-amber-500/35 bg-amber-500/10",
    text: "text-amber-100/90",
  },
  low: {
    box: "border-rose-500/35 bg-rose-500/10",
    text: "text-rose-100/90",
  },
};

function storageKey(reportId: string) {
  return `confidence-upsell-dismissed:${reportId}`;
}

/**
 * Manual review upsell for medium/low confidence scans.
 * Dismissal persists in localStorage for the report id.
 */
export function ConfidenceUpsellBanner({ reportId, label }: ConfidenceUpsellBannerProps) {
  const [dismissed, setDismissed] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      setDismissed(localStorage.getItem(storageKey(reportId)) === "1");
    } catch {
      setDismissed(false);
    }
    setReady(true);
  }, [reportId]);

  if (!ready || dismissed) return null;

  const styles = BANNER_STYLES[label];
  const levelWord = label === "medium" ? "medium" : "low";

  function dismiss() {
    setDismissed(true);
    try {
      localStorage.setItem(storageKey(reportId), "1");
    } catch {
      /* session-only if storage blocked */
    }
  }

  return (
    <div
      className={`relative flex gap-4 rounded-xl border px-4 py-4 pr-12 md:px-5 ${styles.box}`}
      role="status"
    >
      <div className={`text-sm leading-relaxed ${styles.text}`}>
        This assessment was made with <strong>{levelWord}</strong> confidence. For a deeper,
        expert-verified analysis, contact us for a manual compliance review.{" "}
        <a
          href="mailto:contact@dpdpscanner.in?subject=DPDP%20Manual%20Compliance%20Review"
          className="font-semibold text-white underline decoration-white/40 underline-offset-2 hover:decoration-white"
        >
          Contact Us
        </a>
      </div>
      <button
        type="button"
        onClick={dismiss}
        className="absolute right-3 top-3 rounded-lg p-1.5 text-white/70 transition-colors hover:bg-white/10 hover:text-white"
        aria-label="Dismiss banner"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
