"use client";

import Link from "next/link";
import { ArrowUpRight, Scale, ShieldCheck } from "lucide-react";
import { BrandLogo } from "@/components/brand/BrandLogo";

const PLATFORM_LINKS = [
  { href: "/", label: "New Assessment" },
] as const;

const LEGAL_LINKS = [
  { href: "/privacy", label: "Privacy Policy" },
  { href: "/terms", label: "Terms of Service" },
  { href: "/cookies", label: "Cookie Policy" },
] as const;

function FooterLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="site-footer__link group">
      <span>{label}</span>
      <ArrowUpRight
        className="h-3 w-3 shrink-0 opacity-0 transition-all duration-200 group-hover:opacity-70 group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
        aria-hidden
      />
    </Link>
  );
}

export function SiteFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="site-footer">
      <div className="site-footer__accent" aria-hidden />

      <div className="site-footer__inner">
        <div className="site-footer__grid">
          {/* Brand */}
          <div className="site-footer__brand">
            <Link href="/" className="site-footer__brand-link group">
              <span className="site-footer__logo-wrap">
                <BrandLogo size={44} className="transition-transform duration-300 group-hover:scale-[1.04]" />
              </span>
              <span className="site-footer__brand-text">
                <span className="site-footer__brand-name gradient-text">DPDP Scanner</span>
                <span className="site-footer__brand-tag">DPDP Compliance Console</span>
              </span>
            </Link>
            <p className="site-footer__blurb">
              Automated privacy policy assessments against India&apos;s Digital Personal Data
              Protection Act, 2025 and DPDP Rules, 2025.
            </p>
            <div className="site-footer__trust">
              <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-mint-soft" aria-hidden />
              <span>Rules engine + DeepSeek expert analysis</span>
            </div>
          </div>

          {/* Platform */}
          <div className="site-footer__column">
            <h2 className="site-footer__heading">Platform</h2>
            <nav className="site-footer__nav" aria-label="Platform">
              {PLATFORM_LINKS.map((link) => (
                <FooterLink key={link.href} href={link.href} label={link.label} />
              ))}
            </nav>
          </div>

          {/* Legal */}
          <div className="site-footer__column">
            <h2 className="site-footer__heading">Legal</h2>
            <nav className="site-footer__nav" aria-label="Legal">
              {LEGAL_LINKS.map((link) => (
                <FooterLink key={link.href} href={link.href} label={link.label} />
              ))}
            </nav>
          </div>
        </div>

        <div className="site-footer__divider" aria-hidden />

        <div className="site-footer__bottom">
          <div className="site-footer__bottom-copy">
            <p className="site-footer__copyright">
              <span className="site-footer__status-dot" aria-hidden />
              &copy; <span suppressHydrationWarning>{year}</span> DPDP Scanner. All rights reserved.
            </p>
            <p className="site-footer__disclaimer">
              <Scale className="h-3.5 w-3.5 shrink-0 text-amber/80" aria-hidden />
              Generated assessments are indicative only and do not constitute legal advice.
            </p>
            <p className="mt-2 text-xs text-[var(--color-text-muted)]">
              Support:{" "}
              <a href="mailto:support@dpdpscanner.in" className="text-mint-soft hover:underline">
                support@dpdpscanner.in
              </a>
            </p>
          </div>

          <div className="site-footer__bottom-meta">
            <span className="site-footer__badge">DPDP Act, 2025</span>
            <span className="site-footer__badge site-footer__badge--live">
              <span className="site-footer__live-pulse" aria-hidden />
              DeepSeek AI
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
