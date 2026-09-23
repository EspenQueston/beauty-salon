"use client";

/**
 * Barre de réservation fixe, en bas de l'écran.
 *
 * Elle n'apparaît qu'après le premier écran : au chargement, le bouton du
 * haut de page est déjà visible, et deux appels à l'action superposés se
 * neutralisent. Elle disparaît sur la page de réservation, où elle
 * renverrait vers l'écran qu'on est en train de remplir.
 */

import { useTranslations } from "next-intl";

import { Lien } from "@/features/ui/Lien";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { whatsappHref } from "./contact";
import { SalonIcon } from "./icons";
import type { PublicSalon } from "@/lib/types";

export function BookingBar({ salon }: { salon: PublicSalon }) {
  const t = useTranslations("salon");
  const c = useTranslations("commun");
  const pathname = usePathname();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > 420);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  if (pathname.startsWith("/reserver")) return null;

  const whatsapp = whatsappHref(salon.whatsapp_number);

  return (
    <div
      aria-hidden={!visible}
      className={`fixed inset-x-0 bottom-0 z-30 border-t border-[var(--site-line)] bg-[var(--site-surface)]/95 p-3 backdrop-blur transition-transform duration-300 marge-basse-sure ${
        visible ? "translate-y-0" : "translate-y-full"
      }`}
    >
      <div className="mx-auto flex max-w-5xl items-center gap-3">
        <div className="hidden min-w-0 flex-1 sm:block">
          <p className="truncate font-medium text-[var(--site-ink)]">
            {salon.name}
          </p>
          <p className="truncate text-sm text-[var(--site-muted)]">
            {t("reservationImmediate")}
          </p>
        </div>

        {whatsapp && (
          <a
            href={whatsapp}
            target="_blank"
            rel="noreferrer noopener"
            aria-label={t("ecrireWhatsApp")}
            tabIndex={visible ? undefined : -1}
            className="flex size-12 shrink-0 items-center justify-center rounded-xl border border-[var(--site-line)] text-[var(--site-muted)] transition hover:border-[var(--salon-primary)] hover:text-[var(--salon-ink)]"
          >
            <SalonIcon name="whatsapp" className="size-5" />
          </a>
        )}

        <Lien
          href="/reserver"
          tabIndex={visible ? undefined : -1}
          className="salon-gradient flex flex-1 items-center justify-center gap-2 rounded-xl px-6 py-3.5 font-semibold text-white shadow-sm transition hover:brightness-110 sm:flex-none"
        >
          <SalonIcon name="calendar" className="size-4.5" />
          {c("reserver")}
        </Lien>
      </div>
    </div>
  );
}
