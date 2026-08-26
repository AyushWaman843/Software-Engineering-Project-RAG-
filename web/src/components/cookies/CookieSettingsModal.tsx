"use client";

import { useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Cookie, ExternalLink, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { useCookieConsent } from "@/contexts/CookieConsentContext";

interface CookieToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}

function CookieToggle({ checked, onChange, label }: CookieToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={`cookie-toggle${checked ? " cookie-toggle--on" : ""}`}
      onClick={() => onChange(!checked)}
    >
      <span className="cookie-toggle__knob" aria-hidden />
    </button>
  );
}

export function CookieSettingsModal() {
  const {
    settingsOpen,
    closeCookieSettings,
    functional,
    analytics,
    savePreferences,
    acceptAll,
    hasDecided,
  } = useCookieConsent();
  const [mounted, setMounted] = useState(false);
  const [functionalEnabled, setFunctionalEnabled] = useState(functional);
  const [analyticsEnabled, setAnalyticsEnabled] = useState(analytics);
  const titleId = useId();

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!settingsOpen) return;
    setFunctionalEnabled(functional);
    setAnalyticsEnabled(analytics);
  }, [settingsOpen, functional, analytics]);

  useEffect(() => {
    if (!settingsOpen) return;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeCookieSettings();
    };
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [settingsOpen, closeCookieSettings]);

  if (!mounted) return null;

  const saveLabel = hasDecided ? "Save preferences" : "Confirm preferences";

  return createPortal(
    <AnimatePresence>
      {settingsOpen && (
        <motion.div
          key="cookie-settings-modal"
          className="cookie-settings-overlay"
          role="presentation"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <button
            type="button"
            className="cookie-settings-backdrop"
            aria-label="Close cookie settings"
            onClick={closeCookieSettings}
          />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="cookie-settings-card"
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 6 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="cookie-settings-card__glow" aria-hidden />

            <button
              type="button"
              className="cookie-settings-close"
              aria-label="Close"
              onClick={closeCookieSettings}
            >
              <X className="h-4 w-4" />
            </button>

            <div className="cookie-settings-brand">
              <span className="cookie-settings-brand__icon">
                <Cookie className="h-5 w-5" />
              </span>
              <div>
                <p className="cookie-settings-brand__eyebrow">Privacy</p>
                <h2 id={titleId} className="cookie-settings-brand__title">
                  Cookie Settings
                </h2>
              </div>
            </div>

            <p className="cookie-settings-intro">
              Manage optional cookies below. Strictly necessary cookies stay active so authentication,
              security, and the scanner continue to work.
            </p>

            <div className="cookie-settings-list">
              <div className="cookie-settings-row cookie-settings-row--locked">
                <div className="cookie-settings-row__copy">
                  <p className="cookie-settings-row__title">Strictly Necessary</p>
                  <p className="cookie-settings-row__desc">
                    Session, security, and authentication cookies required for the scanner.
                  </p>
                </div>
                <span className="cookie-settings-badge">Always on</span>
              </div>

              <div className="cookie-settings-row cookie-settings-row--interactive">
                <div className="cookie-settings-row__copy">
                  <p className="cookie-settings-row__title">Functional</p>
                  <p className="cookie-settings-row__desc">
                    Remember preferences such as remediation checklist progress on reports.
                  </p>
                </div>
                <CookieToggle
                  label="Functional cookies"
                  checked={functionalEnabled}
                  onChange={setFunctionalEnabled}
                />
              </div>

              <div className="cookie-settings-row cookie-settings-row--interactive">
                <div className="cookie-settings-row__copy">
                  <p className="cookie-settings-row__title">Analytics</p>
                  <p className="cookie-settings-row__desc">
                    Aggregated usage insights such as page views and traffic sources.
                  </p>
                </div>
                <CookieToggle
                  label="Analytics cookies"
                  checked={analyticsEnabled}
                  onChange={setAnalyticsEnabled}
                />
              </div>

              <div className="cookie-settings-row cookie-settings-row--locked">
                <div className="cookie-settings-row__copy">
                  <p className="cookie-settings-row__title">Marketing</p>
                  <p className="cookie-settings-row__desc">
                    We do not currently use marketing cookies.
                  </p>
                </div>
                <span className="cookie-settings-badge cookie-settings-badge--muted">Off</span>
              </div>
            </div>

            <button
              type="button"
              className="btn btn-secondary cookie-settings-accept-all"
              onClick={acceptAll}
            >
              Accept all cookies
            </button>

            <div className="cookie-settings-footer">
              <div className="cookie-settings-footer__actions">
                <button
                  type="button"
                  className="btn btn-secondary cookie-settings-footer__btn"
                  onClick={closeCookieSettings}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-primary cookie-settings-footer__btn"
                  onClick={() => savePreferences(functionalEnabled, analyticsEnabled)}
                >
                  <Check className="h-4 w-4" />
                  {saveLabel}
                </button>
              </div>

              <p className="cookie-settings-footnote">
                <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-mint-soft" />
                <span>
                  Your choices are stored locally on this device.{" "}
                  <Link href="/cookies" className="cookie-settings-footnote__link" onClick={closeCookieSettings}>
                    Cookie Policy
                    <ExternalLink className="h-3 w-3" aria-hidden />
                  </Link>
                </span>
              </p>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
