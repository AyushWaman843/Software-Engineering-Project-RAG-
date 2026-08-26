/**
 * Security response headers for the Next.js app (applied in middleware).
 *
 * CSP is stricter than the DPDP baseline and extended only for required third parties
 * (Supabase Auth, Razorpay checkout). HSTS is production-only over HTTPS.
 */

function supabaseConnectOrigins(): string {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  if (!url) return "";
  try {
    return new URL(url).origin;
  } catch {
    return "";
  }
}

export function buildContentSecurityPolicy(isDev: boolean): string {
  const supabaseOrigin = supabaseConnectOrigins();

  // Baseline DPDP policy — extended minimally for auth + payments.
  const directives = [
    "default-src 'self'",
    [
      "script-src",
      "'self'",
      "'unsafe-inline'",
      isDev ? "'unsafe-eval'" : "",
      "https://checkout.razorpay.com",
      "https://challenges.cloudflare.com",
    ]
      .filter(Boolean)
      .join(" "),
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    [
      "connect-src",
      "'self'",
      supabaseOrigin,
      "https://*.supabase.co",
      "wss://*.supabase.co",
      "https://api.razorpay.com",
      "https://checkout.razorpay.com",
      "https://challenges.cloudflare.com",
    ]
      .filter(Boolean)
      .join(" "),
    "frame-src https://api.razorpay.com https://checkout.razorpay.com https://challenges.cloudflare.com",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ];

  if (!isDev) {
    directives.push("upgrade-insecure-requests");
  }

  return directives.join("; ");
}

/** Attach security headers to every Next.js response. */
export function applySecurityHeaders(response: Response, isDev: boolean): void {
  response.headers.set("Content-Security-Policy", buildContentSecurityPolicy(isDev));
  response.headers.set("X-Content-Type-Options", "nosniff");
  // DENY prevents clickjacking; aligns with CSP frame-ancestors 'none'.
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set(
    "Permissions-Policy",
    "camera=(), microphone=(), geolocation=(), payment=(self)",
  );

  // HSTS only in production (site served over HTTPS).
  if (!isDev) {
    response.headers.set(
      "Strict-Transport-Security",
      "max-age=63072000; includeSubDomains; preload",
    );
  }
}
