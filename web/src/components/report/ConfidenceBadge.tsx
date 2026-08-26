"use client";

export type ConfidenceLabel = "high" | "medium" | "low";

const BADGE_STYLES: Record<
  ConfidenceLabel,
  { className: string; label: string }
> = {
  high: {
    className: "bg-emerald-600 text-white",
    label: "High confidence",
  },
  medium: {
    className: "bg-amber-400 text-slate-900",
    label: "Medium confidence",
  },
  low: {
    className: "bg-rose-600 text-white",
    label: "Low confidence",
  },
};

interface ConfidenceBadgeProps {
  label: ConfidenceLabel;
  average?: number | null;
  className?: string;
}

/** Small badge showing how confident the AI was in this assessment. */
export function ConfidenceBadge({ label, average, className = "" }: ConfidenceBadgeProps) {
  const style = BADGE_STYLES[label];

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[0.7rem] font-bold uppercase tracking-[0.12em] ${style.className} ${className}`}
      title={
        average != null
          ? `Average indicator confidence: ${average}%`
          : `${style.label} assessment`
      }
    >
      {style.label}
    </span>
  );
}
