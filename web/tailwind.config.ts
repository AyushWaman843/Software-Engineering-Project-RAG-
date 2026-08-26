import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: ["class"],
  theme: {
    extend: {
      colors: {
        // Core ink scale
        ink: {
          900: "#070a11",
          850: "#0b1019",
          800: "#10162a",
          750: "#161d2f",
          700: "#1c2438",
          600: "#252f48",
        },
        // Primary orange accent (CTAs, focus, progress)
        mint: {
          DEFAULT: "#ff7a18",
          strong: "#ff6a00",
          soft: "#ff9a4d",
        },
        accent: {
          DEFAULT: "#ff7a18",
          strong: "#ff6a00",
          soft: "#ff9a4d",
        },
        brand: {
          DEFAULT: "#6c8cff",
          soft: "#9db1ff",
        },
        green: {
          DEFAULT: "#25c08a",
          soft: "#5bd6ab",
        },
        blue: {
          DEFAULT: "#4ea1ff",
          soft: "#8fc2ff",
        },
        violet: { DEFAULT: "#6c8cff", soft: "#9db1ff" },
        cyan: { DEFAULT: "#4ea1ff", soft: "#8fc2ff" },
        amber: { DEFAULT: "#ffb020", soft: "#ffd060" },
        rose: { DEFAULT: "#ff5f5f", soft: "#ff8c8c" },
        gold: { DEFAULT: "#e6b450", light: "#ffb020" },
        navy: {
          DEFAULT: "#e9eef9",
          light: "#9aa6bd",
          muted: "#9aa6bd",
        },
        surface: "#10162a",
        background: "#070a11",
        border: {
          DEFAULT: "rgba(255,255,255,0.09)",
          light: "rgba(255,255,255,0.05)",
          strong: "rgba(255,255,255,0.14)",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "Space Grotesk", "system-ui", "sans-serif"],
        serif: ["var(--font-display)", "Space Grotesk", "system-ui", "sans-serif"],
        sans: ["var(--font-sans)", "Inter", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 0 rgba(255,255,255,0.04) inset, 0 18px 40px -24px rgba(0,0,0,0.8)",
        panelMd: "0 1px 0 rgba(255,255,255,0.05) inset, 0 30px 60px -28px rgba(0,0,0,0.85)",
        glow: "0 0 0 1px var(--glow), 0 12px 40px -12px rgba(255,122,24,0.35)",
        lift: "0 24px 50px -24px rgba(0,0,0,0.9)",
      },
      borderRadius: {
        xl2: "1.25rem",
      },
      keyframes: {
        auroraPan: {
          "0%, 100%": { transform: "translate3d(0,0,0) scale(1)" },
          "33%": { transform: "translate3d(6%,-4%,0) scale(1.08)" },
          "66%": { transform: "translate3d(-5%,5%,0) scale(0.96)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        shimmer: {
          "0%": { transform: "translateX(-120%)" },
          "100%": { transform: "translateX(220%)" },
        },
        pulseRing: {
          "0%": { transform: "scale(0.6)", opacity: "0.7" },
          "100%": { transform: "scale(2.2)", opacity: "0" },
        },
        sweep: {
          to: { transform: "rotate(360deg)" },
        },
        gridPan: {
          "0%": { backgroundPosition: "0 0" },
          "100%": { backgroundPosition: "64px 64px" },
        },
        shine: {
          "0%": { backgroundPosition: "0% 50%" },
          "100%": { backgroundPosition: "200% 50%" },
        },
      },
      animation: {
        "aurora-pan": "auroraPan 26s ease-in-out infinite",
        float: "float 6s ease-in-out infinite",
        shimmer: "shimmer 2.4s ease-in-out infinite",
        "pulse-ring": "pulseRing 2.4s ease-out infinite",
        sweep: "sweep 3.2s linear infinite",
        "grid-pan": "gridPan 18s linear infinite",
        shine: "shine 6s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
