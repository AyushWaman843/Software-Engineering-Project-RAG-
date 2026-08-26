"use client";

import { PageLoader } from "@/components/ui/PageLoader";

/** Full-screen first-paint loader with clear brand shield. */
export function SplashLoader() {
  return (
    <div id="initial-loader" className="initial-loader" aria-live="polite" aria-busy="true">
      <div className="initial-loader__backdrop" aria-hidden />
      <div className="initial-loader__panel">
        <PageLoader
          badge="DPDP Compliance Scanner"
          label="DPDP Scanner"
          sublabel="Loading your privacy compliance workspace"
          compact={false}
        />
      </div>
    </div>
  );
}
