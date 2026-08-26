"use client";

import { useEffect, useState } from "react";
import { History, Loader2, User } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useMobileHistory } from "@/contexts/MobileHistoryContext";
import { usePremiumNavStatus } from "@/hooks/usePremiumNavStatus";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { truststackSubscribeUrl } from "@/lib/truststack";

export function MobileHeaderActions() {
  const { user, loading, configured, openAuth, signOut } = useAuth();
  const { openHistory } = useMobileHistory();
  const isPremium = usePremiumNavStatus();
  const [accountOpen, setAccountOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    if (!accountOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setAccountOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [accountOpen]);

  function handleHistoryClick() {
    if (!configured || loading) return;
    if (!user) {
      openAuth("signin");
      return;
    }
    openHistory();
  }

  function handleAccountClick() {
    if (!configured || loading) return;
    if (!user) {
      openAuth("signin");
      return;
    }
    setAccountOpen((open) => !open);
  }

  return (
    <>
      <div className="flex items-center gap-1 md:hidden">
        <button
          type="button"
          className="mobile-header-icon-btn"
          aria-label="Assessment history"
          onClick={handleHistoryClick}
        >
          <History className="h-5 w-5" aria-hidden />
        </button>
        <button
          type="button"
          className="mobile-header-icon-btn"
          aria-label={user ? "Account menu" : "Sign in"}
          aria-expanded={accountOpen}
          onClick={handleAccountClick}
        >
          <User className="h-5 w-5" aria-hidden />
        </button>
      </div>

      {accountOpen && user && (
        <>
          <button
            type="button"
            className="mobile-account-sheet__backdrop"
            aria-label="Close account menu"
            onClick={() => setAccountOpen(false)}
          />
          <div className="mobile-account-sheet md:hidden" role="dialog" aria-label="Account">
            <p className="mobile-account-sheet__email" title={user.email ?? undefined}>
              {user.email || "Account"}
            </p>
            <p
              className={`mobile-account-sheet__meta ${
                isPremium ? "text-[var(--color-gold-light)]" : ""
              }`}
            >
              {isPremium ? "Pilot active" : "Free plan"}
            </p>
            {!isPremium && (
              <a
                href={truststackSubscribeUrl()}
                className="btn btn-primary mobile-account-sheet__menu-btn"
                onClick={() => setAccountOpen(false)}
              >
                Get Pilot
              </a>
            )}
            <div className="mobile-account-sheet__row">
              <span className="text-sm text-[var(--color-text-muted)]">Theme</span>
              <ThemeToggle />
            </div>
            <button
              type="button"
              className="btn btn-secondary mobile-account-sheet__logout"
              disabled={signingOut}
              onClick={() => {
                setSigningOut(true);
                void signOut().finally(() => {
                  setSigningOut(false);
                  setAccountOpen(false);
                });
              }}
            >
              {signingOut && <Loader2 className="h-4 w-4 animate-spin" />}
              Log out
            </button>
          </div>
        </>
      )}
    </>
  );
}
