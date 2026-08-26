"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  FileText,
  Globe,
  Link2,
  Loader2,
  Radar,
  Upload,
} from "lucide-react";
import { clientApiBase, userApiHeaders } from "@/lib/api";
import { signalRouteStart } from "@/lib/route-progress";
import { validateOptionalScanUrlClient, validateScanUrlClient } from "@/lib/security/validate-url";
import { firstZodError, pdfReferenceSchema, scanUrlPayloadSchema } from "@/lib/security/schemas";
import { supabaseConfigured } from "@/lib/supabase/client";
import { saveUserScanClient } from "@/lib/supabase/scans";
import type { InputMode, ScanStatusResponse } from "@/lib/types";
import { AssessmentDisclaimerModal } from "@/components/home/AssessmentDisclaimerModal";
import { MobileScanSubmitBar } from "@/components/home/MobileScanSubmitBar";
import { ScanQuotaBanner } from "@/components/home/ScanQuotaBanner";
import { TurnstileWidget } from "@/components/security/TurnstileWidget";
import { useAuth } from "@/contexts/AuthContext";
import { useSessionReady } from "@/contexts/SessionReadyContext";
import { usePaidScanCheckout } from "@/hooks/usePaidScanCheckout";
import { turnstileEnabled } from "@/lib/captcha";
import { pollScanStatus } from "@/lib/scan-poll";

const ACTIVE_SCAN_KEY = "dpdp:active-scan";

const MODES: { value: InputMode; icon: typeof Globe; title: string; subtitle: string }[] = [
  { value: "url", icon: Globe, title: "Website URL", subtitle: "Discover or link to policies online" },
  { value: "pdf", icon: Upload, title: "Upload PDFs", subtitle: "Submit privacy, terms & cookie documents" },
];

