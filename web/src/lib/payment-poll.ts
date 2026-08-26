import { clientApiBase, userApiHeaders } from "@/lib/api";
import type { QuotaInfo } from "@/lib/types";

const POLL_INTERVAL_MS = 1200;
const DEFAULT_TIMEOUT_MS = 90_000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

/** Notify the app that entitlements changed so report/nav/quota UIs can soft-refresh. */
export function notifyPremiumUpdated(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event("premium-status-updated"));
}

/** Poll until report access_tier is full (webhook or client unlock). */
export async function pollReportUnlocked(
  reportId: string,
  userId: string,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  accessToken?: string,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    try {
      const res = await fetch(
        `${clientApiBase}/report/${encodeURIComponent(reportId)}/status`,
        {
          credentials: "include",
          cache: "no-store",
          headers: userApiHeaders(userId, accessToken),
        },
      );
      if (res.ok) {
        const data = (await res.json()) as { access_tier?: string };
        if (data.access_tier === "full") return true;
      }
    } catch {
      /* retry until timeout */
    }
    await sleep(POLL_INTERVAL_MS);
  }

  return false;
}

/** Poll until prepaid scan credit appears (paid_scan webhook / confirm). */
export async function pollPrepaidScanGranted(
  userId: string,
  baselinePrepaid: number,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  accessToken?: string,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${clientApiBase}/quota`, {
        credentials: "include",
        cache: "no-store",
        headers: userApiHeaders(userId, accessToken),
      });
      if (res.ok) {
        const data = (await res.json()) as QuotaInfo;
        const prepaid = data.prepaid_scans ?? data.scan_credits ?? 0;
        if (prepaid > baselinePrepaid) return true;
      }
    } catch {
      /* retry */
    }
    await sleep(POLL_INTERVAL_MS);
  }

  return false;
}

export type ClientUnlockResult = {
  ok: boolean;
  accessTier?: "full" | "preview";
  status?: number;
  error?: string;
};

/** Client-side report unlock; returns whether the API already granted full access. */
export async function tryClientReportUnlock(
  reportId: string,
  userId: string,
  payment: {
    razorpay_payment_id: string;
    razorpay_order_id: string;
    razorpay_signature: string;
  },
  accessToken?: string,
): Promise<ClientUnlockResult> {
  try {
    const res = await fetch(`${clientApiBase}/report/${encodeURIComponent(reportId)}/unlock`, {
      method: "POST",
      credentials: "include",
      headers: { ...userApiHeaders(userId, accessToken), "Content-Type": "application/json" },
      body: JSON.stringify(payment),
    });
    const data = (await res.json().catch(() => ({}))) as {
      access_tier?: string;
      error?: string;
      code?: string;
    };
    if (res.ok) {
      return {
        ok: true,
        accessTier: data.access_tier === "full" ? "full" : "preview",
        status: res.status,
      };
    }
    // Idempotent: payment already applied for this report.
    if (res.status === 409 && data.code === "PAYMENT_ALREADY_USED") {
      return { ok: true, accessTier: "full", status: res.status, error: data.error };
    }
    console.error("Report unlock failed:", data.error || res.status);
    return { ok: false, status: res.status, error: data.error };
  } catch (err) {
    console.error("Report unlock request failed:", err);
    return { ok: false, error: "network" };
  }
}

export async function tryClientPrepaidConfirm(
  userId: string,
  payment: {
    razorpay_payment_id: string;
    razorpay_order_id: string;
    razorpay_signature: string;
  },
  accessToken?: string,
): Promise<boolean> {
  try {
    const res = await fetch(`${clientApiBase}/scan/confirm-payment`, {
      method: "POST",
      credentials: "include",
      headers: { ...userApiHeaders(userId, accessToken), "Content-Type": "application/json" },
      body: JSON.stringify(payment),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** Poll until Pilot (or legacy premium) is active for the signed-in user. */
export async function pollProSubscriptionActive(
  userId: string,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  accessToken?: string,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${clientApiBase}/subscription/status`, {
        credentials: "include",
        cache: "no-store",
        headers: userApiHeaders(userId, accessToken),
      });
      if (res.ok) {
        const data = (await res.json()) as { has_pro?: boolean; has_pilot?: boolean; tier?: string };
        if (data.has_pilot || data.tier === "pilot" || data.has_pro) return true;
      }
    } catch {
      /* retry */
    }
    await sleep(POLL_INTERVAL_MS);
  }

  return false;
}

export async function tryClientProConfirm(
  userId: string,
  payment:
    | {
        razorpay_payment_id: string;
        razorpay_subscription_id: string;
        razorpay_signature: string;
      }
    | {
        razorpay_payment_id: string;
        razorpay_order_id: string;
        razorpay_signature: string;
      },
  accessToken?: string,
): Promise<boolean> {
  try {
    const res = await fetch(`${clientApiBase}/subscription/pro/confirm`, {
      method: "POST",
      credentials: "include",
      headers: { ...userApiHeaders(userId, accessToken), "Content-Type": "application/json" },
      body: JSON.stringify(payment),
    });
    if (res.ok) return true;
    const data = (await res.json().catch(() => ({}))) as { error?: string };
    console.error("Subscription confirm failed:", data.error || res.status);
    return false;
  } catch (err) {
    console.error("Subscription confirm request failed:", err);
    return false;
  }
}
