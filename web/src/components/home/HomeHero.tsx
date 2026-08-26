"use client";

import { motion } from "framer-motion";

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.09, delayChildren: 0.05 } },
};

const item = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] as const } },
};

const features = [
  { label: "AI + Rules engine" },
  { label: "Indicator-level scoring" },
  { label: "URL & PDF sources" },
];

/** Desktop-only marketing hero. Mobile uses the compact intro on the home page. */
export function HomeHero() {
  return (
    <motion.section
      variants={container}
      initial="hidden"
      animate="show"
      className="mb-9 text-center"
    >
      <motion.span
        variants={item}
        className="inline-flex items-center gap-2 rounded-full border border-border-strong bg-white/[0.03] px-3.5 py-1.5 text-[0.7rem] font-semibold uppercase tracking-[0.2em] text-mint-soft backdrop-blur"
      >
        DPDP Act 2025 &middot; Rules 2025
      </motion.span>

      <motion.h1
        variants={item}
        className="mx-auto mt-6 max-w-3xl font-display text-4xl font-bold leading-[1.08] tracking-tight sm:text-[3.25rem]"
      >
        <span className="gradient-text">Privacy compliance,</span>
        <br />
        <span className="text-[var(--color-text)]">quantified in seconds.</span>
      </motion.h1>

      <motion.p
        variants={item}
        className="mx-auto mt-5 max-w-2xl text-base leading-relaxed text-[var(--color-text-muted)]"
      >
        Evaluate privacy policies and related disclosures against India&apos;s Digital Personal Data
        Protection Act, 2025 and the DPDP Rules, 2025 — with an auditable, indicator-level verdict.
      </motion.p>

      <motion.ul
        variants={item}
        className="mx-auto mt-7 flex flex-wrap items-center justify-center gap-2.5"
      >
        {features.map(({ label }) => (
          <li
            key={label}
            className="inline-flex items-center gap-2 rounded-full border border-border bg-white/[0.02] px-3.5 py-1.5 text-xs font-medium text-[var(--color-text-muted)]"
          >
            {label}
          </li>
        ))}
      </motion.ul>
    </motion.section>
  );
}
