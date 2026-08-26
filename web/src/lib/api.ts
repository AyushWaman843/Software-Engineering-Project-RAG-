import { unstable_cache } from "next/cache";
import type { AppMeta, HistoryItem, ReportContext } from "./types";
import type { PrevScan } from "./trend";

function backendUrl(): string {
  return process.env.BACKEND_URL ?? "http://127.0.0.1:5000";
}

/** Auth for server-side fetches to Flask (bypasses Next.js middleware). */
function backendHeaders(extra?: HeadersInit): HeadersInit {
  const headers = new Headers(extra);
  const key = (process.env.INTERNAL_API_KEY || process.env.API_KEY || "").trim();
  if (key) {
    headers.set("X-API-Key", key);
  }
  return headers;
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    cache: "no-store",
    headers: backendHeaders(init?.headers),
  });
  if (!res.ok) throw new Error(`Request failed: ${url}`);
  return res.json() as Promise<T>;
}

/**
 * Server-side fetch against the Flask API (cached — metadata rarely changes).
 * INTERNAL_API_KEY / API_KEY are server-only — never import into client components.
 */
export const fetchMeta = unstable_cache(
  async (): Promise<AppMeta> => fetchJson(`${backendUrl()}/api/meta`),
  ["app-meta"],
  { revalidate: 300 },
);

/** Recent assessment list for the sidebar (cached briefly). */
export const fetchHistory = unstable_cache(
  async (): Promise<HistoryItem[]> => {
    const res = await fetch(`${backendUrl()}/api/history`, {
      cache: "no-store",
      headers: backendHeaders(),
    });
    if (!res.ok) return [];
    return res.json() as Promise<HistoryItem[]>;
  },
  ["scan-history", process.env.INTERNAL_API_KEY || process.env.API_KEY || "no-key"],
  { revalidate: 30 },
);

/** Full report payload for the report page (tier depends on unlock status). */
/**
 * Server-side report fetch. Pass the viewer's access token — Flask verifies JWT.
 * Do not rely on X-User-Id alone.
 */
export async function fetchReport(
  reportId: string,
  opts?: { cookieHeader?: string; userId?: string; accessToken?: string },
): Promise<ReportContext | null | "forbidden"> {
  const headers = new Headers(
    backendHeaders(opts?.cookieHeader ? { Cookie: opts.cookieHeader } : undefined),
  );
  if (opts?.accessToken) {
    headers.set("Authorization", `Bearer ${opts.accessToken}`);
  }
  if (opts?.userId) {
    headers.set("X-User-Id", opts.userId);
  }
  const res = await fetch(`${backendUrl()}/api/report/${encodeURIComponent(reportId)}`, {
    cache: "no-store",
    headers,
  });
  if (res.status === 404) return null;
  if (res.status === 403) return "forbidden";
  if (res.status === 401) {
    throw new Error("Report API unauthorized — check INTERNAL_API_KEY matches API_KEY in .env");
  }
  if (!res.ok) throw new Error("Failed to load report");
  return res.json() as Promise<ReportContext>;
}

/** Prior scan of the same site — lightweight alternative to loading full history. */
export async function fetchPreviousScan(
  reportId: string,
  opts?: { accessToken?: string },
): Promise<PrevScan | null> {
  const headers = new Headers(backendHeaders());
  if (opts?.accessToken) {
    headers.set("Authorization", `Bearer ${opts.accessToken}`);
  }
  const res = await fetch(`${backendUrl()}/api/report/${encodeURIComponent(reportId)}/previous`, {
    cache: "no-store",
    headers,
  });
  if (res.status === 404) return null;
  if (!res.ok) return null;
  const data = (await res.json()) as PrevScan | null;
  return data?.timestamp ? data : null;
}

/** Client-side relative URL (proxied by Next.js rewrites). */
export const clientApiBase = "/scanner/api";

/**
 * Forward the signed-in Supabase access token so Flask can verify identity.
 * `userId` is optional metadata only and must never be trusted alone.
 */
export function userApiHeaders(
  userIdOrToken?: string,
  accessToken?: string,
): HeadersInit {
  // Backward compatible: userApiHeaders(userId) OR userApiHeaders(userId, accessToken)
  // Preferred: userApiHeaders(undefined, accessToken) or pass token as 2nd arg.
  const headers: Record<string, string> = {};
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  } else if (userIdOrToken && userIdOrToken.includes(".")) {
    // Looks like a JWT (three segments) — treat first arg as access token.
    headers.Authorization = `Bearer ${userIdOrToken}`;
  }
  if (userIdOrToken && !userIdOrToken.includes(".")) {
    headers["X-User-Id"] = userIdOrToken;
  }
  return headers;
}
