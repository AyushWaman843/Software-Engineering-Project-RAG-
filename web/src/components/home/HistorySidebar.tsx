"use client";

import { motion } from "framer-motion";
import { History } from "lucide-react";
import { HistoryList } from "@/components/home/HistoryList";
import type { HistoryItem } from "@/lib/types";

interface HistorySidebarProps {
  items: HistoryItem[];
  title?: string;
  emptyMessage?: string;
}

export function HistorySidebar({
  items,
  title = "Recent Assessments",
  emptyMessage = "No previous assessments recorded.",
}: HistorySidebarProps) {
  return (
    <motion.aside
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4, delay: 0.15 }}
      className="panel h-fit min-w-0"
    >
      <header className="panel-header flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-display text-base font-bold tracking-tight text-[var(--color-text)]">
          <History className="h-4 w-4 text-mint" />
          {title}
        </h2>
        {items.length > 0 && (
          <span className="rounded-full border border-border bg-white/[0.03] px-2 py-0.5 text-xs font-semibold tabular-nums text-[var(--color-text-muted)]">
            {items.length}
          </span>
        )}
      </header>

      <HistoryList items={items} emptyMessage={emptyMessage} />
    </motion.aside>
  );
}
