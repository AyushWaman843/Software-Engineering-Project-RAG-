interface SparklineProps {
  /** Score values 0–100, oldest → newest. */
  values: number[];
  width?: number;
  height?: number;
  color?: string;
  className?: string;
}

/** Minimal inline sparkline for a 0–100 score series. Inherits `currentColor` by default. */
export function Sparkline({
  values,
  width = 84,
  height = 24,
  color = "currentColor",
  className,
}: SparklineProps) {
  if (values.length < 2) return null;

  const n = values.length;
  const dx = width / (n - 1);
  const y = (v: number) => {
    const clamped = Math.max(0, Math.min(100, v));
    return height - 2 - (clamped / 100) * (height - 4);
  };

  const points = values.map((v, i) => `${(i * dx).toFixed(1)},${y(v).toFixed(1)}`);
  const line = points.map((p, i) => (i === 0 ? `M${p}` : `L${p}`)).join(" ");
  const area = `${line} L${width.toFixed(1)},${height} L0,${height} Z`;
  const lastX = (n - 1) * dx;
  const lastY = y(values[n - 1]);

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      style={{ color }}
      aria-hidden
    >
      <path d={area} fill="currentColor" opacity={0.12} />
      <path
        d={line}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={lastX} cy={lastY} r={2.2} fill="currentColor" />
    </svg>
  );
}
