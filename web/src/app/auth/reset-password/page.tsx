import { Suspense } from "react";
import { ResetPasswordPage } from "./ResetPasswordClient";

export default function Page() {
  return (
    <Suspense
      fallback={
        <div className="panel mx-auto mt-16 max-w-md p-8 text-center text-sm text-[var(--color-text-muted)]">
          Loading…
        </div>
      }
    >
      <ResetPasswordPage />
    </Suspense>
  );
}
