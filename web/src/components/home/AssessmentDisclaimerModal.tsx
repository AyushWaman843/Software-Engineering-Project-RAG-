"use client";

import { useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Scale, X } from "lucide-react";

interface AssessmentDisclaimerModalProps {
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function AssessmentDisclaimerModal({
  open,
  onCancel,
  onConfirm,
}: AssessmentDisclaimerModalProps) {
  const [mounted, setMounted] = useState(false);
  const titleId = useId();

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) return;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onCancel]);

  if (!mounted) return null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="assessment-disclaimer-modal"
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
            aria-label="Close disclaimer"
            onClick={onCancel}
          />

          <motion.div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="assessment-disclaimer-card"
            initial={{ opacity: 0, scale: 0.96, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 8 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            <button
              type="button"
              className="assessment-disclaimer-close"
              aria-label="Close"
              onClick={onCancel}
            >
              <X className="h-4 w-4" />
            </button>

            <div className="assessment-disclaimer-icon" aria-hidden>
              <Scale className="h-5 w-5" />
            </div>

            <h2 id={titleId} className="assessment-disclaimer-title">
              Indicative assessment only
            </h2>

            <p className="assessment-disclaimer-text">
              This automated scan is for informational purposes only and does{" "}
              <strong>not</strong> constitute legal advice. Results are indicative — for
              expert-verified compliance analysis,{" "}
              <a
                href="mailto:contact@dpdpscanner.in?subject=DPDP%20Manual%20Compliance%20Review"
                className="font-semibold text-mint-soft underline decoration-mint/40 underline-offset-2 hover:text-mint"
              >
                contact us
              </a>{" "}
              for a manual review, or consult a qualified attorney.
            </p>

            <div className="assessment-disclaimer-actions">
              <button type="button" className="btn btn-secondary assessment-disclaimer-btn" onClick={onCancel}>
                Cancel
              </button>
              <button type="button" className="btn btn-primary assessment-disclaimer-btn" onClick={onConfirm}>
                I understand, continue
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
