"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion, useDragControls } from "framer-motion";
import { Loader2 } from "lucide-react";
import { HistoryList } from "@/components/home/HistoryList";
import { PageLoader } from "@/components/ui/PageLoader";
import { useAuth } from "@/contexts/AuthContext";
import { useMobileHistory } from "@/contexts/MobileHistoryContext";
import { fetchUserScansClient } from "@/lib/supabase/scans";
import type { HistoryItem } from "@/lib/types";

const DISMISS_OFFSET = 100;
const DISMISS_VELOCITY = 400;

export function MobileHistorySheet() {
  const { open, closeHistory } = useMobileHistory();
  const { user, session, loading: authLoading, configured, openAuth } = useAuth();
  const dragControls = useDragControls();
  const [mounted, setMounted] = useState(false);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);

  const loadHistory = useCallback(async () => {
    if (!configured || !user) {
      setItems([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const result = await fetchUserScansClient(user.id, session?.access_token);
      setItems(result.items);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [configured, user, session?.access_token]);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    void loadHistory();
  }, [open, loadHistory]);

  useEffect(() => {
    if (!open) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeHistory();
    };
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, closeHistory]);

  useEffect(() => {
    if (!user) return undefined;
    const onRefresh = () => void loadHistory();
    window.addEventListener("scan-history-updated", onRefresh);
    return () => window.removeEventListener("scan-history-updated", onRefresh);
  }, [loadHistory, user]);

  if (!mounted) return null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <>
          <motion.button
            type="button"
            className="mobile-sheet-backdrop md:hidden"
            aria-label="Close history"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closeHistory}
          />
          <motion.div
            className="mobile-history-sheet md:hidden"
            role="dialog"
            aria-modal="true"
            aria-label="Assessment history"
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 32, stiffness: 360 }}
            drag="y"
            dragControls={dragControls}
            dragListener={false}
            dragConstraints={{ top: 0, bottom: 0 }}
            dragElastic={{ top: 0, bottom: 0.35 }}
            onDragEnd={(_, info) => {
              if (info.offset.y > DISMISS_OFFSET || info.velocity.y > DISMISS_VELOCITY) {
                closeHistory();
              }
            }}
          >
            <div
              className="mobile-sheet-handle-wrap"
              aria-hidden
              onPointerDown={(event) => dragControls.start(event)}
            >
              <span className="mobile-sheet-handle" />
            </div>

            <header
              className="mobile-history-sheet__header"
              onPointerDown={(event) => dragControls.start(event)}
            >
              <h2 className="font-display text-base font-bold text-[var(--color-text)]">
                Previous assessments
              </h2>
              {items.length > 0 && (
                <span className="rounded-full border border-border bg-white/[0.03] px-2 py-0.5 text-xs font-semibold tabular-nums text-[var(--color-text-muted)]">
                  {items.length}
                </span>
              )}
            </header>

            <div className="mobile-history-sheet__body">
              {!configured || authLoading ? (
                <PageLoader compact label="Loading history" sublabel="Fetching your saved assessments" />
              ) : !user ? (
                <div className="mobile-history-sheet__empty">
                  <p className="font-medium text-[var(--color-text)]">Sign in to view history</p>
                  <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                    Your saved assessments appear here after you sign in.
                  </p>
                  <button
                    type="button"
                    className="btn btn-primary mt-4 w-full"
                    onClick={() => {
                      closeHistory();
                      openAuth("signin");
                    }}
                  >
                    Sign in
                  </button>
                </div>
              ) : loading && items.length === 0 ? (
                <div className="flex items-center justify-center gap-2 py-10 text-sm text-[var(--color-text-muted)]">
                  <Loader2 className="h-4 w-4 animate-spin text-mint" />
                  Loading assessments…
                </div>
              ) : (
                <HistoryList
                  items={items}
                  openInNewTab
                  onItemClick={closeHistory}
                  emptyMessage="No saved assessments yet. Run a scan while signed in and it will appear here."
                />
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>,
    document.body,
  );
}
