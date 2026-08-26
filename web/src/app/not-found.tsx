import Link from "next/link";
import { Compass } from "lucide-react";

export default function NotFound() {
  return (
    <div className="panel mx-auto max-w-lg overflow-hidden p-10 text-center">
      <div className="mx-auto mb-5 grid h-14 w-14 place-items-center rounded-2xl border border-mint/30 bg-mint/10 text-mint">
        <Compass className="h-7 w-7" />
      </div>
      <p className="font-display text-6xl font-bold tracking-tight gradient-text">404</p>
      <h1 className="mt-3 font-display text-2xl font-bold text-white">Page not found</h1>
      <p className="mt-2 text-[var(--color-text-muted)]">
        The requested assessment or page does not exist.
      </p>
      <Link href="/" className="btn btn-primary mt-7 inline-flex">
        Back to assessments
      </Link>
    </div>
  );
}
