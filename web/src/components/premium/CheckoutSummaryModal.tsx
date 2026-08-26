"use client";

import { useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Crown, Loader2, ShieldCheck, X } from "lucide-react";

export interface CheckoutSummaryData {
  checkout_title: string;
  checkout_subtitle?: string;
  checkout_includes: string[];
  price_display?: number;
  original_price_display?: number;
  discount_percent?: number;
  currency?: string;
  description?: string;
}

interface CheckoutSummaryModalProps {
  open: boolean;
  data: CheckoutSummaryData | null;
  loading?: boolean;
  verifying?: boolean;
  verifyingMessage?: string;
  error?: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}

/** What the customer pays for — shown before Razorpay opens. */
export function CheckoutSummaryModal({
  open,
  data,
  loading = false,
  verifying = false,
  verifyingMessage = "Confirming your purchase…",
  error = null,
  onCancel,
  onConfirm,
}: CheckoutSummaryModalProps) {
  const [mounted, setMounted] = useState(false);
  const titleId = useId();
  const busy = loading || verifying;

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) return;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, busy, onCancel]);

  if (!mounted || !data) return null;

  const isSubscription =
    data.checkout_title.toLowerCase().includes("pro") ||
    Boolean(data.discount_percent);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="checkout-summary-modal"
          className="assessment-disclaimer-overlay"
          role="presentation"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
        >
          <button
            type="button"
            className="assessment-disclaimer-backdrop"
            aria-label="Close"
            onClick={busy ? undefined : onCancel}
            disabled={busy}
          />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-busy={busy}
            className="assessment-disclaimer-card max-w-md"
            initial={{ opacity: 0, scale: 0.96, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 8 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            {!verifying && (
              <button
                type="button"
                className="assessment-disclaimer-close"
                aria-label="Close"
                onClick={onCancel}
                disabled={busy}
              >
                <X className="h-4 w-4" />
              </button>
            )}

            {verifying ? (
              <>
                <div
                  className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-mint/15"
                  aria-hidden
                >
                  <Check className="h-7 w-7 text-mint" />
                </div>
                <h2 id={titleId} className="assessment-disclaimer-title">
                  Payment received
                </h2>
                <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                  Setting up your {isSubscription ? "Pilot subscription" : "purchase"}. This usually takes a few
                  seconds — please don&apos;t close this page.
                </p>

                <div className="checkout-activation-steps mt-6" role="status" aria-live="polite">
                  <div className="checkout-activation-step checkout-activation-step--done">
                    <Check className="h-4 w-4 shrink-0" aria-hidden />
                    <span>Payment confirmed</span>
                  </div>
                  <div className="checkout-activation-step checkout-activation-step--active">
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden />
                    <span>{verifyingMessage}</span>
                  </div>
                  <div className="checkout-activation-step checkout-activation-step--pending">
                    <span className="checkout-activation-dot" aria-hidden />
                    <span>Updating your account</span>
                  </div>
                </div>
              </>
            ) : (
              <>
                <div className="assessment-disclaimer-icon" aria-hidden>
                  <Crown className="h-5 w-5" />
                </div>

                <h2 id={titleId} className="assessment-disclaimer-title">
                  {data.checkout_title}
                </h2>
                {data.checkout_subtitle && (
                  <p className="mt-1 text-sm text-[var(--color-text-muted)]">{data.checkout_subtitle}</p>
                )}

                <p className="mt-4 text-xs font-bold uppercase tracking-[0.16em] text-[var(--color-text-faint)]">
                  {isSubscription ? "Your subscription includes" : "This purchase includes"}
                </p>

                <ul className="mt-3 space-y-2.5 text-left text-sm text-[var(--color-text-muted)]">
                  {data.checkout_includes.map((item, index) => (
                    <li key={`${item}-${index}`} className="flex gap-2.5">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-mint-soft" aria-hidden />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>

                <p className="mt-4 flex items-start gap-2 rounded-lg border border-border-light bg-white/[0.03] px-3 py-2.5 text-xs leading-relaxed text-[var(--color-text-muted)]">
                  <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-mint-soft" aria-hidden />
                  <span>
                    Next you&apos;ll complete payment securely on Razorpay. The same summary appears in the
                    payment description.
                  </span>
                </p>

                <div className="assessment-disclaimer-actions mt-6">
                  {error && (
                    <p className="mb-3 w-full text-center text-sm text-rose-soft" role="alert">
                      {error}
                    </p>
                  )}
                  <button
                    type="button"
                    className={`btn btn-secondary assessment-disclaimer-btn ${loading ? "opacity-50" : ""}`}
                    onClick={onCancel}
                    disabled={loading}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className={`btn btn-premium assessment-disclaimer-btn gap-2 ${loading ? "opacity-80" : ""}`}
                    onClick={onConfirm}
                    disabled={loading}
                  >
                    {loading ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Crown className="h-4 w-4" />
                    )}
                    {loading
                      ? "Opening Razorpay…"
                      : isSubscription
                        ? "Continue to secure checkout"
                        : "Continue to secure checkout"}
                  </button>
                </div>
              </>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
