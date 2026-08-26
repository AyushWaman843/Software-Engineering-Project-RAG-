export const CONSENT_STORAGE_KEY = "anix_cookie_consent";
export const CONSENT_VERSION = 1;

export type CookieConsentPreferences = {
  version: number;
  decidedAt: string;
  functional: boolean;
  analytics: boolean;
};

export type CookieConsentView = {
  hasDecided: boolean;
  functional: boolean;
  analytics: boolean;
};

const FUNCTIONAL_STORAGE_PREFIX = "dpdp:remediation:";

export function readConsent(): CookieConsentView {
  if (typeof window === "undefined") {
    return { hasDecided: false, functional: false, analytics: false };
  }

  try {
    const raw = localStorage.getItem(CONSENT_STORAGE_KEY);
    if (!raw) {
      return { hasDecided: false, functional: false, analytics: false };
    }

    const parsed = JSON.parse(raw) as CookieConsentPreferences;
    if (parsed.version !== CONSENT_VERSION) {
      return { hasDecided: false, functional: false, analytics: false };
    }

    return {
      hasDecided: true,
      functional: Boolean(parsed.functional),
      analytics: Boolean(parsed.analytics),
    };
  } catch {
    return { hasDecided: false, functional: false, analytics: false };
  }
}

export function writeConsent(functional: boolean, analytics: boolean): CookieConsentPreferences {
  const record: CookieConsentPreferences = {
    version: CONSENT_VERSION,
    decidedAt: new Date().toISOString(),
    functional,
    analytics,
  };

  localStorage.setItem(CONSENT_STORAGE_KEY, JSON.stringify(record));
  return record;
}

export function clearFunctionalStorage(): void {
  if (typeof window === "undefined") return;

  const keysToRemove: string[] = [];
  for (let i = 0; i < localStorage.length; i += 1) {
    const key = localStorage.key(i);
    if (key?.startsWith(FUNCTIONAL_STORAGE_PREFIX)) {
      keysToRemove.push(key);
    }
  }
  keysToRemove.forEach((key) => localStorage.removeItem(key));
}

export function applyConsentSideEffects(preferences: Pick<CookieConsentView, "functional" | "analytics">): void {
  if (!preferences.functional) {
    clearFunctionalStorage();
  }

  if (preferences.analytics) {
    initAnalytics();
  }
}

/** Placeholder for future Google Analytics — only runs when analytics consent is granted. */
export function initAnalytics(): void {
  if (typeof window === "undefined") return;
  if (!process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID) return;
  // Wire Google Analytics here when NEXT_PUBLIC_GA_MEASUREMENT_ID is configured.
}
