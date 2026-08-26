"use client";

import { BrandLogo } from "@/components/brand/BrandLogo";

interface LoaderSceneProps {
  size?: "lg" | "sm";
}

const SIZES = {
  lg: { box: 128, iconWrap: 88, logo: 52 },
  sm: { box: 80, iconWrap: 56, logo: 34 },
} as const;

const RING_R = 46;

/** Brand loader — spinning progress arc around the Anix AI logo. */
export function LoaderScene({ size = "lg" }: LoaderSceneProps) {
  const dims = SIZES[size];

  return (
    <div
      className={`brand-loader brand-loader--${size}`}
      style={{ width: dims.box, height: dims.box }}
      aria-hidden
    >
      <div className="brand-loader__halo" />

      <svg className="brand-loader__track" viewBox="0 0 100 100" fill="none" aria-hidden>
        <circle
          cx="50"
          cy="50"
          r={RING_R}
          strokeWidth="2.5"
        />
      </svg>

      <svg className="brand-loader__ring" viewBox="0 0 100 100" fill="none" aria-hidden>
        <defs>
          <linearGradient id="brand-loader-ring" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FF7A18" />
            <stop offset="50%" stopColor="#FFB020" />
            <stop offset="100%" stopColor="#6C8CFF" />
          </linearGradient>
        </defs>
        <circle
          className="brand-loader__arc"
          cx="50"
          cy="50"
          r={RING_R}
          stroke="url(#brand-loader-ring)"
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray="90 199"
        />
      </svg>

      <svg className="brand-loader__ring brand-loader__ring--reverse" viewBox="0 0 100 100" fill="none" aria-hidden>
        <circle
          className="brand-loader__arc-soft"
          cx="50"
          cy="50"
          r={RING_R - 9}
          stroke="rgba(255,122,24,0.28)"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeDasharray="36 215"
        />
      </svg>

      <div
        className="brand-loader__icon-wrap"
        style={{ width: dims.iconWrap, height: dims.iconWrap }}
      >
        <BrandLogo
          size={dims.logo}
          className="brand-loader__logo drop-shadow-[0_2px_8px_rgba(255,122,24,0.3)]"
        />
      </div>
    </div>
  );
}
