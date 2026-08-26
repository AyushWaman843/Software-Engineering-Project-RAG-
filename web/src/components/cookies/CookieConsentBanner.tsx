"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Cookie } from "lucide-react";
import Link from "next/link";
import { useCookieConsent } from "@/contexts/CookieConsentContext";

export function CookieConsentBanner() {
  const { ready, hasDecided, acceptAll, declineNonEssential, openCookieSettings } =
    useCookieConsent();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const visible = mounted && ready && !hasDecided;

  if (!mounted) return null;

  return createPortal(
    <AnimatePresence>
      {visible && (
        <motion.aside
          key="cookie-consent-banner"
          className="cookie-consent-banner"
          role="dialog"
          aria-labelledby="cookie-consent-title"
          aria-describedby="cookie-consent-desc"
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 24 }}
          transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="cookie-consent-banner__inner">
            <div className="cookie-consent-banner__icon" aria-hidden>
              <Cookie className="h-5 w-5" />
            </div>
            <div className="cookie-consent-banner__content">
              <h2 id="cookie-consent-title" className="cookie-consent-banner__title">
                We use cookies
              </h2>
              <p id="cookie-consent-desc" className="cookie-consent-banner__text">
                We use strictly necessary cookies to run the scanner. With your permission, we also
                use functional and analytics cookies. You can accept or decline non‑essential cookies
                now, or manage choices anytime via{" "}
                <button type="button" className="cookie-consent-inline-link" onClick={openCookieSettings}>
                  Cookie Settings
                </button>
                . See our{" "}
                <Link href="/cookies" className="cookie-consent-inline-link">
                  Cookie Policy
                </Link>
                .
              </p>
            </div>
            <div className="cookie-consent-banner__actions">
              <button type="button" className="btn btn-primary cookie-consent-btn" onClick={acceptAll}>
                Accept all
              </button>
              <button
                type="button"
                className="btn btn-secondary cookie-consent-btn"
                onClick={declineNonEssential}
              >
                Decline non‑essential
              </button>
              <button
                type="button"
                className="btn cookie-consent-btn-text"
                onClick={openCookieSettings}
              >
                Cookie Settings
              </button>
            </div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>,
    document.body,
  );
}
