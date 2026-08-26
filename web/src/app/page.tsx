import dynamic from "next/dynamic";
import { HomeHero } from "@/components/home/HomeHero";
import { ScanFormLazy } from "@/components/home/ScanFormLazy";
import { PageLoader } from "@/components/ui/PageLoader";

const UserHistoryPanel = dynamic(
  () => import("@/components/home/UserHistoryPanel").then((mod) => mod.UserHistoryPanel),
  {
    loading: () => (
      <div className="panel overflow-hidden p-4">
        <PageLoader compact label="Loading history" sublabel="Fetching recent scans" />
      </div>
    ),
  },
);

export default function HomePage() {
  return (
    <div className="flex min-w-0 flex-col">
      <div className="hidden md:block">
        <HomeHero />
      </div>

      <div className="grid min-w-0 grid-cols-1 items-start gap-4 md:gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className="min-w-0 overflow-hidden md:panel">
          <header className="hidden panel-header md:block">
            <h2 className="font-display text-xl font-bold tracking-tight text-[var(--color-text)]">
              Configure assessment
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-[var(--color-text-muted)]">
              Sign in, then provide a website URL or upload policy documents to begin a DPDP evaluation.
            </p>
          </header>
          <ScanFormLazy />
        </section>

        <div className="hidden lg:block">
          <UserHistoryPanel />
        </div>
      </div>
    </div>
  );
}
