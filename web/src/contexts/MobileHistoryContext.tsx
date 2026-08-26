"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { MobileHistorySheet } from "@/components/layout/MobileHistorySheet";

interface MobileHistoryContextValue {
  open: boolean;
  openHistory: () => void;
  closeHistory: () => void;
}

const MobileHistoryContext = createContext<MobileHistoryContextValue | null>(null);

export function MobileHistoryProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  const openHistory = useCallback(() => setOpen(true), []);
  const closeHistory = useCallback(() => setOpen(false), []);

  const value = useMemo(
    () => ({ open, openHistory, closeHistory }),
    [open, openHistory, closeHistory],
  );

  return (
    <MobileHistoryContext.Provider value={value}>
      {children}
      <MobileHistorySheet />
    </MobileHistoryContext.Provider>
  );
}

export function useMobileHistory() {
  const context = useContext(MobileHistoryContext);
  if (!context) {
    throw new Error("useMobileHistory must be used within MobileHistoryProvider");
  }
  return context;
}
