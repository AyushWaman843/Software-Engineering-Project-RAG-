"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { clientApiBase, userApiHeaders } from "@/lib/api";
import { ReportView } from "@/components/report/ReportView";
import type { ReportContext } from "@/lib/types";
import type { PrevScan } from "@/lib/trend";

interface ReportViewGuardProps {
  reportId: string;
}

type AccessState = "checking" | "allowed" | "denied";

function redirectHome() {
  window.location.replace("/");
}

function clearSensitiveState(
  setAccess: (state: AccessState) => void,
  setData: (data: ReportContext | null) => void,
  setPrevious: (prev: PrevScan | null) => void,
) {
  setAccess("checking");
  setData(null);
  setPrevious(null);
}

/** Loads report data only after server confirms the current viewer may access it. */
export function ReportViewGuard({ reportId }: ReportViewGuardProps) {
  const { user, session, loading } = useAuth();
  const [access, setAccess] = useState<AccessState>("checking");
  const [data, setData] = useState<ReportContext | null>(null);
  const [previous, setPrevious] = useState<PrevScan | null>(null);
  const verifySeq = useRef(0);

  const verifyAccess = useCallback(
    async (options?: { soft?: boolean }) => {
      const soft = Boolean(options?.soft);
      const seq = ++verifySeq.current;
      if (!soft) {
        setAccess("checking");
        setData(null);
        setPrevious(null);
      }

      try {
        const res = await fetch(`${clientApiBase}/report/${encodeURIComponent(reportId)}`, {
          credentials: "include",
          cache: "no-store",
          headers: userApiHeaders(user?.id, session?.access_token),
        });

        if (seq !== verifySeq.current) return;

        if (res.status === 403 || res.status === 401) {
          setAccess("denied");
          redirectHome();
          return;
        }

        if (!res.ok) {
          if (!soft) setAccess("denied");
          return;
        }

        const next = (await res.json()) as ReportContext;
        if (seq !== verifySeq.current) return;

        const prevRes = await fetch(
          `${clientApiBase}/report/${encodeURIComponent(reportId)}/previous`,
          {
            credentials: "include",
            cache: "no-store",
            headers: userApiHeaders(user?.id, session?.access_token),
          },
        );

        if (seq !== verifySeq.current) return;

        if (prevRes.status === 403 || prevRes.status === 401) {
          setAccess("denied");
          redirectHome();
          return;
        }

        let prev: PrevScan | null = null;
        if (prevRes.ok) {
          const prevJson = (await prevRes.json()) as PrevScan | null;
          prev = prevJson?.timestamp ? prevJson : null;
        }

        if (seq !== verifySeq.current) return;

        setData({ ...next, report_id: reportId });
        setPrevious(prev);
        setAccess("allowed");
      } catch {
        if (seq !== verifySeq.current) return;
        if (!soft) {
          setAccess("denied");
          redirectHome();
        }
      }
    },
    [reportId, user?.id, session?.access_token],
  );

  useEffect(() => {
    if (loading) return;
    void verifyAccess();
  }, [loading, verifyAccess]);

  useEffect(() => {
    const onPremiumUpdated = () => {
      if (!loading && user?.id) void verifyAccess({ soft: true });
    };
    window.addEventListener("premium-status-updated", onPremiumUpdated);
    return () => window.removeEventListener("premium-status-updated", onPremiumUpdated);
  }, [loading, user?.id, verifyAccess]);

  useLayoutEffect(() => {
    const onPageShow = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      clearSensitiveState(setAccess, setData, setPrevious);
      if (!loading) void verifyAccess();
    };

    const onPageHide = () => {
      clearSensitiveState(setAccess, setData, setPrevious);
    };

    window.addEventListener("pageshow", onPageShow);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      window.removeEventListener("pageshow", onPageShow);
      window.removeEventListener("pagehide", onPageHide);
    };
  }, [loading, verifyAccess]);

  if (access !== "allowed" || !data) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <p className="text-sm text-[var(--color-text-muted)]">Verifying access…</p>
      </div>
    );
  }

  return <ReportView data={data} previous={previous} />;
}
