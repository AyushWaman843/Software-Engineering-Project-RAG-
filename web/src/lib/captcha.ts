/**
 * Cloudflare Turnstile helpers (client + shared types).
 */

export const TURNSTILE_SITE_KEY =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY?.trim()) || "";

export function turnstileEnabled(): boolean {
  return Boolean(TURNSTILE_SITE_KEY);
}

declare global {
  interface Window {
    turnstile?: {
      render: (
        container: HTMLElement | string,
        options: {
          sitekey: string;
          callback?: (token: string) => void;
          "expired-callback"?: () => void;
          "error-callback"?: () => void;
          theme?: "light" | "dark" | "auto";
          size?: "normal" | "compact" | "flexible";
        },
      ) => string;
      reset: (widgetId?: string) => void;
      remove: (widgetId?: string) => void;
    };
  }
}
