import { ArrowLeft } from "lucide-react";

interface LegalDocumentShellProps {
  title: string;
  updated: string;
  children: React.ReactNode;
}

export function LegalDocumentShell({ title, updated, children }: LegalDocumentShellProps) {
  return (
    <article className="mx-auto w-full max-w-4xl">
      <header className="mb-8 border-b border-border-light pb-8">
        <a
          href="/scanner"
          className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-[var(--color-text-muted)] transition-colors hover:text-mint-soft"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to assessments
        </a>
        <h1 className="font-display text-3xl font-bold tracking-tight text-white md:text-4xl">{title}</h1>
        <p className="mt-2 text-sm text-[var(--color-text-faint)]">{updated}</p>
      </header>
      <div className="legal-prose w-full">{children}</div>
    </article>
  );
}
