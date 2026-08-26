import type { Metadata } from "next";
import { LegalDocumentShell } from "@/components/legal/LegalDocumentShell";
import { PrivacyPolicyContent } from "@/components/legal/PrivacyPolicyContent";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "DPDP Scanner Privacy Policy — how we collect, use, and protect personal data under the DPDP Act, 2025.",
};

export default function PrivacyPolicyPage() {
  return (
    <LegalDocumentShell title="Privacy Policy" updated="Last Updated: 22 June 2026">
      <PrivacyPolicyContent />
    </LegalDocumentShell>
  );
}
