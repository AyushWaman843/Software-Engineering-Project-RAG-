/** Session key for the TrustStack page to return to from "Back to Website". */
const STORAGE_KEY = "anix_truststack_return_url";

/** Same-origin TrustStack paths only — never bounce into the scanner itself. */
export function isSafeWebsiteReturnPath(path: string): boolean {
  if (!path.startsWith("/") || path.startsWith("//")) return false;
  if (path === "/scanner" || path.startsWith("/scanner/")) return false;
  return true;
}

export function captureWebsiteReturnUrl(fromParam: string | null | undefined): void {
  if (typeof window === "undefined") return;

  if (fromParam) {
    let decoded = fromParam;
    try {
      decoded = decodeURIComponent(fromParam);
    } catch {
      /* use raw */
    }
    if (isSafeWebsiteReturnPath(decoded)) {
      sessionStorage.setItem(STORAGE_KEY, decoded);
      return;
    }
  }

  const existing = sessionStorage.getItem(STORAGE_KEY);
  if (existing && isSafeWebsiteReturnPath(existing)) return;

  try {
    const ref = document.referrer;
    if (!ref) return;
    const url = new URL(ref);
    if (url.origin !== window.location.origin) return;
    const path = `${url.pathname}${url.search}${url.hash}`;
    if (isSafeWebsiteReturnPath(path)) {
      sessionStorage.setItem(STORAGE_KEY, path);
    }
  } catch {
    /* ignore bad referrer */
  }
}

export function getWebsiteReturnUrl(): string {
  if (typeof window === "undefined") return "/";
  const stored = sessionStorage.getItem(STORAGE_KEY);
  if (stored && isSafeWebsiteReturnPath(stored)) return stored;
  return "/";
}
