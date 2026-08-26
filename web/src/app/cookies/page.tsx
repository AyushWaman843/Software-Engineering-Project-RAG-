import type { Metadata } from "next";
import { LegalDocumentShell } from "@/components/legal/LegalDocumentShell";
import { CookiePolicyContent } from "@/components/legal/CookiePolicyContent";

export const metadata: Metadata = {
  title: "Cookie Policy",
  description: "DPDP Scanner Cookie Policy — how we use cookies on our platform.",
};

export default function CookiePolicyPage() {
  return (
    <LegalDocumentShell title="Cookie Policy" updated="Last Updated: 22 June 2026">
      <CookiePolicyContent />
    </LegalDocumentShell>
  );
}
