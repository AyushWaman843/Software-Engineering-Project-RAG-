"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  applyConsentSideEffects,
  readConsent,
  writeConsent,
  type CookieConsentView,
} from "@/lib/cookies/consent";

interface CookieConsentContextValue extends CookieConsentView {
  ready: boolean;
  settingsOpen: boolean;
  openCookieSettings: () => void;
  closeCookieSettings: () => void;
  acceptAll: () => void;
  declineNonEssential: () => void;
  savePreferences: (functional: boolean, analytics: boolean) => void;
}

const CookieConsentContext = createContext<CookieConsentContextValue | null>(null);

export function CookieConsentProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [consent, setConsent] = useState<CookieConsentView>({
    hasDecided: false,
    functional: false,
    analytics: false,
  });

  useEffect(() => {
    const stored = readConsent();
    if (stored.hasDecided) {
      setConsent(stored);
      applyConsentSideEffects(stored);
    } else {
      // Auto-accept silently — no banner shown. Essential + functional accepted,
      // analytics off by default (privacy-friendly).
      writeConsent(true, false);
      const auto = { hasDecided: true, functional: true, analytics: false };
      setConsent(auto);
      applyConsentSideEffects(auto);
    }
    setReady(true);
  }, []);

  const persist = useCallback((functional: boolean, analytics: boolean) => {
    writeConsent(functional, analytics);
    const next = { hasDecided: true, functional, analytics };
    setConsent(next);
    applyConsentSideEffects(next);
    setSettingsOpen(false);
  }, []);

  const acceptAll = useCallback(() => persist(true, true), [persist]);
  const declineNonEssential = useCallback(() => persist(false, false), [persist]);
  const savePreferences = useCallback(
    (functional: boolean, analytics: boolean) => persist(functional, analytics),
    [persist],
  );

  const value = useMemo<CookieConsentContextValue>(
    () => ({
      ...consent,
      ready,
      settingsOpen,
      openCookieSettings: () => setSettingsOpen(true),
      closeCookieSettings: () => setSettingsOpen(false),
      acceptAll,
      declineNonEssential,
      savePreferences,
    }),
    [consent, ready, settingsOpen, acceptAll, declineNonEssential, savePreferences],
  );

  return (
    <CookieConsentContext.Provider value={value}>{children}</CookieConsentContext.Provider>
  );
}

export function useCookieConsent(): CookieConsentContextValue {
  const ctx = useContext(CookieConsentContext);
  if (!ctx) {
    throw new Error("useCookieConsent must be used within CookieConsentProvider");
  }
  return ctx;
}
