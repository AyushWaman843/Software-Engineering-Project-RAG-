"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { AuthButton } from "@/components/auth/AuthButton";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { GetPilotButton } from "@/components/premium/GetPilotButton";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { MobileHeaderActions } from "@/components/layout/MobileHeaderActions";
import { useSessionReady } from "@/contexts/SessionReadyContext";
import { usePremiumNavStatus } from "@/hooks/usePremiumNavStatus";
import { useWebsiteReturnUrl } from "@/hooks/useWebsiteReturnUrl";

export function SiteHeader() {
  const isPremium = usePremiumNavStatus();
  const { ready: sessionReady } = useSessionReady();
  const websiteReturnUrl = useWebsiteReturnUrl();

  return (
    <header className="site-header sticky top-0 z-40 border-b border-border backdrop-blur-xl">
      <div className="h-px w-full bg-gradient-to-r from-transparent via-mint/40 to-transparent" />
      <div className="mx-auto flex max-w-[1200px] items-center justify-between gap-3 px-4 py-2.5 md:flex-wrap md:gap-4 md:px-6 md:py-3">
        <Link href="/" className="group flex min-w-0 items-center gap-2.5 md:gap-3">
          <motion.span
            initial={{ opacity: 0, scale: 0.8, rotate: -8 }}
            animate={{ opacity: 1, scale: 1, rotate: 0 }}
            transition={{ type: "spring", stiffness: 220, damping: 16 }}
            className="relative grid h-9 w-9 shrink-0 place-items-center md:h-10 md:w-10"
          >
            <span className="absolute inset-0 rounded-xl bg-mint/15 blur-md transition-opacity duration-300 group-hover:opacity-100" />
            <BrandLogo
              size={40}
              priority
              className="relative h-9 w-9 drop-shadow-[0_3px_10px_rgba(255,122,24,0.26)] transition-transform duration-300 group-hover:scale-[1.03] md:h-10 md:w-10"
            />
          </motion.span>
          <span className="flex min-w-0 flex-col leading-none">
            <span className="truncate font-display text-base font-bold tracking-tight gradient-text md:text-lg">
              DPDP Scanner
            </span>
            <span className="mt-0.5 block text-[0.55rem] font-medium uppercase tracking-[0.18em] text-[var(--color-text-faint)] md:text-[0.6rem] md:tracking-[0.28em]">
              DPDP Compliance Console
            </span>
          </span>
        </Link>

        <MobileHeaderActions />

        {/* Desktop navigation — unchanged */}
        <nav
          className={`hidden items-center gap-4 md:flex${sessionReady ? "" : " pointer-events-none opacity-60"}`}
          aria-busy={!sessionReady}
        >
          <a
            href={websiteReturnUrl}
            className="group relative flex items-center gap-1.5 text-sm font-medium text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)]"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6"/></svg>
            Back to Website
            <span className="absolute -bottom-1 left-0 h-px w-0 bg-mint transition-all duration-300 group-hover:w-full" />
          </a>
          <GetPilotButton isPremium={isPremium} />
          <ThemeToggle />
          <AuthButton isPremium={isPremium} />
        </nav>
      </div>
    </header>
  );
}
