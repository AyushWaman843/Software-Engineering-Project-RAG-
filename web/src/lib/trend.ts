import type { HistoryItem } from "./types";

/** Normalise a site URL for grouping repeat scans (case + trailing slash insensitive). */
export function normalizeUrl(u: string | undefined | null): string {
  return (u ?? "").trim().toLowerCase().replace(/\/+$/, "");
}

export interface PrevScan {
  score: number;
  timestamp: string;
}

/**
 * Most recent history scan of the same site strictly before `currentTimestamp`,
 * excluding the current report itself. Returns null when there is no prior scan.
 */
export function previousScanFor(
  history: HistoryItem[],
  url: string,
  currentTimestamp: string,
  currentId: string,
): PrevScan | null {
  const key = normalizeUrl(url);
  const earlier = history
    .filter(
      (h) =>
        h._report_id !== currentId &&
        normalizeUrl(h.url) === key &&
        (h.timestamp ?? "") < (currentTimestamp ?? ""),
    )
    .sort((a, b) => (b.timestamp ?? "").localeCompare(a.timestamp ?? ""));

  const prev = earlier[0];
  return prev ? { score: prev.score, timestamp: prev.timestamp } : null;
}

/** Chronological score series (oldest → newest) for every site in the history. */
export function scoreSeriesByUrl(history: HistoryItem[]): Map<string, HistoryItem[]> {
  const groups = new Map<string, HistoryItem[]>();
  for (const item of history) {
    const key = normalizeUrl(item.url);
    const list = groups.get(key);
    if (list) list.push(item);
    else groups.set(key, [item]);
  }
  for (const list of groups.values()) {
    list.sort((a, b) => (a.timestamp ?? "").localeCompare(b.timestamp ?? ""));
  }
  return groups;
}
