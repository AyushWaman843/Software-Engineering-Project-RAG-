"use client";

import { LoaderScene } from "./LoaderScene";

interface PageLoaderProps {
  label?: string;
  sublabel?: string;
  badge?: string;
  showSkeleton?: boolean;
  compact?: boolean;
}

export function PageLoader({
  label = "Loading",
  sublabel = "Please wait a moment",
  badge,
  showSkeleton = false,
  compact = false,
}: PageLoaderProps) {
  return (
    <div
      className={`page-loader ${compact ? "page-loader--compact" : ""}`}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="page-loader__content">
        {badge && !compact && (
          <span className="page-loader__badge">{badge}</span>
        )}

        <LoaderScene size={compact ? "sm" : "lg"} />

        <div className="page-loader__text">
          <p className="page-loader__label gradient-text">{label}</p>
          <p className="page-loader__sublabel">
            {sublabel}
            <span className="page-loader__dots" aria-hidden>
              <span />
              <span />
              <span />
            </span>
          </p>
          {!compact && (
            <div className="page-loader__bar">
              <div className="page-loader__bar-track">
                <div className="page-loader__bar-fill" />
              </div>
            </div>
          )}
        </div>
      </div>

      {showSkeleton && (
        <div className="page-loader__skeleton mt-10 space-y-6" aria-hidden>
          <div className="panel p-8">
            <div className="grid gap-8 md:grid-cols-[auto_1fr]">
              <div className="mx-auto h-[220px] w-[220px] rounded-full bg-white/[0.04] loader-shimmer" />
              <div className="space-y-4">
                <div className="h-3 w-28 rounded bg-white/[0.06] loader-shimmer" />
                <div className="h-10 w-64 max-w-full rounded bg-white/[0.08] loader-shimmer" />
                <div className="h-4 w-full max-w-md rounded bg-white/[0.05] loader-shimmer" />
              </div>
            </div>
          </div>
          <div className="panel h-64 loader-shimmer" />
        </div>
      )}

      <span className="sr-only">{label}</span>
    </div>
  );
}
