"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { stripBasePath } from "@/lib/base-path";

function completeProgress(
  setActive: (active: boolean) => void,
  setProgress: (progress: number) => void,
) {
  setActive(false);
  setProgress(100);
  window.setTimeout(() => setProgress(0), 280);
}

/**
 * Top-of-screen progress bar during client-side route transitions.
 * Works alongside Next.js loading.tsx for server-rendered segments.
 */
export function RouteProgress() {
  const pathname = usePathname();
  const [active, setActive] = useState(false);
  const [progress, setProgress] = useState(0);
  const activeRef = useRef(false);

  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  useEffect(() => {
    completeProgress(setActive, setProgress);
  }, [pathname]);

  useEffect(() => {
    const onStart = () => {
      setActive(true);
      setProgress(12);
    };
    window.addEventListener("route-start", onStart);
    return () => window.removeEventListener("route-start", onStart);
  }, []);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const anchor = (event.target as HTMLElement).closest("a");
      if (!anchor?.href) return;
      if (anchor.target === "_blank" || anchor.hasAttribute("download")) return;

      try {
        const url = new URL(anchor.href);
        if (url.origin !== window.location.origin) return;

        const targetPath = stripBasePath(url.pathname);
        const currentPath = pathname || "/";
        if (targetPath === currentPath && url.search === window.location.search) return;
      } catch {
        return;
      }

      setActive(true);
      setProgress(12);
    };

    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [pathname]);

  useEffect(() => {
    if (!active) return undefined;

    setProgress(28);
    const t1 = window.setTimeout(() => setProgress(52), 180);
    const t2 = window.setTimeout(() => setProgress(74), 520);
    const t3 = window.setTimeout(() => setProgress(88), 1100);

    // Same-route navigations (e.g. footer "New Assessment" on home) scroll to top
    // without changing pathname — complete the bar so it does not stay stuck.
    const stuckGuard = window.setTimeout(() => {
      if (activeRef.current) {
        completeProgress(setActive, setProgress);
      }
    }, 500);

    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
      window.clearTimeout(t3);
      window.clearTimeout(stuckGuard);
    };
  }, [active]);

  if (progress <= 0 && !active) return null;

  return (
    <div
      className="route-progress"
      role="progressbar"
      aria-hidden={!active}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={progress}
    >
      <div
        className="route-progress__bar"
        style={{ transform: `scaleX(${progress / 100})` }}
      />
      <div className="route-progress__glow" style={{ left: `${progress}%` }} />
    </div>
  );
}
