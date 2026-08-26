"use client";

import { Scale } from "lucide-react";

export function DisclaimerBar() {
  return (
    <div className="hidden border-b border-border bg-[rgba(251,191,36,0.05)] md:block">
      <p className="mx-auto flex max-w-[1200px] items-center justify-center gap-2 overflow-x-auto px-4 py-2.5 text-center text-[0.6875rem] text-[var(--color-text-muted)] whitespace-nowrap sm:px-6 sm:text-[0.8125rem] [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
        <Scale className="h-3.5 w-3.5 shrink-0 text-amber/80" aria-hidden />
        <span>
          This automated assessment is indicative only and does not constitute legal advice. For expert-verified compliance analysis,{" "}
          <a
            href="mailto:contact@dpdpscanner.in?subject=DPDP%20Manual%20Compliance%20Review"
            className="font-medium text-mint-soft underline underline-offset-2 hover:text-mint"
          >
            contact us
          </a>{" "}
          for a manual review, or consult a qualified attorney.
        </span>
      </p>
    </div>
  );
}
