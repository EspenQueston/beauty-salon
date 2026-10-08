"use client";

import { useLocale, useTranslations } from "next-intl";

import { platformUrl } from "@/lib/site";
import { BeautySalonSymbol } from "@/features/ui/BeautySalonBrand";

/** Discreet platform signature, shared by the mini-site and booking receipt. */
export function BeautySalonCredit() {
  const locale = useLocale();
  const t = useTranslations("salon");
  const href = locale === "en" ? `${platformUrl}/en` : `${platformUrl}/`;

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="group inline-flex max-w-full items-center gap-2 rounded-full border border-[var(--site-line)] bg-[var(--site-surface)] px-2 py-1.5 pr-3.5 text-[0.75rem] text-[var(--site-muted)] shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-[var(--salon-primary)] hover:text-[var(--site-ink)] hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--salon-primary)] active:translate-y-0 motion-reduce:transform-none sm:text-[0.8rem]"
    >
      <BeautySalonSymbol className="size-6" />
      <span className="min-w-0">
        {t("creeAvec")} <strong className="font-semibold text-[var(--site-ink)]">Beauty Salon</strong>
      </span>
      <svg
        aria-hidden="true"
        viewBox="0 0 16 16"
        fill="none"
        className="size-3.5 shrink-0 transition-transform group-hover:translate-x-0.5 motion-reduce:transform-none"
      >
        <path d="M3 8h9m-4-4 4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </a>
  );
}
