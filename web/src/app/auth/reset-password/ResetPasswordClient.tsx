"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";
import { firstZodError, passwordSchema } from "@/lib/security/schemas";
import { withBasePath } from "@/lib/base-path";

export function ResetPasswordPage() {
  const { user, loading, configured, updatePassword } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const linkExpired = searchParams.get("error") === "link_expired";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sessionChecked, setSessionChecked] = useState(false);

  useEffect(() => {
    if (loading) return;

    if (!configured) {
      setSessionChecked(true);
      return;
    }

    if (user) {
      setSessionChecked(true);
      return;
    }

    const timer = window.setTimeout(() => {
      setSessionChecked(true);
    }, 1200);

    return () => window.clearTimeout(timer);
  }, [loading, configured, user]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setInfo(null);

    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    const parsed = passwordSchema.safeParse(password);
    if (!parsed.success) {
      setError(firstZodError(parsed.error));
      return;
    }

    setBusy(true);
    const result = await updatePassword(parsed.data);
    setBusy(false);

    if (result.status === "error") {
      setError(result.message);
      return;
    }

    setInfo(result.message ?? "Password updated successfully.");
    window.setTimeout(() => router.replace(`${withBasePath("/")}?auth=password_updated`), 1500);
  }

  if (!sessionChecked || loading) {
    return (
      <div className="panel mx-auto mt-16 max-w-md p-8 text-center">
        <Loader2 className="mx-auto h-8 w-8 animate-spin text-mint" />
        <p className="mt-4 text-sm text-[var(--color-text-muted)]">Verifying reset link…</p>
      </div>
    );
  }

  if (linkExpired || (!user && sessionChecked)) {
    return (
      <div className="panel mx-auto mt-16 max-w-md overflow-hidden">
        <header className="panel-header">
          <h1 className="font-display text-xl font-bold text-white">Reset link expired</h1>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            This password reset link is invalid or has already been used. Request a new one below.
          </p>
        </header>
        <div className="p-6">
          <ForgotPasswordForm showBackLink={false} />
          <p className="mt-4 text-center text-xs text-[var(--color-text-muted)]">
            <Link href="/" className="text-mint-soft hover:underline">
              Back to home
            </Link>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="panel mx-auto mt-16 max-w-md overflow-hidden">
      <header className="panel-header">
        <h1 className="font-display text-xl font-bold text-white">Set new password</h1>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">
          Choose a new password for {user?.email}.
        </p>
      </header>

      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4 p-6">
        <div>
          <label htmlFor="new-password" className="auth-modal-label">
            New password
          </label>
          <input
            id="new-password"
            type="password"
            required
            minLength={6}
            autoComplete="new-password"
            className="form-input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="confirm-password" className="auth-modal-label">
            Confirm password
          </label>
          <input
            id="confirm-password"
            type="password"
            required
            minLength={6}
            autoComplete="new-password"
            className="form-input"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
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

        <button type="submit" className="btn btn-primary w-full" disabled={busy}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Update password"}
        </button>

        <p className="text-center text-xs text-[var(--color-text-muted)]">
          <Link href="/" className="text-mint-soft hover:underline">
            Back to home
          </Link>
        </p>
      </form>
    </div>
  );
}
