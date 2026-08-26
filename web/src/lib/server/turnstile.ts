/**
 * Server-only Cloudflare Turnstile verification.
 */

const VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

function secretKey(): string {
  return (
    process.env.TURNSTILE_SECRET_KEY?.trim() ||
    process.env.CLOUDFLARE_TURNSTILE_SECRET_KEY?.trim() ||
    ""
  );
}

function required(): boolean {
  return process.env.TURNSTILE_REQUIRED === "1";
}

export async function verifyTurnstileToken(
  token: string | undefined | null,
  remoteIp?: string | null,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const secret = secretKey();
  if (!secret) {
    if (required()) {
      return { ok: false, error: "CAPTCHA is required but not configured on the server." };
    }
    return { ok: true };
  }

  const cleaned = (token || "").trim();
  if (!cleaned) {
    return { ok: false, error: "Please complete the CAPTCHA and try again." };
  }

  const body = new URLSearchParams();
  body.set("secret", secret);
  body.set("response", cleaned);
  if (remoteIp) body.set("remoteip", remoteIp);

  try {
    const res = await fetch(VERIFY_URL, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
      cache: "no-store",
    });
    const data = (await res.json()) as { success?: boolean };
    if (data.success) return { ok: true };
    return { ok: false, error: "CAPTCHA check failed. Please refresh and try again." };
  } catch {
    return { ok: false, error: "CAPTCHA verification failed. Please try again." };
  }
}
