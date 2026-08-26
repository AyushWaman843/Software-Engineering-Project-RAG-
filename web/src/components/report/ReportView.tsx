"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  FileText,
  Info,
  Lightbulb,
  Minus,
  ShieldCheck,
  ShieldX,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type { ReportContext } from "@/lib/types";
import type { PrevScan } from "@/lib/trend";
import { safeHttpUrl } from "@/lib/security/urls";
import { ScoreGauge } from "@/components/ui/ScoreGauge";
import { RemediationPlan } from "@/components/report/RemediationPlan";
import { PremiumGate } from "@/components/report/PremiumGate";
import { PremiumPdfButton } from "@/components/report/PremiumPdfButton";

interface ReportViewProps {
  data: ReportContext;
  previous?: PrevScan | null;
}

/** Hide raw "conf: N%" from labels; surface it via the info control instead. */
function parseScoreBreakdownLabel(item: string): { title: string; confidence: string | null } {
  const confMatch = item.match(/,?\s*conf:\s*(\d+%)/i);
  const confidence = confMatch?.[1] ?? null;
  if (!confidence) return { title: item, confidence: null };

  let title = item.replace(/,?\s*conf:\s*\d+%/i, "");
  title = title.replace(/\(\s*\)/g, "").replace(/\(\s+/g, "(").replace(/\s+\)/g, ")").replace(/\s{2,}/g, " ").trim();
  return { title, confidence };
}

type Band = "high" | "mid" | "low";

function bandFor(scoreClass: string, verdictClass: string): Band {
  if (scoreClass === "score-high" || verdictClass === "verdict-compliant") return "high";
  if (scoreClass === "score-mid" || verdictClass === "verdict-partial") return "mid";
  return "low";
}

const BAND_TEXT: Record<Band, string> = {
  high: "text-green-soft",
  mid: "text-amber-soft",
  low: "text-rose-soft",
};

const BAND_GLOW: Record<Band, string> = {
  high: "rgba(37,192,138,0.16)",
  mid: "rgba(255,176,32,0.14)",
  low: "rgba(255,95,95,0.14)",
};

