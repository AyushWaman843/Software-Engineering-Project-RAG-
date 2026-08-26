"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Check, ClipboardCheck, Copy, ListChecks, Sparkles } from "lucide-react";
import type { Finding } from "@/lib/types";
import { useCookieConsent } from "@/contexts/CookieConsentContext";

interface RemediationPlanProps {
  findings: Finding[];
  reportId: string;
  score: number;
}

interface RemediationItem extends Finding {
  gap: number;
  allocGap: number;
}

const reveal = {
  initial: { opacity: 0, y: 10 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-40px" },
  transition: { duration: 0.25, ease: [0.22, 1, 0.36, 1] as const },
};

/** Distribute recoverable points across items without exceeding the 100-pt scale. */
function buildRemediationItems(findings: Finding[], score: number): {
  items: RemediationItem[];
  totalRecoverable: number;
  potentialScore: number;
} {
  const headroom = Math.max(0, 100 - score);
  const rawItems = findings
    .map((f) => ({
      ...f,
      gap: Math.max(0, (f.max_points ?? 0) - (f.points ?? 0)),
    }))
    .filter((f) => f.gap > 0.05)
    .sort((a, b) => b.gap - a.gap);

  const rawTotal = rawItems.reduce((sum, it) => sum + it.gap, 0);
  const totalRecoverable = Math.min(rawTotal, headroom);
  const potentialScore = Math.min(100, score + totalRecoverable);

  if (rawTotal <= 0 || totalRecoverable <= 0) {
    return { items: [], totalRecoverable: 0, potentialScore: score };
  }

  if (rawTotal <= headroom) {
    return {
      items: rawItems.map((it) => ({ ...it, allocGap: it.gap })),
      totalRecoverable,
      potentialScore,
    };
  }

  // Raw indicator gaps can exceed headroom when the headline score is rounded —
  // scale per-item gains so they sum exactly to remaining points on the 100-pt scale.
  let allocated = 0;
  const items: RemediationItem[] = rawItems.map((it, index, arr) => {
    if (index === arr.length - 1) {
      const allocGap = Math.max(0, Math.round((totalRecoverable - allocated) * 10) / 10);
      return { ...it, allocGap };
    }
    const allocGap = Math.round((it.gap / rawTotal) * totalRecoverable * 10) / 10;
    allocated += allocGap;
    return { ...it, allocGap };
  });

  return {
    items: items.filter((it) => it.allocGap > 0.05),
    totalRecoverable,
    potentialScore,
  };
}

function formatPts(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

/** Prioritised, checkable list of fixes derived from indicators with remaining point gaps. */
export function RemediationPlan({ findings, reportId, score }: RemediationPlanProps) {
  const { ready: consentReady, functional: functionalConsent } = useCookieConsent();
  const { items, totalRecoverable, potentialScore } = useMemo(
    () => buildRemediationItems(findings, score),
    [findings, score],
  );

  const storageKey = `dpdp:remediation:${reportId}`;
  const [resolved, setResolved] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (!consentReady || !functionalConsent) {
      setHydrated(true);
      return;
    }

    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) setResolved(new Set(JSON.parse(raw) as string[]));
    } catch {
      /* ignore corrupt/unavailable storage */
    }
    setHydrated(true);
  }, [storageKey, consentReady, functionalConsent]);

  useEffect(() => {
    if (!hydrated || !functionalConsent) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify([...resolved]));
    } catch {
      /* ignore */
    }
  }, [resolved, hydrated, storageKey, functionalConsent]);

  if (items.length === 0) {
    return (
      <motion.section {...reveal} className="panel relative overflow-hidden">
        <span className="absolute inset-y-0 left-0 w-[3px] bg-mint" aria-hidden />
        <div className="flex items-center gap-3 px-7 py-6">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-mint/15 text-mint">
            <Sparkles className="h-5 w-5" />
          </span>
          <div>
            <h2 className="font-display text-lg font-bold tracking-tight text-white">
              No remediation required
            </h2>
            <p className="mt-0.5 text-sm text-[var(--color-text-muted)]">
              Every assessed indicator was satisfied. Re-scan periodically to maintain compliance.
            </p>
          </div>
        </div>
      </motion.section>
    );
  }

  const recovered = items
    .filter((it) => resolved.has(it.key))
    .reduce((sum, it) => sum + it.allocGap, 0);
  const remainingRecoverable = Math.max(0, totalRecoverable - recovered);
  const doneCount = items.filter((it) => resolved.has(it.key)).length;
  const pct = Math.round((doneCount / items.length) * 100);

  const toggle = (key: string) =>
    setResolved((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const copy = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      setTimeout(() => setCopied((c) => (c === key ? null : c)), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <motion.section {...reveal} className="panel overflow-hidden">
      <header className="panel-header">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 font-display text-lg font-bold tracking-tight text-white">
              <ListChecks className="h-4 w-4 text-mint" />
              Remediation Plan
            </h2>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">
              Prioritised fixes to raise your compliance score — highest impact first.
            </p>
          </div>
          <div className="text-right">
            <p className="font-display text-2xl font-bold leading-none tabular-nums text-mint-soft">
              +{formatPts(remainingRecoverable)}
            </p>
            <p className="mt-1 text-[0.6rem] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-faint)]">
              pts recoverable
            </p>
            <p className="mt-1.5 text-xs tabular-nums text-[var(--color-text-muted)]">
              {score}/100 → up to {potentialScore}/100
            </p>
          </div>
        </div>
        <div className="mt-4">
          <div className="mb-1.5 flex items-center justify-between text-xs text-[var(--color-text-muted)]">
            <span>
              {doneCount} of {items.length} resolved
            </span>
            <span className="tabular-nums">{pct}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-white/5">
            <motion.span
              className="block h-full rounded-full bg-gradient-to-r from-mint-strong to-mint"
              initial={{ width: 0 }}
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.5, ease: "easeOut" }}
            />
          </div>
        </div>
      </header>

      <ul className="divide-y divide-border-light">
        {items.map((it, i) => {
          const done = resolved.has(it.key);
          return (
            <li key={it.key || `remediation-${i}`} className="px-7 py-4">
              <div className="flex items-start gap-3.5">
                <button
                  type="button"
                  onClick={() => toggle(it.key)}
                  aria-pressed={done}
                  aria-label={done ? "Mark as not done" : "Mark as resolved"}
                  className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md border transition-all ${
                    done
                      ? "border-mint bg-mint text-[#05130d]"
                      : "border-border-strong bg-white/[0.03] text-transparent hover:border-mint/60"
                  }`}
                >
                  <Check className="h-3.5 w-3.5" strokeWidth={3} />
                </button>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[0.7rem] font-bold tabular-nums text-[var(--color-text-faint)]">
                      #{i + 1}
                    </span>
                    <h3
                      className={`font-display font-bold ${
                        done ? "text-[var(--color-text-faint)] line-through" : "text-white"
                      }`}
                    >
                      {it.indicator}
                    </h3>
                    <span className={`status-pill status-${it.status.toLowerCase()}`}>
                      {it.status}
                    </span>
                    <span className="inline-flex items-center rounded-full border border-mint/30 bg-mint/10 px-2 py-0.5 text-xs font-bold tabular-nums text-mint-soft">
                      +{formatPts(it.allocGap)} pts
                    </span>
                  </div>
                  {it.recommendation && (
                    <p
                      className={`mt-1.5 text-sm leading-relaxed ${
                        done ? "text-[var(--color-text-faint)]" : "text-[var(--color-text-muted)]"
                      }`}
                    >
                      {it.recommendation}
                    </p>
                  )}
                  <p className="mt-1 font-mono text-[0.7rem] text-[var(--color-text-faint)]">
                    {it.rule}
                    {it.gap !== it.allocGap && (
                      <span className="ml-2 text-[var(--color-text-faint)]">
                        ({formatPts(it.points)}/{formatPts(it.max_points)} earned)
                      </span>
                    )}
                  </p>
                </div>

                {it.recommendation && (
                  <button
                    type="button"
                    onClick={() => copy(it.key, it.recommendation)}
                    className="shrink-0 rounded-lg border border-border-strong bg-white/[0.03] p-2 text-[var(--color-text-muted)] transition-colors hover:border-mint/40 hover:text-white"
                    aria-label="Copy recommendation"
                  >
                    {copied === it.key ? (
                      <ClipboardCheck className="h-4 w-4 text-mint" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </motion.section>
  );
}
