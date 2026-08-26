"use client";

import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { useSessionReady } from "@/contexts/SessionReadyContext";

interface WorkspaceReadyGateProps {
  children: ReactNode;
  skip?: boolean;
}

/**
 * Blocks interaction until the first auth + quota bootstrap completes.
 * Uses a stable wrapper so children are never remounted when quota refreshes.
 */
export function WorkspaceReadyGate({ children, skip = false }: WorkspaceReadyGateProps) {
  const { ready, authLoading, quotaLoading } = useSessionReady();
  const showGate = !skip && !ready;

  const label = authLoading
    ? "Checking your session…"
    : quotaLoading
      ? "Loading account status…"
      : "Preparing workspace…";

  return (
    <div className="relative min-h-[12rem]">
      {children}
      {showGate && (
        <div
          className="workspace-ready-gate"
          role="status"
          aria-live="polite"
          aria-busy="true"
        >
          <Loader2 className="h-7 w-7 animate-spin text-mint" aria-hidden />
          <p className="workspace-ready-gate__label">{label}</p>
          <p className="workspace-ready-gate__hint">Please wait — don&apos;t click until this finishes.</p>
        </div>
      )}
    </div>
  );
}
