"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/contexts/ThemeContext";

export function ThemeToggle() {
  const { theme, mounted, toggleTheme } = useTheme();
  const isDark = theme === "dark";

  const ariaLabel = !mounted
    ? "Toggle color theme"
    : isDark
      ? "Switch to light mode"
      : "Switch to dark mode";

  const title = !mounted ? "Color theme" : isDark ? "Light mode" : "Dark mode";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="theme-toggle"
      aria-label={ariaLabel}
      title={title}
      suppressHydrationWarning
    >
      <Sun className="theme-toggle__icon theme-toggle__icon--sun" aria-hidden />
      <Moon className="theme-toggle__icon theme-toggle__icon--moon" aria-hidden />
    </button>
  );
}
