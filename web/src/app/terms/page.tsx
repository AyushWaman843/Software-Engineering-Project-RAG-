import type { Metadata } from "next";
import { LegalDocumentShell } from "@/components/legal/LegalDocumentShell";
import { TermsOfServiceContent } from "@/components/legal/TermsOfServiceContent";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: "DPDP Scanner Terms of Service for the DPDP compliance scanning platform.",
};

export default function TermsOfServicePage() {
  return (
    <LegalDocumentShell title="Terms of Service" updated="Effective Date: 22 June 2026">
      <TermsOfServiceContent />
    </LegalDocumentShell>
  );
}
