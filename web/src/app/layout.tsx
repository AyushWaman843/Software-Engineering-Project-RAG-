import type { Metadata } from "next";
import { Inter, Space_Grotesk, JetBrains_Mono } from "next/font/google";
import { AppShell } from "@/components/layout/AppShell";
import { LOGO_PATH } from "@/components/brand/BrandLogo";
import { ThemeScript } from "@/components/theme/ThemeScript";
import "./globals.css";

const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const display = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "DPDP Compliance Scanner",
    template: "%s | DPDP Scanner",
  },
  description:
    "Evaluate privacy policies against India's Digital Personal Data Protection Act, 2025 and DPDP Rules, 2025.",
  icons: {
    icon: LOGO_PATH,
    apple: LOGO_PATH,
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${sans.variable} ${display.variable} ${mono.variable}`}
      suppressHydrationWarning
    >
      <head>
        <ThemeScript />
        <style
          dangerouslySetInnerHTML={{
            __html: `
              html,body{background:var(--bg,#070a11)!important;color:var(--text,#e9eef9);margin:0}
              #initial-loader{position:fixed;inset:0;z-index:99999;background:var(--bg,#070a11)}
            `,
          }}
        />
      </head>
      <body className="relative flex min-h-screen flex-col font-sans">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
