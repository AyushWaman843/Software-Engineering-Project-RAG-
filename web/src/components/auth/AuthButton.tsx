"use client";

import { useEffect, useState } from "react";
import { Loader2, LogOut, LogIn, UserPlus } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

interface AuthButtonProps {
  isPremium?: boolean;
}

/** Placeholder matches nav button footprint so layout does not shift after hydration. */
function AuthButtonPlaceholder() {
  return (
    <span
      className="inline-flex h-[34px] min-w-[140px] items-center justify-end gap-2"
      aria-hidden
    />
  );
}

export function AuthButton({ isPremium = false }: AuthButtonProps) {
  const { user, loading, configured, signOut, openAuth } = useAuth();
  const [signingOut, setSigningOut] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted || !configured || loading) {
    return <AuthButtonPlaceholder />;
  }

  if (user) {
    return (
      <button
        type="button"
        className="flex h-[34px] items-center justify-center gap-1.5 rounded-full border border-border-strong bg-white/[0.03] px-3 text-xs font-medium text-[var(--color-text-muted)] shadow-sm backdrop-blur transition-colors hover:border-border hover:bg-white/[0.06] hover:text-[var(--color-text)] sm:px-3.5"
        disabled={signingOut}
        onClick={() => {
          setSigningOut(true);
          void signOut().finally(() => setSigningOut(false));
        }}
        title="Log out"
      >
        {signingOut ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LogOut className="h-3.5 w-3.5" />}
        <span className="hidden sm:inline">Log out</span>
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        className="btn btn-secondary gap-1.5 px-3 py-1.5 text-xs"
        onClick={() => openAuth("signin")}
      >
        <LogIn className="h-3.5 w-3.5" />
        Sign in
      </button>
      <button
        type="button"
        className="btn btn-primary hidden gap-1.5 px-3 py-1.5 text-xs sm:inline-flex"
        onClick={() => openAuth("signup")}
      >
        <UserPlus className="h-3.5 w-3.5" />
        Sign up
      </button>
    </div>
  );
}
