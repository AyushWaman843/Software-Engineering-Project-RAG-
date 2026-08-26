"use client";

import { useEffect, useRef } from "react";
import { useSessionReady } from "@/contexts/SessionReadyContext";

/** Fades out the full-screen splash once auth + quota bootstrap completes. */
export function InitialLoaderDismiss() {
  const { ready } = useSessionReady();
  const dismissed = useRef(false);

  useEffect(() => {
    if (!ready || dismissed.current) return undefined;

    const root = document.getElementById("initial-loader");
    if (!root) return undefined;

    dismissed.current = true;

    const timer = window.setTimeout(() => {
      root.classList.add("initial-loader--hide");
      window.setTimeout(() => root.remove(), 450);
    }, 200);

    return () => window.clearTimeout(timer);
  }, [ready]);

  return null;
}
