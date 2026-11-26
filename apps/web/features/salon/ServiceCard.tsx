/**
 * Une prestation, telle qu'une cliente la choisit.
 *
 * Trois informations décident de la réservation, et dans cet ordre : ce que
 * c'est, combien de temps ça prend, combien ça coûte. Le prix est donc
 * toujours à la même place, en couleur de marque, et jamais tronqué — un
 * tarif qu'on doit chercher est un tarif dont on se méfie.
 */

import { useTranslations } from "next-intl";

import { Lien } from "@/features/ui/Lien";

import { formatDuration } from "@/lib/format";
import { Prix } from "./Devise";
import {
  illustrationUrl,
  pickIllustration,
  type Illustration,
  type IllustrationTheme,
} from "@/lib/illustrations";
import type { PublicService } from "@/lib/types";
import { SalonIcon, type SalonIconName } from "./icons";
import { Relief } from "@/features/ui/Relief";
import { Pill, SURFACE } from "./ui";
import { photo, TAILLES } from "./images";
import { TeinteDeMarque } from "./Teinte";

export function ServiceCard({
  service,
  icon,
  theme,
  fallback,
}: {
  service: PublicService;
  icon: SalonIconName;
  /** Famille de la catégorie : choisit l'illustration à défaut de photo. */
  theme: IllustrationTheme;
  /**
   * Illustration imposée par la grille qui contient la carte.
   *
   * Une carte isolée sait très bien choisir la sienne. Une grille, non :
   * toutes les prestations d'un salon de tresses partagent le même thème, et
   * le vivier correspondant compte quatre photos. Chacune tirant de son
   * côté, les quatre cartes en vedette affichaient la même image. Seul
   * l'appelant connaît les voisines, donc seul lui peut répartir.
   */
  fallback?: Illustration;
}) {
  const t = useTranslations("salon");
  const c = useTranslations("commun");
  const deposit = service.requires_deposit;

  // Une carte sans visuel casse la grille et se lit comme une fiche
  // inachevée. L'illustration est choisie par l'identifiant de la
  // prestation : elle ne change pas d'une visite à l'autre.
  const illustration = service.image
    ? null
    : (fallback ?? pickIllustration(service.id, theme));

  return (
    <Relief className="h-full">
      <Lien
        href={`/reserver?service=${service.id}`}
        // Une adresse par prestation : prechargees toutes a l'affichage du
        // catalogue, elles faisaient autant de rendus serveur que de cartes
        // visibles. La page de reservation, elle, est deja prechargee par le
        // bouton « Reserver » du menu.
        prefetch={false}
        className={`${SURFACE} group flex h-full flex-col overflow-hidden transition-shadow hover:shadow-[0_14px_32px_-10px_rgb(23_23_28_/_0.22)]`}
      >
        {service.image ? (
          <span className="relative block aspect-[16/10] overflow-hidden bg-black/[0.04]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              {...photo(service.image, TAILLES.cartes)}
              alt={service.image.alt_text || service.name}
              loading="lazy"
              className="size-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"
            />
            <TeinteDeMarque />
          </span>
        ) : (
          <span className="relative block aspect-[16/10] overflow-hidden bg-black/[0.04]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={illustrationUrl(illustration!.id, {
                width: 640,
                ratio: 0.63,
              })}
              alt=""
              loading="lazy"
              className="size-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"
            />
            {/* Teinte de marque : l'illustration reste au service du salon,
                elle ne prend pas le dessus sur son identité. */}
            <TeinteDeMarque />
            <span
              aria-hidden
              className="absolute bottom-2 left-2 flex size-8 items-center justify-center rounded-lg bg-white/85 text-[var(--salon-ink-white)] backdrop-blur"
            >
              <SalonIcon name={icon} className="size-4" />
            </span>
          </span>
        )}

        {/*
          Deux cartes par ligne sur téléphone : une seule colonne obligeait à
          faire défiler neuf écrans pour parcourir un catalogue. Les tailles
          se resserrent en dessous de `sm` — sur 170 px de large, le
          remplissage d'un écran d'ordinateur ne laisse plus de place au
          texte.
        */}
        {/*
          Une seule disposition pour toutes les cartes, de tous les salons :
          le nom, puis le prix dessous, puis la durée. Le prix ne remonte
          jamais à côté d'un nom court — c'est ce qui donnait des cartes de
          hauteurs différentes côte à côte. Le nom et la description gardent
          chacun un nombre de lignes plafonné (deux ; trois pour la
          description sur grand écran), et le bloc de texte une hauteur
          réservée — celle d'un nom sur deux lignes et d'une description
          pleine, mesurée : 9,2rem sur téléphone, 11,5rem au-delà. Toutes les
          cartes ont ainsi la même taille, et l'espace libre d'un texte court
          tombe au-dessus de « Réserver », pas entre le nom et son prix.
        */}
        <span className="flex flex-1 flex-col p-3.5 sm:p-5">
          <span className="flex min-h-[9.2rem] flex-col sm:min-h-[11.5rem]">
          <span className="flex flex-col items-start gap-1">
            <span
              title={service.name}
              className="line-clamp-2 text-[0.9rem] font-semibold leading-snug text-[var(--site-ink)] sm:text-base"
            >
              {service.name}
            </span>
            {/*
              Le prix passe par `<Prix>`, seul morceau client de cette carte.

              Il doit suivre la devise que la visiteuse a choisi de lire, et
              ce choix ne peut pas être connu du serveur. Rendre la carte
              entière côté client pour un seul nombre serait payer cher un
              détail : seul le nombre descend.
            */}
            {service.price_kind === "quote" ? (
              <span className="shrink-0 text-sm font-semibold text-[var(--salon-ink)] sm:text-base">
                {t("prix.surDevis")}
              </span>
            ) : (
              <Prix
                montant={service.price_amount}
                prefixe={
                  service.price_kind === "from" ? t("prix.aPartirDeSeul") : ""
                }
                className="tabular shrink-0 text-sm font-semibold text-[var(--salon-ink)] sm:text-base"
              />
            )}
          </span>

          <span className="mt-2 flex flex-wrap items-center gap-1.5">
            <Pill>
              <SalonIcon name="clock" className="size-3.5" />
              {formatDuration(service.duration_minutes)}
            </Pill>
            {deposit && <Pill tone="accent">{t("acompte")}</Pill>}
          </span>

          {service.description && (
            <span className="mt-2.5 line-clamp-2 text-[0.8rem] leading-relaxed text-[var(--site-muted)] sm:mt-3 sm:line-clamp-3 sm:text-sm">
              {service.description}
            </span>
          )}
          </span>

          <span className="mt-auto flex items-center gap-1.5 pt-4 text-[0.8rem] font-medium text-[var(--salon-ink)] sm:pt-5 sm:text-sm">
            {c("reserver")}
            <SalonIcon
              name="arrow"
              className="size-4 transition-transform group-hover:translate-x-1"
            />
          </span>
        </span>
      </Lien>
    </Relief>
  );
}
