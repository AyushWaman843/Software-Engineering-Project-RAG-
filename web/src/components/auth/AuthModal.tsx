"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2, LogIn, Mail, ShieldCheck, UserPlus, X } from "lucide-react";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";
import { TurnstileWidget } from "@/components/security/TurnstileWidget";
import { useAuth } from "@/contexts/AuthContext";
import { turnstileEnabled } from "@/lib/captcha";
import {
  firstZodError,
  signInFormSchema,
  signUpFormSchema,
} from "@/lib/security/schemas";

interface AuthModalProps {
  open: boolean;
  onClose: () => void;
  initialMode?: "signin" | "signup" | "forgot";
}

export function AuthModal({ open, onClose, initialMode = "signin" }: AuthModalProps) {
  const { signIn, signUp, resendConfirmation, configured } = useAuth();
  const [mounted, setMounted] = useState(false);
  const [mode, setMode] = useState<"signin" | "signup" | "forgot">(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [ageConfirmed, setAgeConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [awaitingConfirmation, setAwaitingConfirmation] = useState(false);
  const [busy, setBusy] = useState(false);
  const [captchaToken, setCaptchaToken] = useState("");
  const [captchaReset, setCaptchaReset] = useState(0);
  const emailRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (open) {
      setMode(initialMode);
      setError(null);
      setInfo(null);
      setAwaitingConfirmation(false);
      return;
    }

    setEmail("");
    setPassword("");
    setAgeConfirmed(false);
    setError(null);
    setInfo(null);
    setAwaitingConfirmation(false);
    setCaptchaToken("");
    setCaptchaReset((n) => n + 1);
    setMode("signin");
  }, [open, initialMode]);

  useEffect(() => {
    if (!open) return;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);

    const timer = window.setTimeout(() => emailRef.current?.focus(), 120);

    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKeyDown);
      window.clearTimeout(timer);
    };
  }, [open, onClose]);

  if (!configured || !mounted) return null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setInfo(null);
    setAwaitingConfirmation(false);
    setBusy(true);

    const trimmedEmail = email.trim();

    const parsed =
      mode === "signin"
        ? signInFormSchema.safeParse({ email: trimmedEmail, password })
        : signUpFormSchema.safeParse({ email: trimmedEmail, password, ageConfirmed });

    if (!parsed.success) {
      setBusy(false);
      setError(firstZodError(parsed.error));
      return;
    }

    if (mode === "signup" && turnstileEnabled() && !captchaToken) {
      setBusy(false);
      setError("Please complete the CAPTCHA before creating an account.");
      return;
    }

    const result =
      mode === "signin"
        ? await signIn(parsed.data.email, parsed.data.password)
        : await signUp(parsed.data.email, parsed.data.password, captchaToken || undefined);

    if (result.status === "ok") {
      // Do not clear the busy state or close the modal manually.
      // The global onAuthStateChange listener in AuthContext will close
      // the modal once the user session is completely loaded.
      return;
    }

    setBusy(false);
    if (mode === "signup") {
      setCaptchaToken("");
      setCaptchaReset((n) => n + 1);
    }

    if (result.status === "error") {
      setError(result.message);
      return;
    }

    if (result.status === "already_registered") {
      setError(result.message);
      setMode("signin");
      return;
    }

    if (result.status === "confirm_email") {
      setInfo(result.message);
      setAwaitingConfirmation(true);
      setMode("signin");
      setPassword("");
      return;
    }
  }

  async function handleResendConfirmation() {
    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setError("Enter your email address first.");
      return;
    }

    setError(null);
    setInfo(null);
    setBusy(true);

    const result = await resendConfirmation(trimmedEmail);
    setBusy(false);

    if (result.status === "error") {
      setError(result.message);
      return;
    }

    if (result.status === "confirm_email") {
      setInfo(result.message);
      setAwaitingConfirmation(true);
    }
  }

  function switchMode(next: "signin" | "signup" | "forgot") {
    setMode(next);
    setError(null);
    setInfo(null);
    setAwaitingConfirmation(false);
    setCaptchaToken("");
    setCaptchaReset((n) => n + 1);
    if (next !== "signup") {
      setAgeConfirmed(false);
    }
  }

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="auth-modal"
          className="auth-modal-overlay"
          role="presentation"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <button
            type="button"
            className="auth-modal-backdrop"
            aria-label="Close dialog"
            onClick={onClose}
          />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="auth-modal-title"
            className="auth-modal-card"
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 6 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="auth-modal-card__glow" aria-hidden />

            <button
              type="button"
              onClick={onClose}
              className="auth-modal-close"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>

            <div className="auth-modal-brand">
              <span className="auth-modal-brand__icon auth-modal-brand__icon--logo">
                <BrandLogo size={36} />
              </span>
              <div>
                <p className="auth-modal-brand__eyebrow">DPDP Scanner</p>
                <h2 id="auth-modal-title" className="auth-modal-brand__title">
                  {mode === "signin"
                    ? "Welcome back"
                    : mode === "signup"
                      ? "Create your account"
                      : "Reset your password"}
                </h2>
              </div>
            </div>

            {mode !== "forgot" && (
              <p className="auth-modal-subtitle">
                Save scan history, sync reports across devices, and pick up where you left off.
              </p>
            )}

            {mode !== "forgot" && (
              <div className="auth-modal-tabs" role="tablist" aria-label="Authentication mode">
                <button
                  type="button"
                  role="tab"
                  aria-selected={mode === "signin"}
                  className={`auth-modal-tab${mode === "signin" ? " auth-modal-tab--active" : ""}`}
                  onClick={() => switchMode("signin")}
                >
                  <LogIn className="h-3.5 w-3.5" />
                  Sign in
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={mode === "signup"}
                  className={`auth-modal-tab${mode === "signup" ? " auth-modal-tab--active" : ""}`}
                  onClick={() => switchMode("signup")}
                >
                  <UserPlus className="h-3.5 w-3.5" />
                  Sign up
                </button>
              </div>
            )}

            {mode === "forgot" ? (
              <ForgotPasswordForm onBack={() => switchMode("signin")} showBackLink />
            ) : (
            <form onSubmit={(e) => void handleSubmit(e)} className="auth-modal-form" suppressHydrationWarning>
              <div>
                <label htmlFor="auth-email" className="auth-modal-label">
                  Email address
                </label>
                <input
                  ref={emailRef}
                  id="auth-email"
                  type="email"
                  required
                  autoComplete="email"
                  className="form-input"
                  placeholder="you@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  suppressHydrationWarning
                />
              </div>
              <div>
                <label htmlFor="auth-password" className="auth-modal-label">
                  Password
                </label>
                <input
                  id="auth-password"
                  type="password"
                  required
                  minLength={6}
                  autoComplete={mode === "signin" ? "current-password" : "new-password"}
                  className="form-input"
                  placeholder={mode === "signup" ? "At least 6 characters" : "Your password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  suppressHydrationWarning
                />
                {mode === "signin" && (
                  <button
                    type="button"
                    className="mt-2 text-xs text-mint-soft hover:underline"
                    onClick={() => switchMode("forgot")}
                  >
                    Forgot password?
                  </button>
                )}
              </div>

              {mode === "signup" && (
                <label className="auth-modal-checkbox">
                  <input
                    type="checkbox"
                    checked={ageConfirmed}
                    onChange={(e) => setAgeConfirmed(e.target.checked)}
                    required
                    suppressHydrationWarning
                  />
                  <span>I confirm that I am at least 18 years of age.</span>
                </label>
              )}

              {mode === "signup" && turnstileEnabled() && (
                <TurnstileWidget
                  resetSignal={captchaReset}
                  onToken={setCaptchaToken}
                  onExpire={() => setCaptchaToken("")}
                  onError={() => setCaptchaToken("")}
                />
              )}

              {error && (
                <p className="auth-modal-alert auth-modal-alert--error" role="alert">
                  {error}
                </p>
              )}
              {info && (
                <p className="auth-modal-alert auth-modal-alert--success" role="status">
                  {info}
                </p>
              )}

              {awaitingConfirmation && (
                <button
                  type="button"
                  className="btn btn-secondary w-full gap-2 text-xs"
                  disabled={busy}
                  onClick={() => void handleResendConfirmation()}
                >
                  {busy ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Mail className="h-3.5 w-3.5" />
                  )}
                  Resend verification email
                </button>
              )}

              <button type="submit" className="btn btn-primary auth-modal-submit" disabled={busy}>
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : mode === "signin" ? (
                  <LogIn className="h-4 w-4" />
                ) : (
                  <UserPlus className="h-4 w-4" />
                )}
                {busy ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
              </button>
            </form>
            )}

            <p className="auth-modal-footnote">
              <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-mint-soft" />
              Credentials are stored securely via Supabase Auth.
            </p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
