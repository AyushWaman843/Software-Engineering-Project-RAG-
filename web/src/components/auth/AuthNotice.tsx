"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

type NoticeTone = "success" | "error";

export function AuthNotice() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { openAuth } = useAuth();
  const [message, setMessage] = useState<string | null>(null);
  const [tone, setTone] = useState<NoticeTone>("success");

  useEffect(() => {
    const auth = searchParams.get("auth");
    if (!auth) {
      setMessage(null);
      return undefined;
    }

    if (auth === "signin") {
      openAuth("signin");
      router.replace("/", { scroll: false });
      return undefined;
    }

    if (auth === "forgot") {
      openAuth("forgot");
      router.replace("/", { scroll: false });
      return undefined;
    }

    if (auth === "confirmed") {
      setTone("success");
      setMessage("Email verified. You can sign in now.");
    } else if (auth === "password_updated") {
      setTone("success");
      setMessage("Password updated successfully. You are signed in with your new password.");
    } else if (auth === "reset_required") {
      setTone("error");
      setMessage(
        "Your reset link expired or is invalid. Request a new password reset email to continue.",
      );
    } else if (auth === "failed") {
      setTone("error");
      setMessage("Email verification failed or expired. Try signing in or resend the verification email.");
    } else {
      setMessage(null);
      return undefined;
    }

    router.replace("/", { scroll: false });

    const timer = window.setTimeout(() => setMessage(null), 10000);
    return () => window.clearTimeout(timer);
  }, [searchParams, router, openAuth]);

  if (!message) return null;

  const classes =
    tone === "success"
      ? "rounded-xl border border-mint/30 bg-mint/[0.08] px-4 py-3 text-sm text-mint-soft"
      : "rounded-xl border border-rose/30 bg-rose/[0.08] px-4 py-3 text-sm text-rose-soft";

  return (
    <div className="mx-auto mb-3 max-w-[1200px] px-4 md:mb-6 md:px-6" role="status">
      <p className={classes}>
        {message}
        {tone === "error" && (
          <>
            {" "}
            <Link href="/auth/forgot-password" className="font-semibold underline underline-offset-2">
              Request reset link
            </Link>
          </>
        )}
      </p>
    </div>
  );
}
