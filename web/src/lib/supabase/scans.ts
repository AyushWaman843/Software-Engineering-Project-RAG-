import type { HistoryItem } from "@/lib/types";
import { clientApiBase, userApiHeaders } from "@/lib/api";

export interface ScanRecordInput {
  report_id: string;
  url: string;
  score: number;
  verdict: string;
  timestamp?: string;
}

export type SaveScanResult =
  | { ok: true }
  | { ok: false; message: string; setupRequired?: boolean };

export type FetchScansResult = {
  items: HistoryItem[];
  error?: string;
  setupRequired?: boolean;
};

export const SUPABASE_SETUP_HINT =
  "Run supabase/schema.sql in your Supabase project (Dashboard → SQL Editor → New query → Run).";

/** Load saved scans via Flask (avoids browser → Supabase fetch/CSP issues). */
export async function fetchUserScansClient(
  userId?: string,
  accessToken?: string,
): Promise<FetchScansResult> {
  try {
    const res = await fetch(`${clientApiBase}/user/scans`, {
      credentials: "include",
      cache: "no-store",
      headers: userApiHeaders(userId, accessToken),
    });

    if (res.status === 401) {
      return { items: [] };
    }

    if (!res.ok) {
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      return { items: [], error: data.error || "Could not load scan history." };
    }

    const data = (await res.json()) as { items?: HistoryItem[] };
    return { items: data.items ?? [] };
  } catch (err) {
    console.warn("fetchUserScansClient failed:", err);
    return { items: [], error: "Could not load scan history." };
  }
}

/** Persist a completed scan for the signed-in user via Flask. */
export async function saveUserScanClient(
  userId: string | undefined,
  scan: ScanRecordInput,
  accessToken?: string,
): Promise<SaveScanResult> {
  if (!userId) return { ok: true };

  try {
    const res = await fetch(`${clientApiBase}/user/scans`, {
      method: "POST",
      credentials: "include",
      headers: {
        ...userApiHeaders(userId, accessToken),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        report_id: scan.report_id,
        url: scan.url,
        score: scan.score,
        verdict: scan.verdict,
        timestamp: scan.timestamp,
      }),
    });

    if (res.status === 401) {
      return { ok: false, message: "Sign in to save scan history." };
    }

    if (!res.ok) {
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      return { ok: false, message: data.error || "Could not save scan history." };
    }

    return { ok: true };
  } catch (err) {
    console.warn("saveUserScanClient failed:", err);
    return { ok: false, message: "Could not save scan history." };
  }
}
