"use client";

import { useRef } from "react";
import { motion, useInView } from "framer-motion";
import { CountUp } from "./CountUp";

type Band = "high" | "mid" | "low";

interface ScoreGaugeProps {
  score: number;
  band: Band;
  label: string;
  size?: number;
}

const BANDS: Record<Band, { from: string; to: string; glow: string; text: string }> = {
  high: { from: "#5BD6AB", to: "#25C08A", glow: "rgba(37,192,138,0.36)", text: "#5BD6AB" },
  mid: { from: "#FFD060", to: "#FFB020", glow: "rgba(255,176,32,0.32)", text: "#FFB020" },
  low: { from: "#FF8C8C", to: "#FF5F5F", glow: "rgba(255,95,95,0.32)", text: "#FF8C8C" },
};

/** Premium animated radial score gauge with a counting centre value. */
export function ScoreGauge({ score, band, label, size = 220 }: ScoreGaugeProps) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.5 });
  const colors = BANDS[band];

  const stroke = 14;
  const r = (size - stroke) / 2 - 6;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const gid = `gauge-${band}`;

  return (
    <div
      ref={ref}
      className="relative shrink-0"
      style={{ width: size, height: size }}
    >
      {/* rotating comet glow behind the ring */}
      <div
        className="absolute inset-3 rounded-full opacity-40 animate-sweep"
        style={{
          background: `conic-gradient(from 0deg, transparent 0deg, ${colors.glow} 40deg, transparent 90deg)`,
          filter: "blur(9px)",
        }}
        aria-hidden
      />
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="relative -rotate-90"
        role="img"
        aria-label={`Compliance score ${score} out of 100`}
      >
        <defs>
          <linearGradient id={gid} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={colors.from} />
            <stop offset="100%" stopColor={colors.to} />
          </linearGradient>
          <filter id={`${gid}-glow`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* track */}
        <circle
          className="ring-track"
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
        />
        {/* progress arc */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={`url(#${gid})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          filter={`url(#${gid}-glow)`}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: inView ? c - c * pct : c }}
          transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
        />
      </svg>

      {/* centre readout */}
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <div className="flex items-baseline font-display font-bold tabular-nums">
          <CountUp
            value={score}
            className="text-[3.25rem] leading-none"
            format={(n) => String(n)}
          />
          <span className="ml-0.5 text-lg font-semibold text-[var(--color-text-faint)]">/100</span>
        </div>
        <span
          className="mt-2 max-w-[10rem] text-[0.7rem] font-bold uppercase tracking-[0.18em]"
          style={{ color: colors.text }}
        >
          {label}
        </span>
      </div>
    </div>
  );
}