const reveal = {
  initial: { opacity: 0, y: 10 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-40px" },
  transition: { duration: 0.25, ease: [0.22, 1, 0.36, 1] as const },
};

export function ReportView({ data, previous }: ReportViewProps) {
  const report = data.report as {
    url?: string;
    timestamp?: string;
    scraping_method?: string;
    privacy_policy_found?: boolean;
    cookie_banner_found?: boolean;
    grievance_officer_contact?: string | null;
    errors?: string[];
  };

  const scanSteps = (data.analysis_details.scan_steps as string[]) ?? [];
  const policyUrls = (data.analysis_details.policy_urls as Record<string, string>) ?? {};
  const band = bandFor(data.score_class, data.verdict_class);
  const isPreview = data.access_tier === "preview";
  const missingPreview = data.missing_indicators ?? data.rows;
  const policyPages =
    data.discovered_policy_pages ??
    ((data.analysis_details.policy_urls as Record<string, string>) ?? {});
  const lockedIndicators = data.premium?.indicators_locked ?? data.premium?.summary_rows_locked ?? 0;

  const trend = previous
    ? (() => {
        const d = data.score - previous.score;
        const dir: "flat" | "up" | "down" = d === 0 ? "flat" : d > 0 ? "up" : "down";
        return {
          dir,
          label: d === 0 ? "No change" : `${d > 0 ? "+" : ""}${d} pts`,
          cls:
            d === 0
              ? "text-[var(--color-text-muted)]"
              : d > 0
                ? "text-mint-soft"
                : "text-rose-soft",
          date: previous.timestamp.slice(0, 10),
        };
      })()
    : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15 }}
      className="report-page space-y-4 md:space-y-6"
    >
      <nav className="report-page__crumb text-sm text-[var(--color-text-muted)]">
        <Link href="/" className="inline-flex items-center gap-1 transition-colors hover:text-white">
          <ArrowLeft className="h-4 w-4" />
          Assessments
        </Link>
        <span className="mx-2 text-[var(--color-text-faint)]">/</span>
        <span className="text-[var(--color-text-faint)]">Report</span>
      </nav>

      <header className="panel report-page__hero relative overflow-hidden">
        <div
          className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full blur-3xl"
          style={{ background: BAND_GLOW[band] }}
          aria-hidden
        />
        <div className="report-page__hero-grid relative grid grid-cols-[auto_1fr] items-start gap-3 p-4 md:grid-cols-[auto_1fr] md:items-center md:gap-8 md:p-9">
          <div className="report-page__gauge-wrap flex flex-col items-center gap-2 md:items-start md:gap-3">
            <ScoreGauge score={data.score} band={band} label={data.verdict} />
          </div>
          <div className="min-w-0 pt-1 md:pt-0">
            <p className="text-[0.65rem] font-bold uppercase tracking-[0.18em] text-[var(--color-text-faint)] md:text-[0.7rem] md:tracking-[0.22em]">
              Compliance Verdict
            </p>
            <h1 className={`report-page__verdict mt-1 font-display text-xl font-bold leading-tight tracking-tight md:mt-2 md:text-4xl ${BAND_TEXT[band]}`}>
              {data.verdict}
            </h1>
            <p className="report-page__verdict-desc mt-1.5 hidden max-w-md text-sm text-[var(--color-text-muted)] md:block md:mt-2">
              Indicative assessment against the DPDP Act, 2025 and DPDP Rules, 2025, scored across
              weighted compliance indicators.
            </p>
            {trend && (
              <div className="report-page__trend mt-2 inline-flex w-fit max-w-full flex-wrap items-center gap-1.5 rounded-full border border-border-strong bg-white/[0.03] px-2.5 py-1 text-[0.6875rem] md:mt-4 md:gap-2 md:px-3 md:py-1.5 md:text-xs">
                {trend.dir === "flat" ? (
                  <Minus className={`h-3.5 w-3.5 ${trend.cls}`} />
                ) : trend.dir === "up" ? (
                  <TrendingUp className={`h-3.5 w-3.5 ${trend.cls}`} />
                ) : (
                  <TrendingDown className={`h-3.5 w-3.5 ${trend.cls}`} />
                )}
                <span className={`font-bold tabular-nums ${trend.cls}`}>{trend.label}</span>
                <span className="text-[var(--color-text-faint)]">vs previous · {trend.date}</span>
              </div>
            )}
            <dl className="report-page__meta mt-3 grid grid-cols-1 gap-y-2 border-t border-border-light pt-3 text-xs sm:grid-cols-2 sm:gap-x-3 sm:gap-y-2.5 md:mt-6 md:gap-x-6 md:gap-y-4 md:pt-6 md:text-sm">
              <div>
                <dt className="text-[0.6rem] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-faint)] md:text-[0.65rem] md:tracking-[0.16em]">Website</dt>
                <dd className="mt-0.5 break-all font-medium text-[var(--color-text)] md:mt-1">
                  {safeHttpUrl(report.url) ? (
                    <a
                      href={safeHttpUrl(report.url)!}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-mint-soft transition-colors hover:text-mint"
                    >
                      {report.url}
                    </a>
                  ) : (
                    report.url
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-[0.6rem] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-faint)] md:text-[0.65rem] md:tracking-[0.16em]">Assessment Date</dt>
                <dd className="mt-0.5 text-[var(--color-text)] md:mt-1">{report.timestamp?.slice(0, 19).replace("T", " ") ?? "—"}</dd>
              </div>
              <div className="report-page__meta-extra">
                <dt className="text-[0.65rem] font-semibold uppercase tracking-[0.16em] text-[var(--color-text-faint)]">Collection Method</dt>
                <dd className="mt-1 capitalize text-[var(--color-text)]">
                  {report.scraping_method === "pdf_upload" ? "PDF upload" : report.scraping_method ?? "—"}
                </dd>
              </div>
              <div className="report-page__meta-extra">
                <dt className="text-[0.65rem] font-semibold uppercase tracking-[0.16em] text-[var(--color-text-faint)]">Analysis Engine</dt>
                <dd className="mt-1 text-[var(--color-text)]">{data.ai_engine}</dd>
              </div>
              <div className="report-page__meta-extra">
                <dt className="text-[0.65rem] font-semibold uppercase tracking-[0.16em] text-[var(--color-text-faint)]">Scanner Version</dt>
                <dd className="mt-1 text-[var(--color-text)]">{data.scanner_version}</dd>
              </div>
              <div className="report-page__meta-extra">
                <dt className="text-[0.65rem] font-semibold uppercase tracking-[0.16em] text-[var(--color-text-faint)]">Ruleset</dt>
                <dd className="mt-1 text-[var(--color-text)]">{data.rules_version}</dd>
              </div>
            </dl>
          </div>
        </div>

        <div className="report-page__cta-block relative hidden border-t border-border-light px-4 pb-7 pt-6 md:block md:px-9">
          <div className="flex flex-col gap-4 rounded-2xl border border-cyan/25 bg-cyan/[0.06] p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex gap-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-cyan/15 text-cyan">
                <Sparkles className="h-5 w-5" />
              </span>
              <div>
                <p className="font-display text-base font-bold text-white">
                  Not sure what to do next?
                </p>
                <p className="mt-1 max-w-2xl text-sm leading-relaxed text-[var(--color-text-muted)]">
                  Your website has gaps in DPDP compliance, and fixing them properly requires legal
                  precision. Our team can help you close every gap — from drafting compliant policies
                  to setting up consent mechanisms.
                </p>
              </div>
            </div>
            <a
              href="mailto:contact@dpdpscanner.in?subject=DPDP%20Compliance%20Help"
              className="btn btn-primary shrink-0 gap-2 whitespace-nowrap"
            >
              Contact Us
              <ArrowRight className="h-4 w-4" />
            </a>
          </div>
        </div>
      </header>

      <div className="report-page__actions hidden flex-wrap gap-3 md:flex">
        <PremiumPdfButton reportId={data.report_id} unlocked={!isPreview} />
        <Link href="/" className="btn btn-secondary gap-2">
          New Assessment
        </Link>
      </div>

      {isPreview ? (
        <>
          {missingPreview.length > 0 && (
            <motion.section {...reveal} className="panel overflow-hidden">
              <header className="panel-header">
                <h2 className="font-display text-lg font-bold tracking-tight text-white">
                  Top Missing Indicators
                </h2>
                <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                  Highest-priority gaps identified in this assessment.
                </p>
              </header>
              <ul className="divide-y divide-border-light px-4 md:px-7 pb-5">
                {missingPreview.map((row) => (
                  <li key={row.key} className="flex flex-wrap items-center justify-between gap-3 py-4">
                    <span className="font-medium text-[var(--color-text)]">{row.indicator}</span>
                    <span className={`status-pill status-${row.status.toLowerCase()}`}>{row.status}</span>
                  </li>
                ))}
              </ul>
            </motion.section>
          )}

          {Object.keys(policyPages).length > 0 && (
            <motion.section {...reveal} className="panel">
              <header className="panel-header">
                <h2 className="font-display text-lg font-bold tracking-tight text-white">
                  Discovered Policy Pages
                </h2>
              </header>
              <dl className="grid gap-3 px-4 md:px-7 pb-6 sm:grid-cols-[auto_1fr]">
                {Object.entries(policyPages).map(([ptype, purl]) => (
                  <div key={ptype} className="contents">
                    <dt className="font-medium capitalize text-[var(--color-text)]">{ptype}</dt>
                    <dd>
                      {purl?.startsWith("Uploaded:") ? (
                        purl
                      ) : safeHttpUrl(purl) ? (
                        <a
                          href={safeHttpUrl(purl)!}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="break-all text-mint-soft hover:text-mint hover:underline"
                        >
                          {purl}
                        </a>
                      ) : purl ? (
                        <span className="break-all text-[var(--color-text-muted)]">{purl}</span>
                      ) : (
                        "Not found"
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            </motion.section>
          )}

          <PremiumGate
            reportId={data.report_id}
            priceDisplay={data.premium?.price_display}
            currency={data.premium?.currency}
            title="Unlock Full Assessment"
            description={`One-time payment unlocks all ${lockedIndicators || 10} indicators, detailed AI analysis, policy excerpts, remediation plan, and a professional PDF for this report.`}
            skeletonRows={6}
          />
        </>
      ) : (
        <>
      {data.policy_extraction_warning && (
        <motion.div
          {...reveal}
          className="flex items-start gap-3 rounded-2xl border border-amber/30 bg-amber/[0.07] px-4 py-3.5 text-sm text-amber-soft"
        >
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber" />
          <p>
            We couldn&apos;t extract the privacy policy automatically. Paste the direct privacy policy
            URL under Direct Policy Links and scan again (e.g.{" "}
            <code className="rounded bg-white/[0.06] px-1 font-mono text-mint-soft">https://www.digilocker.gov.in/digilocker-policy</code>{" "}
            for DigiLocker).
          </p>
        </motion.div>
      )}

      {data.prompt_injection_detected && data.prompt_injection_detected.length > 0 && (
        <motion.div
          {...reveal}
          className="flex items-start gap-3 rounded-2xl border border-amber/30 bg-amber/[0.07] px-4 py-3.5 text-sm text-amber-soft"
        >
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber" />
          <div>
            <p className="font-semibold text-amber">Security notice</p>
            <p className="mt-1">
              The scraped policy text contained {data.prompt_injection_detected.length} instruction-like
              phrase{data.prompt_injection_detected.length === 1 ? "" : "s"} sometimes used in prompt-injection
              attempts. These were treated strictly as document data during analysis and did not influence the
              assessment.
            </p>
          </div>
        </motion.div>
      )}

      <RemediationPlan findings={data.findings} reportId={data.report_id} score={data.score} />

      <motion.section {...reveal} className="panel overflow-hidden">
        <header className="panel-header">
          <h2 className="font-display text-lg font-bold tracking-tight text-white">Compliance Summary</h2>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            Indicator-level assessment against DPDP Rules, 2025.
          </p>
        </header>
        <div className="overflow-x-auto px-2 pb-4">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="border-b border-border text-[0.7rem] uppercase tracking-[0.14em] text-[var(--color-text-faint)]">
                <th className="px-4 py-3 font-semibold">Indicator</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold">Confidence</th>
                <th className="px-4 py-3 font-semibold">Rule Reference</th>
                <th className="px-4 py-3 font-semibold">Points</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.key} className="border-b border-border-light transition-colors hover:bg-white/[0.02]">
                  <td className="px-4 py-3 font-medium text-[var(--color-text)]">{row.indicator}</td>
                  <td className="px-4 py-3">
                    <span className={`status-pill status-${row.status.toLowerCase()}`}>
                      {row.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-[var(--color-text-muted)]">{row.rule}</td>
                  <td className="px-4 py-3 font-mono tabular-nums text-[var(--color-text)]">
                    {row.points} / {row.max_points}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </motion.section>

      {Object.keys(data.score_breakdown).length > 0 && (
        <motion.section {...reveal} className="panel">
          <header className="panel-header">
            <h2 className="font-display text-lg font-bold tracking-tight text-white">Score Breakdown</h2>
          </header>
          <ul className="divide-y divide-border-light px-4 md:px-7 pb-5">
            {Object.entries(data.score_breakdown).map(([item, points]) => {
              const { title, confidence } = parseScoreBreakdownLabel(item);
              return (
                <li key={item} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 py-3 text-sm">
                  <span className="min-w-0 flex-1 font-medium text-[var(--color-text)]">{title}</span>
                  <span className="inline-flex items-center rounded-full border border-mint/30 bg-mint/10 px-2 py-0.5 text-xs font-bold tabular-nums text-mint-soft">
                    +{points} pts
                  </span>
                  {data.rule_citations[item] && (
                    <span className="font-mono text-xs text-[var(--color-text-faint)]">{data.rule_citations[item]}</span>
                  )}
                  {confidence && (
                    <span className="group/conf relative ml-auto inline-flex shrink-0">
                      <button
                        type="button"
                        className="grid h-7 w-7 place-items-center rounded-full border border-[var(--line)] text-[var(--text-faint)] transition-colors hover:border-[var(--accent)]/40 hover:text-[var(--accent-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/40"
                        aria-label={`Confidence ${confidence}`}
                      >
                        <Info className="h-3.5 w-3.5" strokeWidth={2} />
                      </button>
                      <span
                        role="tooltip"
                        className="pointer-events-none absolute bottom-full right-0 z-30 mb-2 hidden w-[15.5rem] rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3.5 py-3 text-left shadow-[0_12px_32px_-12px_rgba(0,0,0,0.35)] group-hover/conf:block group-focus-within/conf:block"
                      >
                        <span className="block text-[0.75rem] font-semibold leading-snug text-[var(--text)]">
                          Confidence: {confidence}
                        </span>
                        <span className="mt-1.5 block text-[0.7rem] font-normal leading-relaxed text-[var(--text-muted)]">
                          How sure the scanner is about this finding from the policy text. Higher means clearer evidence; lower means the wording was incomplete or unclear.
                        </span>
                      </span>
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </motion.section>
      )}

      <motion.section {...reveal} className="panel">
        <header className="panel-header">
          <h2 className="font-display text-lg font-bold tracking-tight text-white">Key Findings</h2>
        </header>
        <div className="report-page__key-findings grid grid-cols-3 gap-2 px-4 pb-4 md:gap-4 md:px-7 md:pb-6">
          {[
            {
              label: "Privacy Policy",
              value: report.privacy_policy_found ? "Present" : "Not Found",
              ok: report.privacy_policy_found,
            },
            {
              label: "Cookie Banner",
              value: report.cookie_banner_found ? "Detected" : "Not Detected",
              ok: report.cookie_banner_found,
            },
            {
              label: "Grievance Contact",
              value: report.grievance_officer_contact || "Not Identified",
              ok: Boolean(report.grievance_officer_contact),
            },
          ].map((stat) => (
            <div
              key={stat.label}
              className="report-page__stat group rounded-xl border border-border bg-white/[0.02] p-2.5 transition-all duration-300 md:rounded-2xl md:p-4 md:hover:-translate-y-0.5 md:hover:border-border-strong"
            >
              <span className="text-[0.55rem] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-faint)] md:text-[0.65rem] md:tracking-[0.16em]">
                {stat.label}
              </span>
              <p
                className={`mt-1.5 flex flex-col items-start gap-1 text-[0.6875rem] font-semibold leading-tight md:mt-2 md:flex-row md:items-center md:gap-2 md:text-sm ${
                  stat.ok ? "text-mint-soft" : "text-rose-soft"
                }`}
              >
                <span
                  className={`grid h-6 w-6 shrink-0 place-items-center rounded-md md:h-7 md:w-7 md:rounded-lg ${
                    stat.ok ? "bg-mint/15" : "bg-rose/15"
                  }`}
                >
                  {stat.ok ? <ShieldCheck className="h-3.5 w-3.5 md:h-4 md:w-4" /> : <ShieldX className="h-3.5 w-3.5 md:h-4 md:w-4" />}
                </span>
                <span className="break-all">{stat.value}</span>
              </p>
            </div>
          ))}
        </div>
      </motion.section>

      {data.findings.length > 0 && (
        <motion.section {...reveal} className="panel">
          <header className="panel-header">
            <h2 className="font-display text-lg font-bold tracking-tight text-white">Detailed Analysis</h2>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">
              Expert assessment by indicator with policy excerpts and recommendations.
            </p>
          </header>
          <div className="space-y-4 px-4 md:px-7 pb-6">
            {data.findings.map((item, index) => (
              <motion.article
                key={item.key}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ delay: Math.min(index * 0.02, 0.12), duration: 0.2 }}
                className={`relative overflow-hidden rounded-2xl border border-border bg-white/[0.02] p-5 transition-colors hover:bg-white/[0.035] before:absolute before:inset-y-0 before:left-0 before:w-[3px] before:content-[''] ${
                  item.status === "Found"
                    ? "before:bg-mint"
                    : item.status === "Partial"
                      ? "before:bg-amber"
                      : "before:bg-rose"
                }`}
              >
                <header className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-display font-bold text-white">{item.indicator}</h3>
                  <span className={`status-pill status-${item.status.toLowerCase()}`}>
                    {item.status}
                  </span>
                </header>
                <p className="mb-3 font-mono text-xs text-[var(--color-text-faint)]">
                  {item.rule}
                </p>
                {item.analysis && <p className="text-sm leading-relaxed text-[var(--color-text)]">{item.analysis}</p>}
                {item.excerpt &&
                  item.excerpt !== "[Excerpt not verifiable in original text]" &&
                  item.excerpt !== "Relevant text not located automatically" && (
                    <blockquote className="mt-3 rounded-r-lg border-l-[3px] border-border-strong bg-white/[0.03] px-3 py-2 text-sm italic text-[var(--color-text-muted)]">
                      {item.excerpt}
                    </blockquote>
                  )}
                {item.recommendation &&
                  (item.status === "Missing" || item.status === "Partial") && (
                    <div className="mt-3 flex gap-2 rounded-xl border border-cyan/25 bg-cyan/[0.07] px-3 py-2.5 text-sm text-[var(--color-text)]">
                      <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-cyan" />
                      <span><strong className="font-semibold text-cyan-soft">Recommended action:</strong> {item.recommendation}</span>
                    </div>
                  )}
              </motion.article>
            ))}
          </div>
        </motion.section>
      )}

      {report.errors && report.errors.length > 0 && (
        <motion.section {...reveal} className="panel relative overflow-hidden">
          <span className="absolute inset-y-0 left-0 w-[3px] bg-amber" aria-hidden />
          <header className="panel-header">
            <h2 className="font-display text-lg font-bold tracking-tight text-white">Errors &amp; Warnings</h2>
          </header>
          <ul className="list-disc space-y-1 px-10 pb-6 text-sm text-[var(--color-text-muted)] marker:text-amber">
            {report.errors.map((err) => (
              <li key={err}>{err}</li>
            ))}
          </ul>
        </motion.section>
      )}

      <details className="panel group">
        <summary className="flex cursor-pointer items-center justify-between px-4 md:px-7 py-4 font-display font-semibold text-white marker:content-none">
          <span className="inline-flex items-center gap-2">
            <FileText className="h-4 w-4 text-mint" />
            Technical Details
          </span>
          <ChevronDown className="h-4 w-4 text-[var(--color-text-faint)] transition-transform duration-300 group-open:rotate-180" />
        </summary>
        <div className="border-t border-border-light px-4 md:px-7 pb-6 pt-4 text-sm text-[var(--color-text-muted)]">
          <h3 className="mb-2 font-semibold text-[var(--color-text)]">Scan Execution Steps</h3>
          <ol className="mb-6 list-decimal space-y-1 pl-5 marker:text-[var(--color-text-faint)]">
            {scanSteps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          {Object.keys(policyUrls).length > 0 && (
            <>
              <h3 className="mb-2 font-semibold text-[var(--color-text)]">
                {report.scraping_method === "pdf_upload"
                  ? "Policy Documents"
                  : "Discovered Policy URLs"}
              </h3>
              <dl className="mb-6 grid gap-2 sm:grid-cols-[auto_1fr]">
                {Object.entries(policyUrls).map(([ptype, purl]) => (
                  <div key={ptype} className="contents">
                    <dt className="font-medium capitalize text-[var(--color-text)]">{ptype}</dt>
                    <dd>
                      {purl?.startsWith("Uploaded:") ? (
                        purl
                      ) : safeHttpUrl(purl) ? (
                        <a
                          href={safeHttpUrl(purl)!}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="break-all text-mint-soft hover:text-mint hover:underline"
                        >
                          {purl}
                        </a>
                      ) : purl ? (
                        <span className="break-all text-[var(--color-text-muted)]">{purl}</span>
                      ) : (
                        "Not found"
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            </>
          )}
          <h3 className="mb-2 font-semibold text-[var(--color-text)]">Text Analysis</h3>
          <p>
            Policy text length:{" "}
            {Number(data.analysis_details.policy_text_length ?? 0).toLocaleString()} characters
          </p>
          <p>Chunks analyzed: {String(data.analysis_details.chunks_analyzed ?? 0)}</p>
        </div>
      </details>
        </>
      )}
    </motion.div>
  );
}
