/**
 * Comment se passe une réservation, en trois temps.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi cette section existe
 * ---------------------------------------------------------------------------
 *
 * Une bonne partie des visiteuses arrivent d'un lien WhatsApp et n'ont jamais
 * réservé en ligne chez un salon. La question qu'elles se posent n'est pas
 * « que proposez-vous » — le catalogue y répond — mais « qu'est-ce qui se
 * passe si je clique ». Sans réponse, le doute se règle en n'appuyant pas.
 *
 * Trois étapes, donc, et rien de promotionnel : ce sont les trois écrans
 * qu'elle va réellement traverser. La troisième mentionne l'acompte quand le
 * salon en demande un, parce que c'est précisément là que la confiance se
 * joue — l'apprendre au moment de payer donne le sentiment d'un piège.
 *
 * ---------------------------------------------------------------------------
 * La numérotation, et le trait qui relie
 * ---------------------------------------------------------------------------
 *
 * Le numéro dit combien il en reste avant d'avoir fini de lire le premier.
 * Le trait qui court entre les cartes dit que ce sont des étapes et non trois
 * arguments : sans lui, l'ordre se devine, il ne se voit pas.
 */

import { useTranslations } from "next-intl";

import { SalonIcon, type SalonIconName } from "./icons";
import { PrimaryLink } from "./ui";
import type { PublicSalon } from "@/lib/types";

interface Step {
  title: string;
  body: string;
  icon: SalonIconName;
}

export function HowItWorks({ salon }: { salon: PublicSalon }) {
  const t = useTranslations("salon.etapes");
  // Un acompte est demandé dès qu'une prestation en porte un. On ne l'annonce
  // pas « au cas où » : une cliente à qui l'on parle d'acompte alors qu'il n'y
  // en a pas referme la page.
  const asksDeposit = salon.categories.some((category) =>
    category.services.some((service) => service.requires_deposit),
  );

  const steps: Step[] = [
    {
      title: t("choisirTitre"),
      body: t("choisirCorps"),
      icon: "sparkle",
    },
    {
      title: t("creneauTitre"),
      body: t("creneauCorps"),
      icon: "calendar",
    },
    {
      title: asksDeposit ? t("acompteTitre") : t("confirmeTitre"),
      body: asksDeposit ? t("acompteCorps") : t("confirmeCorps"),
      icon: asksDeposit ? "star" : "check",
    },
  ];

  return (
    <div>
      {/*
        Deux colonnes dès le téléphone, trois dès la tablette.

        Sur une colonne, ces trois cartes courtes occupent trois écrans et la
        troisième — celle qui répond à « et si je dois payer » — se lit après
        deux glissements. Deux colonnes les ramènent en un seul écran.

        La troisième prend alors toute la largeur de la seconde ligne : une
        carte orpheline centrée casse l'alignement des numéros, qui est
        justement ce qui fait lire la séquence.
      */}
      <ol className="relative grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
        {/* Le fil qui relie les étapes, sur grand écran seulement : à deux
            colonnes il traverserait un retour à la ligne et relierait
            l'étape 2 à l'étape 3 dans le mauvais sens. */}
        <span
          aria-hidden
          className="absolute inset-x-[16%] top-[2.6rem] hidden border-t border-dashed border-[var(--site-line)] lg:block"
        />

        {steps.map((step, index) => (
          <li
            key={step.title}
            className={`relative ${index === 2 ? "col-span-2 lg:col-span-1" : ""}`}
          >
            <div className="lift h-full rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] p-4 shadow-[0_1px_3px_rgb(23_23_28_/_0.05)] sm:p-5">
              <span className="salon-gradient relative z-10 flex size-10 items-center justify-center rounded-xl text-white sm:size-11">
                <SalonIcon name={step.icon} className="size-5" />
              </span>

              <p className="tabular mt-3 text-xs font-semibold tracking-[0.14em] text-[var(--site-subtle)]">
                {String(index + 1).padStart(2, "0")}
              </p>
              <h3 className="mt-0.5 text-[0.95rem] font-semibold text-[var(--site-ink)] sm:text-lg">
                {step.title}
              </h3>
              <p className="mt-1.5 text-[0.8rem] leading-relaxed text-[var(--site-muted)] sm:text-sm">
                {step.body}
              </p>
            </div>
          </li>
        ))}
      </ol>

      <div className="mt-6 flex justify-center">
        <PrimaryLink href="/reserver" icon="calendar" className="px-6 py-3">
          {t("commencer")}
        </PrimaryLink>
      </div>
    </div>
  );
}
