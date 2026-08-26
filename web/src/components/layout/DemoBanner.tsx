"use client";

import { useAuth } from "@/contexts/AuthContext";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_AUTO_LOGIN === "1";

export function DemoBanner() {
  const { user, loading } = useAuth();

  if (!DEMO_MODE || loading || !user) return null;

  return (
    <div className="border-b border-mint/20 bg-mint/10 px-3 py-1.5 text-center text-xs text-[var(--color-text)] md:px-4 md:py-2 md:text-sm">
      <span className="font-medium text-mint">Demo mode</span>
      {" — signed in as "}
      <span className="font-mono text-xs">{user.email}</span>
      {" · Pilot active (1 full scan/day)"}
    </div>
  );
}