export function ScanForm() {
  const router = useRouter();
  const { openAuth, user, session, loading: authLoading, configured } = useAuth();
  const { ready: sessionReady, quotaLoading, quota, proActivating, refreshQuota } = useSessionReady();
  const {
    checkout: payForScan,
    loading: payForScanLoading,
    error: payForScanError,
    SummaryModal: paidScanSummaryModal,
  } = usePaidScanCheckout();
  const [mode, setMode] = useState<InputMode>("url");
  const [submitting, setSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [disclaimerOpen, setDisclaimerOpen] = useState(false);
  const [captchaToken, setCaptchaToken] = useState("");
  const [captchaReset, setCaptchaReset] = useState(0);
  const formRef = useRef<HTMLFormElement>(null);
  const lastScanLabel = useRef("");

  const needsCaptcha =
    turnstileEnabled() &&
    Boolean(quota?.signed_in) &&
    !quota?.premium_free_access &&
    // Captcha only for free preview — Pilot daily + prepaid skip
    !(quota?.has_pilot && (quota?.pilot_scans_remaining ?? 0) > 0) &&
    !(quota?.has_pro && (quota?.pro_scans_remaining ?? 0) > 0) &&
    !((quota?.prepaid_scans ?? quota?.scan_credits ?? 0) > 0);

  function resetCaptcha() {
    setCaptchaToken("");
    setCaptchaReset((n) => n + 1);
  }

  function requireSignedIn(): boolean {
    if (!configured) {
      setError("Sign-in is not configured. Contact the administrator.");
      return false;
    }
    if (!user) {
      setError("Sign in to run an assessment.");
      openAuth("signin");
      return false;
    }
    return true;
  }

  function promptPaidScan(message?: string) {
    setError(
      message ||
        "You've used all free scans. Purchase a scan credit to run a new assessment.",
    );
    void payForScan();
  }

  function handleScanStartError(data: { error?: string; code?: string }) {
    if (data.code === "SIGN_IN_REQUIRED") {
      setError(data.error || "Sign in to continue scanning.");
      openAuth("signin");
    } else if (data.code === "SCAN_QUOTA_EXCEEDED") {
      promptPaidScan(data.error);
    } else {
      setError(data.error || "Failed to start assessment.");
    }
    setSubmitting(false);
    sessionStorage.removeItem(ACTIVE_SCAN_KEY);
  }

  const persistScanIfAuthed = useCallback(async (data: ScanStatusResponse) => {
    if (!supabaseConfigured() || !data.report_id || !user?.id) return;
    try {
      const result = await saveUserScanClient(
        user.id,
        {
          report_id: data.report_id,
          url: data.url || lastScanLabel.current,
          score: data.score ?? 0,
          verdict: data.verdict ?? "",
        },
        session?.access_token,
      );
      if (result.ok) {
        window.dispatchEvent(new Event("scan-history-updated"));
      }
    } catch {
      /* non-fatal */
    }
  }, [user?.id, session?.access_token]);

  const finishScan = useCallback(
    async (data: ScanStatusResponse) => {
      setProgress(100);
      setStatusMessage("Assessment complete — opening report…");
      await persistScanIfAuthed(data);
      void refreshQuota({ blocking: false });
      sessionStorage.removeItem(ACTIVE_SCAN_KEY);
      signalRouteStart();
      if (data.redirect) {
        router.push(data.redirect);
      } else if (data.report_id) {
        router.push(`/report/${data.report_id}`);
      }
    },
    [router, persistScanIfAuthed, refreshQuota],
  );

  const beginPolling = useCallback(
    (jobId: string) => {
      void pollScanStatus(
        () =>
          fetch(`${clientApiBase}/scan/${jobId}`, {
            credentials: "include",
            headers: userApiHeaders(user?.id, session?.access_token),
          }),
        {
          onProgress: (data) => {
            const pct = Math.max(0, Math.min(100, Number(data.progress) || 0));
            setProgress(pct);
            setStatusMessage(data.message?.trim() || "Processing…");
          },
          onRetry: (message) => setStatusMessage(message),
          onComplete: (data) => void finishScan(data),
          onError: (message) => {
            setError(message);
            setSubmitting(false);
            sessionStorage.removeItem(ACTIVE_SCAN_KEY);
          },
        },
      );
    },
    [user?.id, finishScan],
  );

  useEffect(() => {
    if (!sessionReady || !user) return;
    const raw = sessionStorage.getItem(ACTIVE_SCAN_KEY);
    if (!raw) return;

    try {
      const parsed = JSON.parse(raw) as { jobId?: string; startedAt?: number };
      if (!parsed.jobId || !parsed.startedAt || Date.now() - parsed.startedAt > 30 * 60 * 1000) {
        sessionStorage.removeItem(ACTIVE_SCAN_KEY);
        return;
      }
      setSubmitting(true);
      setProgress((prev) => (prev > 0 ? prev : 5));
      setStatusMessage("Reconnecting to scan in progress…");
      beginPolling(parsed.jobId);
    } catch {
      sessionStorage.removeItem(ACTIVE_SCAN_KEY);
    }
  }, [sessionReady, user, beginPolling]);

  function validateForm(form: HTMLFormElement): boolean {
    setError("");

    if (mode === "pdf") {
      const reference = (form.elements.namedItem("reference") as HTMLInputElement).value;
      const refCheck = pdfReferenceSchema.safeParse(reference);
      if (!refCheck.success) {
        setError(firstZodError(refCheck.error));
        return false;
      }
      const privacyFile = (form.elements.namedItem("privacy_pdf") as HTMLInputElement).files?.[0];

      if (!privacyFile) {
        setError("Please upload a Privacy Policy PDF.");
        return false;
      }
      return true;
    }

    const urlInput = (form.elements.namedItem("url") as HTMLInputElement).value;
    const privacyRaw = (form.elements.namedItem("privacy_url") as HTMLInputElement).value;
    const termsRaw = (form.elements.namedItem("terms_url") as HTMLInputElement).value;
    const cookieRaw = (form.elements.namedItem("cookie_url") as HTMLInputElement).value;

    const payloadCheck = scanUrlPayloadSchema.safeParse({
      url: urlInput,
      privacy_url: privacyRaw || undefined,
      terms_url: termsRaw || undefined,
      cookie_url: cookieRaw || undefined,
    });
    if (!payloadCheck.success) {
      setError(firstZodError(payloadCheck.error));
      return false;
    }

    const urlCheck = validateScanUrlClient(payloadCheck.data.url, "website URL");
    if (!urlCheck.ok) {
      setError(urlCheck.error);
      return false;
    }

    const optionalFields = [
      { name: "privacy_url", label: "Privacy Policy URL" },
      { name: "terms_url", label: "Terms of Service URL" },
      { name: "cookie_url", label: "Cookie Policy URL" },
    ] as const;

    for (const field of optionalFields) {
      const raw = (form.elements.namedItem(field.name) as HTMLInputElement).value;
      const check = validateOptionalScanUrlClient(raw, field.label);
      if (!check.ok) {
        setError(check.error);
        return false;
      }
    }

    return true;
  }

  async function startAssessment() {
    const form = formRef.current;
    if (!form) return;
    if (!requireSignedIn()) return;

    if (quota && quota.signed_in && !quota.premium_free_access && !quota.can_scan) {
      promptPaidScan();
      return;
    }

    if (needsCaptcha && !captchaToken) {
      setError("Please complete the CAPTCHA before starting an assessment.");
      return;
    }

    setDisclaimerOpen(false);
    setError("");
    setSubmitting(true);
    setProgress(0);
    setStatusMessage("Initializing scan…");

    if (mode === "pdf") {
      const referenceRaw = (form.elements.namedItem("reference") as HTMLInputElement).value;
      const refCheck = pdfReferenceSchema.safeParse(referenceRaw);
      if (!refCheck.success) {
        setError(firstZodError(refCheck.error));
        setSubmitting(false);
        return;
      }
      const privacyFile = (form.elements.namedItem("privacy_pdf") as HTMLInputElement).files?.[0]!;

      lastScanLabel.current = refCheck.data;

      const formData = new FormData();
      formData.append("reference", refCheck.data);
      formData.append("privacy_pdf", privacyFile);
      if (captchaToken) formData.append("captcha_token", captchaToken);

      const termsFile = (form.elements.namedItem("terms_pdf") as HTMLInputElement).files?.[0];
      const cookieFile = (form.elements.namedItem("cookie_pdf") as HTMLInputElement).files?.[0];
      if (termsFile) formData.append("terms_pdf", termsFile);
      if (cookieFile) formData.append("cookie_pdf", cookieFile);

      try {
        const res = await fetch(`${clientApiBase}/scan`, {
          method: "POST",
          credentials: "include",
          headers: userApiHeaders(user?.id, session?.access_token),
          body: formData,
        });
        const data = await res.json();
        if (!res.ok) {
          resetCaptcha();
          handleScanStartError(data);
          return;
        }
        sessionStorage.setItem(
          ACTIVE_SCAN_KEY,
          JSON.stringify({ jobId: data.job_id, startedAt: Date.now() }),
        );
        beginPolling(data.job_id);
      } catch {
        resetCaptcha();
        setError("Network error. Please check your connection and try again.");
        setSubmitting(false);
        sessionStorage.removeItem(ACTIVE_SCAN_KEY);
      }
      return;
    }

    const urlInput = (form.elements.namedItem("url") as HTMLInputElement).value;
    const urlCheck = validateScanUrlClient(urlInput, "website URL");
    if (!urlCheck.ok) {
      setError(urlCheck.error);
      setSubmitting(false);
      return;
    }
    lastScanLabel.current = urlCheck.url;

    const optionalFields = [
      { name: "privacy_url", label: "Privacy Policy URL" },
      { name: "terms_url", label: "Terms of Service URL" },
      { name: "cookie_url", label: "Cookie Policy URL" },
    ] as const;

    const payload: {
      input_mode: "url";
      url: string;
      privacy_url: string;
      terms_url: string;
      cookie_url: string;
      captcha_token?: string;
    } = {
      input_mode: "url",
      url: urlCheck.url,
      privacy_url: "",
      terms_url: "",
      cookie_url: "",
    };
    if (captchaToken) payload.captcha_token = captchaToken;

    for (const field of optionalFields) {
      const raw = (form.elements.namedItem(field.name) as HTMLInputElement).value;
      const check = validateOptionalScanUrlClient(raw, field.label);
      if (!check.ok) {
        setError(check.error);
        setSubmitting(false);
        return;
      }
      if (check.url) {
        payload[field.name] = check.url;
      }
    }

    try {
      const res = await fetch(`${clientApiBase}/scan`, {
        method: "POST",
        credentials: "include",
        headers: {
          ...userApiHeaders(user?.id, session?.access_token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        resetCaptcha();
        handleScanStartError(data);
        return;
      }
      sessionStorage.setItem(
        ACTIVE_SCAN_KEY,
        JSON.stringify({ jobId: data.job_id, startedAt: Date.now() }),
      );
      beginPolling(data.job_id);
    } catch {
      resetCaptcha();
      setError("Network error. Please check your connection and try again.");
      setSubmitting(false);
      sessionStorage.removeItem(ACTIVE_SCAN_KEY);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting || authLoading || !sessionReady) return;
    if (!requireSignedIn()) return;
    if (quota && quota.signed_in && !quota.premium_free_access && !quota.can_scan) {
      promptPaidScan();
      return;
    }
    if (needsCaptcha && !captchaToken) {
      setError("Please complete the CAPTCHA before starting an assessment.");
      return;
    }
    if (!validateForm(event.currentTarget)) return;
    setDisclaimerOpen(true);
  }

  return (
    <>
      <ScanQuotaBanner
        quota={quota}
        loading={authLoading || (quotaLoading && !quota)}
        proActivating={proActivating}
        onSignIn={() => openAuth("signin")}
        onPayForScan={payForScan}
        payForScanLoading={payForScanLoading}
      />
      {payForScanError && (
        <p className="mb-2 px-4 text-sm text-rose-soft md:mx-7 md:px-0">{payForScanError}</p>
      )}
      <form
        id="scan-assessment-form"
        ref={formRef}
        method="post"
        onSubmit={handleSubmit}
        className={`px-4 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] pt-1 md:px-7 md:pb-7 md:pt-0${!sessionReady || payForScanLoading ? " pointer-events-none opacity-60" : ""}`}
        noValidate
        suppressHydrationWarning
        aria-busy={!sessionReady}
      >
      {/* Document Source — sliding segmented control */}
      <div className="pb-5 pt-4 md:pb-6 md:pt-5">
        <h3 className="mb-3 text-[0.7rem] font-bold uppercase tracking-[0.18em] text-[var(--color-text-faint)]">
          Document Source
        </h3>
        <div
          className="relative grid grid-cols-2 gap-1.5 rounded-2xl border border-border bg-[var(--surface-2)] p-1.5"
          role="radiogroup"
          aria-label="Document source"
        >
          {MODES.map((m) => {
            const Icon = m.icon;
            const active = mode === m.value;
            return (
              <label
                key={m.value}
                className="relative flex min-h-[3.25rem] cursor-pointer flex-col justify-center gap-0.5 rounded-xl px-3 py-3.5 transition-colors md:min-h-0 md:px-4 md:py-3"
              >
                <input
                  type="radio"
                  name="input_mode"
                  value={m.value}
                  checked={active}
                  onChange={() => setMode(m.value)}
                  className="sr-only"
                />
                {active && (
                  <motion.span
                    layoutId="mode-pill"
                    transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    className="absolute inset-0 rounded-xl border border-mint/30 bg-mint/[0.10] shadow-[0_0_16px_-10px_rgba(255,122,24,0.4)]"
                  />
                )}
                <span
                  className={`relative z-10 inline-flex items-center gap-1.5 text-sm font-semibold transition-colors md:gap-2 ${
                    active ? "text-[var(--color-text)]" : "text-[var(--color-text-muted)]"
                  }`}
                >
                  <Icon className={`h-4 w-4 shrink-0 ${active ? "text-mint" : ""}`} />
                  <span className="leading-tight">{m.title}</span>
                </span>
                <span className="relative z-10 hidden text-[0.8125rem] text-[var(--color-text-faint)] md:block">
                  {m.subtitle}
                </span>
              </label>
            );
          })}
        </div>
      </div>

      <AnimatePresence mode="wait">
        {mode === "url" ? (
          <motion.div
            key="url-fields"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="flex flex-col gap-6"
          >
            <div>
              <h3 className="mb-3 hidden text-[0.7rem] font-bold uppercase tracking-[0.18em] text-[var(--color-text-faint)] md:block">
                Target Website
              </h3>
              <label htmlFor="url" className="mb-1.5 block text-sm font-semibold text-[var(--color-navy-light)]">
                Website URL
              </label>
              <input
                type="url"
                id="url"
                name="url"
                className="form-input"
                placeholder="https://www.example.com"
                autoComplete="url"
                required={mode === "url"}
              />
              <span className="mt-1.5 block text-[0.8125rem] text-[var(--color-text-faint)]">
                Enter the homepage URL of the organisation to assess.
              </span>
            </div>

            <div className="mobile-policy-card relative overflow-hidden rounded-2xl border border-gold/25 bg-[rgba(212,180,131,0.05)] p-4 md:p-5">
              <span className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-gold-light to-gold" />
              <h3 className="mb-2 flex flex-wrap items-center gap-2 font-display text-[0.95rem] font-bold text-[var(--color-text)]">
                <Link2 className="hidden h-4 w-4 text-gold-light md:block" />
                Direct Policy Links
                <span className="rounded-full border border-gold/40 bg-gold/15 px-2 py-0.5 font-sans text-[0.625rem] font-bold uppercase tracking-wider text-gold-light">
                  Recommended
                </span>
              </h3>
              <p className="mb-5 text-[0.8125rem] leading-relaxed text-[var(--color-text-muted)]">
                Paste direct URLs for the most accurate assessment. Automatic discovery often misses
                policies on government and enterprise sites (e.g.{" "}
                <code className="rounded bg-white/[0.06] px-1 font-mono text-[0.7rem] text-mint-soft">
                  https://www.digilocker.gov.in/digilocker-policy
                </code>
                ).
              </p>
              {(["privacy_url", "terms_url", "cookie_url"] as const).map((field, i) => {
                const labels = ["Privacy Policy URL", "Terms of Service URL", "Cookie Policy URL"];
                return (
                  <div key={field} className={i < 2 ? "mb-4" : ""}>
                    <label htmlFor={field} className="mb-1.5 block text-[0.8125rem] font-semibold text-[var(--color-navy-light)]">
                      {labels[i]}
                    </label>
                    <input
                      type="url"
                      id={field}
                      name={field}
                      className="form-input"
                      placeholder={`https://www.example.com/${field.replace("_url", "").replace("_", "-")}`}
                    />
                  </div>
                );
              })}
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="pdf-fields"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
          >
            <h3 className="mb-3 text-[0.7rem] font-bold uppercase tracking-[0.18em] text-[var(--color-text-faint)]">
              Uploaded Documents
            </h3>
            <div className="mb-4">
              <label htmlFor="reference" className="mb-1.5 block text-[0.8125rem] font-semibold text-[var(--color-navy-light)]">
                Organisation / Reference
              </label>
              <input
                type="text"
                id="reference"
                name="reference"
                className="form-input"
                placeholder="Acme Corp or https://www.example.com"
                required={mode === "pdf"}
              />
              <span className="mt-1.5 block text-[0.8125rem] text-[var(--color-text-faint)]">
                Shown on the compliance report as the subject of assessment.
              </span>
            </div>
            {(
              [
                ["privacy_pdf", "Privacy Policy PDF", true],
                ["terms_pdf", "Terms of Service PDF", false],
                ["cookie_pdf", "Cookie Policy PDF", false],
              ] as const
            ).map(([id, label, required]) => (
              <div key={id} className="mb-4">
                <label htmlFor={id} className="mb-1.5 flex items-center gap-1.5 text-[0.8125rem] font-semibold text-[var(--color-navy-light)]">
                  <FileText className="h-3.5 w-3.5 text-[var(--color-text-faint)]" />
                  {label}
                  {required && <span className="text-rose"> *</span>}
                </label>
                <input
                  type="file"
                  id={id}
                  name={id}
                  accept="application/pdf,.pdf"
                  className="form-input"
                  required={required && mode === "pdf"}
                />
              </div>
            ))}
            <p className="text-[0.8125rem] text-[var(--color-text-faint)]">
              Upload all related policy documents you have. Privacy Policy is required; Terms and Cookie
              policies are optional. Maximum 15 MB per file.
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {needsCaptcha && (
        <div className="mt-5">
          <TurnstileWidget
            resetSignal={captchaReset}
            onToken={setCaptchaToken}
            onExpire={() => setCaptchaToken("")}
            onError={() => setCaptchaToken("")}
          />
        </div>
      )}

      <div className="mt-7 hidden border-t border-border-light pt-6 md:block">
        <button
          type="submit"
          className="btn btn-primary group w-full gap-2 sm:w-auto"
          disabled={submitting || payForScanLoading || !sessionReady}
        >
          {!submitting && (
            <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/40 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
          )}
          {submitting || payForScanLoading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              {payForScanLoading ? "Opening checkout…" : "Assessment Running…"}
            </>
          ) : (
            "Commence Assessment"
          )}
        </button>
      </div>

      <AnimatePresence>
        {submitting && (
          <motion.div
            key="scan-progress"
            initial={{ opacity: 0, y: 8, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-5 overflow-hidden rounded-2xl border border-mint/25 bg-[rgba(255,122,24,0.05)]"
            role="status"
            aria-live="polite"
            aria-valuenow={progress}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div className="flex items-center gap-3 px-4 py-3.5 md:gap-4 md:px-5 md:py-4">
              <Loader2 className="h-6 w-6 shrink-0 animate-spin text-mint md:hidden" aria-hidden />
              <div className="relative hidden h-14 w-14 shrink-0 place-items-center md:grid">
                <span className="absolute inset-0 animate-pulse-ring rounded-full bg-mint/15" />
                <span
                  className="absolute inset-1 animate-pulse-ring rounded-full bg-mint/10"
                  style={{ animationDelay: "1.2s" }}
                />
                <span className="absolute inset-0 overflow-hidden rounded-full">
                  <span
                    className="absolute inset-0 animate-sweep"
                    style={{
                      background:
                        "conic-gradient(from 0deg, transparent 0deg, rgba(255,122,24,0.55) 70deg, transparent 130deg)",
                    }}
                  />
                </span>
                <span className="absolute inset-0 rounded-full border border-mint/30" />
                <Radar className="relative h-5 w-5 text-mint" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm font-semibold text-[var(--color-text)]">{statusMessage || "Processing…"}</p>
                  <span className="shrink-0 font-mono text-xs font-bold tabular-nums text-mint-soft">
                    {progress}%
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
                  Running DPDP compliance analysis — this may take a minute.
                </p>
                <div className="relative mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
                  <motion.span
                    className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-mint/70 via-mint to-mint-soft/80"
                    initial={false}
                    animate={{ width: `${Math.max(progress, progress > 0 ? 8 : 0)}%` }}
                    transition={{ duration: 0.35, ease: "easeOut" }}
                  />
                  {progress < 100 && (
                    <motion.span
                      className="absolute inset-y-0 w-1/4 rounded-full bg-gradient-to-r from-transparent via-white/30 to-transparent"
                      animate={{ x: ["-110%", "430%"] }}
                      transition={{ repeat: Infinity, duration: 1.4, ease: "easeInOut" }}
                    />
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {error && (
          <motion.div
            key="scan-error"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-4 flex items-start gap-2 rounded-2xl border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose-soft"
            role="alert"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            {error}
          </motion.div>
        )}
      </AnimatePresence>
    </form>

      <AssessmentDisclaimerModal
        open={disclaimerOpen}
        onCancel={() => setDisclaimerOpen(false)}
        onConfirm={() => void startAssessment()}
      />
      {paidScanSummaryModal}
      <MobileScanSubmitBar
        formId="scan-assessment-form"
        submitting={submitting}
        payForScanLoading={payForScanLoading}
        sessionReady={sessionReady}
      />
    </>
  );
}
