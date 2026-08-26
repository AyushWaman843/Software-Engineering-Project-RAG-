"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Loader2 } from "lucide-react";

interface MobileScanSubmitBarProps {
  formId: string;
  submitting: boolean;
  payForScanLoading: boolean;
  sessionReady: boolean;
}

export function MobileScanSubmitBar({
  formId,
  submitting,
  payForScanLoading,
  sessionReady,
}: MobileScanSubmitBarProps) {
  const [mounted, setMounted] = useState(false);
  const busy = submitting || payForScanLoading;
  const disabled = busy || !sessionReady;

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

  return createPortal(
    <div className="mobile-sticky-cta md:hidden" role="presentation">
      <button
        type="submit"
        form={formId}
        className="btn btn-primary mobile-sticky-cta__btn"
        disabled={disabled}
      >
        {busy && <Loader2 className="h-4 w-4 animate-spin" />}
        {payForScanLoading ? "Opening checkout…" : submitting ? "Assessment running…" : "Commence Assessment"}
      </button>
    </div>,
    document.body,
  );
}
