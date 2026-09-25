/**
 * Un salon dont les réservations en ligne sont fermées.
 *
 * Cela arrive quand son abonnement est échu ou suspendu. Le mini-site reste
 * en ligne — la vitrine, les prestations, les avis, les coordonnées — mais
 * il ne laisse plus remplir un formulaire que le serveur refuserait. Il le
 * dit tôt, et propose ce qui reste possible : appeler, écrire.
 *
 * La cliente n'a pas à savoir pourquoi. Rien ici ne parle d'abonnement.
 */

import { useTranslations } from "next-intl";

import { Lien } from "@/features/ui/Lien";
import type { PublicSalon } from "@/lib/types";

import { contactLinks } from "./contact";
import { SalonIcon } from "./icons";
import { PrimaryLink } from "./ui";

export function reservationsFermees(salon: PublicSalon): boolean {
  return salon.reservations_ouvertes === false;
}

/** Bandeau fin, sous la navigation, sur toutes les pages du mini-site. */
export function BandeauFermeture() {
  const t = useTranslations("salon.fermeture");
  return (
    <div
      role="status"
      className="border-b border-[var(--site-line)] bg-[var(--site-surface)] px-4 py-2.5 text-center text-[13px] text-[var(--site-muted)] sm:text-sm"
    >
      {t("bandeau")}
    </div>
  );
}

/** Ce que montre la page « Réserver » à la place du parcours. */
export function ReservationsFermees({ salon }: { salon: PublicSalon }) {
  const t = useTranslations("salon.fermeture");
  const s = useTranslations("salon");
  const liens = contactLinks(salon);

  return (
    <section className="mx-auto flex max-w-xl flex-col items-center px-4 py-16 text-center sm:py-24">
      <span className="flex size-14 items-center justify-center rounded-full bg-[var(--salon-primary-soft)] text-[var(--salon-ink)]">
        <SalonIcon name="calendar" className="size-6" />
      </span>
      <h1 className="mt-5 text-2xl font-semibold tracking-tight text-[var(--site-ink)] sm:text-3xl">
        {t("titre")}
      </h1>
      <p className="mt-3 text-sm leading-relaxed text-[var(--site-muted)] sm:text-base">
        {t("texte", { salon: salon.name })}
      </p>

      {liens.length > 0 && (
        <div className="mt-7 grid w-full grid-cols-2 gap-2.5 sm:flex sm:w-auto sm:justify-center">
          {liens.map((lien) => (
            <PrimaryLink
              key={lien.key}
              href={lien.href}
              icon={lien.icon}
              external={lien.external}
              className={liens.length === 1 ? "col-span-2" : ""}
            >
              {lien.key === "whatsapp" ? s("ecrireWhatsApp") : t("appeler")}
            </PrimaryLink>
          ))}
        </div>
      )}

      <Lien
        href="/"
        className="mt-6 text-sm font-medium text-[var(--salon-ink)] underline-offset-4 hover:underline"
      >
        {t("retour")}
      </Lien>
    </section>
  );
}
