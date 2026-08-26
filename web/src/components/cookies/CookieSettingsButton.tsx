"use client";

import { useCookieConsent } from "@/contexts/CookieConsentContext";

interface CookieSettingsButtonProps {
  className?: string;
}

export function CookieSettingsButton({ className }: CookieSettingsButtonProps) {
  const { openCookieSettings } = useCookieConsent();

  return (
    <button
      type="button"
      className={className ?? "text-[var(--color-text-muted)] transition-colors hover:text-mint-soft"}
      onClick={openCookieSettings}
    >
      Cookie Settings
    </button>
  );
}
