/**
 * Client-side URL validation for scan inputs (UX only — server enforces SSRF rules).
 */

const MAX_URL_LENGTH = 2048;

const BLOCKED_HOSTNAMES = new Set([
  "localhost",
  "metadata.google.internal",
  "metadata.google",
]);

const PRIVATE_IPV4 =
  /^(127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.|0\.|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.)/;

const PRIVATE_IPV6 = /^(::1$|fc|fd|fe80)/i;

function isPrivateOrLocalHost(hostname: string): boolean {
  const host = hostname.toLowerCase().replace(/\.$/, "");
  if (BLOCKED_HOSTNAMES.has(host)) return true;
  if (host.endsWith(".localhost") || host.endsWith(".local")) return true;
  if (PRIVATE_IPV4.test(host) || PRIVATE_IPV6.test(host)) return true;
  return false;
}

function allowedPort(port: string | undefined): boolean {
  if (!port) return true;
  return port === "80" || port === "443";
}

export function normalizeScanUrl(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;

  let url = trimmed;
  if (!/^https?:\/\//i.test(url)) {
    url = `https://${url}`;
  }

  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    if (!parsed.hostname) return null;
    if (parsed.username || parsed.password) return null;
    if (!allowedPort(parsed.port || undefined)) return null;
    if (url.length > MAX_URL_LENGTH) return null;
    return parsed.href;
  } catch {
    return null;
  }
}

export type UrlValidationResult =
  | { ok: true; url: string }
  | { ok: false; error: string };

export function validateScanUrlClient(raw: string, label = "URL"): UrlValidationResult {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { ok: false, error: `Please enter a ${label}.` };
  }
  if (trimmed.length > MAX_URL_LENGTH) {
    return { ok: false, error: `${label} is too long (max ${MAX_URL_LENGTH} characters).` };
  }

  const normalized = normalizeScanUrl(trimmed);
  if (!normalized) {
    return { ok: false, error: `Please enter a valid ${label} (http or https only).` };
  }

  try {
    const parsed = new URL(normalized);
    const hostname = parsed.hostname.toLowerCase();
    if (isPrivateOrLocalHost(hostname)) {
      return { ok: false, error: `${label} must be a public website address.` };
    }
  } catch {
    return { ok: false, error: `Please enter a valid ${label}.` };
  }

  return { ok: true, url: normalized };
}

export function validateOptionalScanUrlClient(
  raw: string,
  label: string,
): UrlValidationResult | { ok: true; url: string | null } {
  if (!raw.trim()) return { ok: true, url: null };
  return validateScanUrlClient(raw, label);
}
