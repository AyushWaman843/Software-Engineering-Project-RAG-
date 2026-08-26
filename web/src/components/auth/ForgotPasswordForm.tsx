"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { emailSchema } from "@/lib/security/schemas";

interface ForgotPasswordFormProps {
  onBack?: () => void;
  showBackLink?: boolean;
}

export function ForgotPasswordForm({ onBack, showBackLink = true }: ForgotPasswordFormProps) {
  const { requestPasswordReset } = useAuth();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setInfo(null);

    const parsed = emailSchema.safeParse(email.trim());
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Enter a valid email address.");
      return;
    }

    setBusy(true);
    const result = await requestPasswordReset(parsed.data);
    setBusy(false);

    if (result.status === "error") {
      setError(result.message);
      return;
    }

    setSent(true);
    setInfo(
      result.message ??
        "If an account with that email exists, we've sent a password reset link. Check your inbox and spam folder.",
    );
  }

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="auth-modal-form" suppressHydrationWarning>
      <p className="text-sm leading-relaxed text-[var(--color-text-muted)]">
        Enter the email address for your account. We&apos;ll send a secure link to choose a new password.
      </p>

      <div>
        <label htmlFor="forgot-email" className="auth-modal-label">
          Email address
        </label>
        <input
          id="forgot-email"
          type="email"
          required
          autoComplete="email"
          className="form-input"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={sent}
          suppressHydrationWarning
        />
      </div>

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

      <button type="submit" className="btn btn-primary auth-modal-submit" disabled={busy || sent}>
        {busy && <Loader2 className="h-4 w-4 animate-spin" />}
        {busy ? "Sending…" : sent ? "Email sent" : "Send reset link"}
      </button>

      {showBackLink && (
        onBack ? (
          <button type="button" className="btn btn-secondary w-full text-xs" onClick={onBack}>
            Back to sign in
          </button>
        ) : (
          <p className="text-center text-xs text-[var(--color-text-muted)]">
            <Link href="/" className="text-mint-soft hover:underline">
              Back to home
            </Link>
          </p>
        )
      )}
    </form>
  );
}
