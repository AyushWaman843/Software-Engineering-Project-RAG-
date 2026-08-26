import type { QuotaInfo } from "./types";
import { clientApiBase, userApiHeaders } from "./api";

export { userApiHeaders } from "./api";

export async function fetchQuotaClient(
  userId?: string,
  accessToken?: string,
): Promise<QuotaInfo | null> {
  try {
    const res = await fetch(`${clientApiBase}/quota`, {
      credentials: "include",
      headers: userApiHeaders(userId, accessToken),
    });
    if (!res.ok) return null;
    return (await res.json()) as QuotaInfo;
  } catch {
    return null;
  }
}

export async function fetchNavPremiumStatus(
  userId?: string,
  reportId?: string,
  accessToken?: string,
): Promise<boolean> {
  try {
    const qs = reportId ? `?report_id=${encodeURIComponent(reportId)}` : "";
    const res = await fetch(`${clientApiBase}/user/nav-status${qs}`, {
      credentials: "include",
      headers: userApiHeaders(userId, accessToken),
    });
    if (!res.ok) return false;
    const data = (await res.json()) as { is_premium_user?: boolean };
    return Boolean(data.is_premium_user);
  } catch {
    return false;
  }
}

export async function claimVisitorScanClient(
  userId?: string,
  accessToken?: string,
): Promise<QuotaInfo | null> {
  try {
    const res = await fetch(`${clientApiBase}/quota/claim`, {
      method: "POST",
      credentials: "include",
      headers: userApiHeaders(userId, accessToken),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { quota?: QuotaInfo };
    return data.quota ?? null;
  } catch {
    return null;
  }
}
