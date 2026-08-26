"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { usePathname } from "next/navigation";

const HIDDEN_PATHS = new Set(["/privacy", "/terms", "/cookies", "/"]);

export function MobileReportBar() {
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted || !pathname.startsWith("/report/") || HIDDEN_PATHS.has(pathname)) return null;

  return createPortal(
    <div className="mobile-sticky-cta md:hidden" role="presentation">
      <Link href="/" className="btn btn-primary mobile-sticky-cta__btn">
        New assessment
      </Link>
    </div>,
    document.body,
  );
}
