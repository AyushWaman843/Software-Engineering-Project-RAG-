"use client";

import { useMemo } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ChevronRight, Clock, Lock, LockOpen, TrendingDown, TrendingUp } from "lucide-react";
import type { HistoryItem } from "@/lib/types";
import { normalizeUrl, scoreSeriesByUrl } from "@/lib/trend";
import { Sparkline } from "@/components/ui/Sparkline";

interface HistoryListProps {
  items: HistoryItem[];
  emptyMessage?: string;
  openInNewTab?: boolean;
  onItemClick?: () => void;
}

type Band = "high" | "mid" | "low";

const BANDS: Record<Band, { chip: string; text: string; bar: string }> = {
  high: { chip: "border-mint/40 bg-mint/10 text-mint-soft", text: "text-mint-soft", bar: "bg-mint" },
  mid: { chip: "border-amber/40 bg-amber/10 text-amber-soft", text: "text-amber-soft", bar: "bg-amber" },
  low: { chip: "border-rose/40 bg-rose/10 text-rose-soft", text: "text-rose-soft", bar: "bg-rose" },
};

function bandFor(verdict: string, score: number): Band {
  const v = (verdict ?? "").toLowerCase();
  if (v.includes("non")) return "low";
  if (v.includes("partial")) return "mid";
  if (v.includes("complia")) return "high";
  return score >= 67 ? "high" : score >= 34 ? "mid" : "low";
}

export function HistoryList({
  items,
  emptyMessage = "No previous assessments recorded.",
  openInNewTab = false,
  onItemClick,
}: HistoryListProps) {
  const series = useMemo(() => scoreSeriesByUrl(items), [items]);

  if (items.length === 0) {
    return (
      <p className="px-4 py-10 text-center text-sm leading-relaxed text-[var(--color-text-faint)]">
        {emptyMessage}
      </p>
    );
  }

  return (
    <ul className="divide-y divide-border-light">
      {items.map((item, index) => {
        const band = BANDS[bandFor(item.verdict, item.score)];
        const group = series.get(normalizeUrl(item.url)) ?? [];
        const idx = group.findIndex((g) => g._report_id === item._report_id);
        const prev = idx > 0 ? group[idx - 1] : null;
        const delta = prev ? item.score - prev.score : null;
        const showSpark = group.length >= 2 && idx === group.length - 1;

        return (
          <motion.li
            key={item._report_id || `history-${index}`}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(index * 0.02, 0.1), duration: 0.2 }}
          >
            <Link
              href={`/report/${item._report_id}`}
              target={openInNewTab ? "_blank" : undefined}
              rel={openInNewTab ? "noopener noreferrer" : undefined}
              onClick={onItemClick}
              className="group relative block overflow-hidden px-4 py-4 transition-colors hover:bg-[var(--overlay-hover)] md:px-5"
            >
              <span
                className={`absolute inset-y-0 left-0 w-[3px] origin-top scale-y-0 transition-transform duration-300 group-hover:scale-y-100 ${band.bar}`}
                aria-hidden
              />
              <div className="flex items-start justify-between gap-2">
                <span className="truncate text-sm font-semibold text-[var(--color-text)] transition-colors group-hover:text-mint">
                  {item.url}
                </span>
                <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 -translate-x-1 text-mint opacity-0 transition-all duration-300 group-hover:translate-x-0 group-hover:opacity-100" />
              </div>
              <div className="mt-2 flex flex-col gap-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <span
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-bold tabular-nums ${band.chip}`}
                    >
                      {item.score}
                      <span className="ml-0.5 font-medium opacity-60">/100</span>
                    </span>

                    {delta !== null && delta !== 0 && (
                      <span
                        className={`inline-flex items-center gap-0.5 text-xs font-bold tabular-nums ${
                          delta > 0 ? "text-mint-soft" : "text-rose-soft"
                        }`}
                        title="Change vs previous scan"
                      >
                        {delta > 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                        {delta > 0 ? `+${delta}` : delta}
                      </span>
                    )}

                    <span className={`text-xs font-semibold ${band.text}`}>{item.verdict}</span>
                  </div>

                  {showSpark && (
                    <span className={`shrink-0 ${band.text}`} aria-hidden>
                      <Sparkline values={group.map((g) => g.score)} width={62} height={22} />
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-3 text-xs">
                  <span className="inline-flex items-center gap-1 text-[var(--color-text-faint)]">
                    <Clock className="h-3 w-3" />
                    {item.timestamp?.slice(0, 10) ?? "—"}
                  </span>

                  <span className="h-3 w-px bg-border-strong" />

                  {item.access_tier === "full" ? (
                    <span
                      title="Full report unlocked"
                      className="inline-flex items-center gap-1 font-medium text-mint-soft"
                    >
                      <LockOpen className="h-3 w-3" />
                      Full report unlocked
                    </span>
                  ) : (
                    <span
                      title="Free preview — full report locked"
                      className="inline-flex items-center gap-1 font-medium text-amber-500/80"
                    >
                      <Lock className="h-3 w-3" />
                      Preview report
                    </span>
                  )}
                </div>
              </div>
            </Link>
          </motion.li>
        );
      })}
    </ul>
  );
}
