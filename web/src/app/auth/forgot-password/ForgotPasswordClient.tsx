"use client";

import Link from "next/link";
import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";

export function ForgotPasswordPage() {
  return (
    <div className="panel mx-auto mt-16 max-w-md overflow-hidden">
      <header className="panel-header">
        <h1 className="font-display text-xl font-bold text-white">Reset your password</h1>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">
          We&apos;ll email you a link to set a new password.
        </p>
      </header>

      <div className="p-6">
        <ForgotPasswordForm showBackLink={false} />
        <p className="mt-4 text-center text-xs text-[var(--color-text-muted)]">
          Remember your password?{" "}
          <Link href="/?auth=signin" className="text-mint-soft hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
