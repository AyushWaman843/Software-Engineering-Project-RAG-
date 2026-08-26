"use client";

import { Suspense } from "react";
import { usePathname } from "next/navigation";
import { AuthProvider } from "@/contexts/AuthContext";
import { SessionReadyProvider } from "@/contexts/SessionReadyContext";
import { CookieConsentProvider } from "@/contexts/CookieConsentContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { AuthNotice } from "@/components/auth/AuthNotice";
import { CookieConsentBanner } from "@/components/cookies/CookieConsentBanner";
import { CookieSettingsModal } from "@/components/cookies/CookieSettingsModal";
import { DisclaimerBar } from "@/components/layout/DisclaimerBar";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { MobileReportBar } from "@/components/layout/MobileReportBar";
import { DemoBanner } from "@/components/layout/DemoBanner";
import { WorkspaceReadyGate } from "@/components/layout/WorkspaceReadyGate";
import { InitialLoaderDismiss } from "@/components/ui/InitialLoaderDismiss";
import { PageLoader } from "@/components/ui/PageLoader";
import { RouteProgress } from "@/components/ui/RouteProgress";
import { SplashLoader } from "@/components/ui/SplashLoader";

const LEGAL_PATHS = new Set(["/privacy", "/terms", "/cookies"]);

import { LexBot } from "@/components/chat/LexBot";
import { MobileHistoryProvider } from "@/contexts/MobileHistoryContext";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLegalPage = LEGAL_PATHS.has(pathname);
  const isReportPage = pathname.startsWith("/report/");

  return (
    <>
      <SplashLoader />

      <div className="aurora" aria-hidden>
        <span className="aurora-blob" />
      </div>
      <div className="app-texture" aria-hidden />

      <AuthProvider>
        <SessionReadyProvider>
        <MobileHistoryProvider>
        <InitialLoaderDismiss />
        <ThemeProvider>
        <CookieConsentProvider>
          <div className="relative z-10 flex min-h-screen flex-col">
            <RouteProgress />
            <SiteHeader />
            <DemoBanner />
            <DisclaimerBar />
            <Suspense fallback={null}>
              <AuthNotice />
            </Suspense>
            <main
              className={
                isLegalPage
                  ? "mx-auto w-full max-w-5xl flex-1 py-4 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] md:px-6 md:py-10 md:pb-10 lg:px-8"
                  : isReportPage
                    ? "mx-auto w-full max-w-[1200px] flex-1 pt-3 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] md:px-6 md:py-4 md:pb-10"
                    : "mx-auto w-full max-w-[1200px] flex-1 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] md:px-6 md:py-4 md:pb-10"
              }
            >
              <Suspense
                fallback={
                  <PageLoader
                    label="Loading workspace"
                    sublabel="Syncing compliance data"
                  />
                }
              >
                <WorkspaceReadyGate skip={isLegalPage}>{children}</WorkspaceReadyGate>
              </Suspense>
            </main>
            <div className="hidden md:block">
              <SiteFooter />
            </div>
            <MobileReportBar />
          </div>
          <CookieSettingsModal />
          <div className="hidden md:block">
            <LexBot />
          </div>
        </CookieConsentProvider>
        </ThemeProvider>
        </MobileHistoryProvider>
        </SessionReadyProvider>
      </AuthProvider>
    </>
  );
}
