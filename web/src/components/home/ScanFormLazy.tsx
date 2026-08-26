"use client";

import dynamic from "next/dynamic";
import { PageLoader } from "@/components/ui/PageLoader";

/** Client-only load — avoids hydration mismatches from password managers on form inputs. */
export const ScanFormLazy = dynamic(
  () => import("@/components/home/ScanForm").then((mod) => mod.ScanForm),
  {
    ssr: false,
    loading: () => (
      <div className="px-7 pb-8 pt-2">
        <PageLoader compact label="Loading scanner" sublabel="Preparing assessment form" />
      </div>
    ),
  },
);
