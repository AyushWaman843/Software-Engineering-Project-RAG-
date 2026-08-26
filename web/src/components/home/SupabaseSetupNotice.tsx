"use client";

import { Database } from "lucide-react";
import { SUPABASE_SETUP_HINT } from "@/lib/supabase/scans";

export function SupabaseSetupNotice() {
  return (
    <div className="rounded-xl border border-amber/30 bg-amber/[0.08] px-4 py-3 text-left">
      <p className="flex items-start gap-2 text-sm font-semibold text-amber-soft">
        <Database className="mt-0.5 h-4 w-4 shrink-0" />
        Database setup required
      </p>
      <p className="mt-2 text-xs leading-relaxed text-[var(--color-text-muted)]">
        The <code className="rounded bg-white/[0.06] px-1 font-mono text-[0.7rem]">user_scans</code>{" "}
        table is missing in Supabase. {SUPABASE_SETUP_HINT}
      </p>
      <p className="mt-2 text-xs text-[var(--color-text-faint)]">
        File in this project: <code className="font-mono">supabase/schema.sql</code>
      </p>
    </div>
  );
}
