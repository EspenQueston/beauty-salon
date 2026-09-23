/**
 * Le récit du salon, en chapitres alternés.
 *
 * ---------------------------------------------------------------------------
 * Le défaut que ça corrige
 * ---------------------------------------------------------------------------
 *
 * La page tenait en deux colonnes : le texte à gauche, une image collante à
 * droite. Tant que le récit faisait la hauteur de l'image, l'équilibre
 * tenait. Dès qu'il la dépassait — c'est-à-dire dès qu'un salon prend la
 * peine d'écrire — le texte continuait seul dans une colonne étroite avec un
 * grand vide à sa droite. Plus le salon écrivait, plus sa page paraissait
 * inachevée.
 *
 * ---------------------------------------------------------------------------
 * Le principe
 * ---------------------------------------------------------------------------
 *
 * Le récit est découpé en chapitres de trois paragraphes, et chaque chapitre
 * change de côté : texte à gauche, puis à droite, puis à gauche. En face,
 * une image différente à chaque fois. Le vide disparaît parce qu'il n'y a
 * plus de colonne unique qui file — il y a des paires.
 *
 * Trois paragraphes par chapitre n'est pas un chiffre rond choisi au hasard :
 * c'est la hauteur qui équilibre une image au format 4/5 dans une colonne de
 * cette largeur. En dessous, l'image dépasse ; au-dessus, le texte dépasse à
 * nouveau et le problème revient.
 *
 * ---------------------------------------------------------------------------
 * D'où viennent les images
 * ---------------------------------------------------------------------------
 *
 * De la galerie du salon, c'est-à-dire de son vrai travail. L'image « à
 * propos » qu'il a choisie ouvre le récit ; les réalisations prennent la
 * suite. À défaut, des illustrations d'ambiance, tirées de façon
 * déterministe — la même page montre toujours les mêmes, sinon chaque visite
 * donnerait une page différente sans raison.
 *
 * ---------------------------------------------------------------------------
 * Le tableau de chiffres, en deuxième position
 * ---------------------------------------------------------------------------
 *
 * Un chapitre sur deux pouvait accueillir autre chose qu'une image, et
 * c'est le moment de montrer ce que le salon est en chiffres : prestations,
 * prestataires, spécialités. Placé en deuxième chapitre, il arrive une fois
 * l'attention acquise et avant qu'elle ne retombe — en bas de page il aurait
 * doublé le récapitulatif qui s'y trouve déjà.
 *
 * ---------------------------------------------------------------------------
 * Sur téléphone
 * ---------------------------------------------------------------------------
 *
 * Une seule colonne, et c'est délibéré : de la prose sur deux colonnes de
 * 160 px se lit trois mots à la fois. L'alternance gauche/droite n'a pas de
 * sens non plus — tout est empilé. Ce qui reste, et qui compte, c'est
 * l'alternance texte / image, qui donne au défilement un rythme au lieu d'un
 * mur.
 */

import { useTranslations } from "next-intl";
import { Lien } from "@/features/ui/Lien";

import { Reveal } from "@/features/ui/Reveal";
import {
  illustrationUrl,
  pickIllustration,
  themeFromCategory,
} from "@/lib/illustrations";
import type { PublicSalon } from "@/lib/types";

import { SalonIcon } from "./icons";

/** Paragraphes par chapitre : la hauteur qui équilibre une image en 4/5. */
const PAR_CHAPITRE = 3;

/** Rang du chapitre dont le vis-à-vis est le tableau de chiffres. */
const RANG_DES_CHIFFRES = 1;

interface Visuel {
  url: string;
  alt: string;
}

export function AboutStory({
  paragraphs,
  minutes,
  salon,
  title,
}: {
  paragraphs: string[];
  minutes: number;
  salon: PublicSalon;
  title: string;
}) {
  const t = useTranslations("salon");
  const chapitres = decouper(paragraphs, PAR_CHAPITRE);
  const visuels = rassemblerVisuels(salon, title, chapitres.length);
  const chiffres = compterLesChiffres(salon, t);

  // Le tableau ne remplace une image que s'il a de quoi se remplir et qu'il
  // reste un chapitre pour l'accueillir.
  const rangDesChiffres =
    chiffres.length >= 3 && chapitres.length > RANG_DES_CHIFFRES
      ? RANG_DES_CHIFFRES
      : -1;

  return (
    <div className="space-y-10 sm:space-y-14">
      {chapitres.map((chapitre, rang) => (
        <Chapitre
          key={rang}
          rang={rang}
          premier={rang === 0}
          dernier={rang === chapitres.length - 1}
          paragraphes={chapitre}
          minutes={minutes}
          salon={salon}
        >
          {rang === rangDesChiffres ? (
            <TableauDeChiffres chiffres={chiffres} />
          ) : (
            <Illustration visuel={visuels[rang % visuels.length]} />
          )}
        </Chapitre>
      ))}
    </div>
  );
}

/**
 * Un chapitre : du texte, et son vis-à-vis.
 *
 * Le côté s'inverse un rang sur deux. `lg:order-*` plutôt que deux gabarits
 * séparés : l'ordre du document reste celui de la lecture — texte puis
 * image — donc un lecteur d'écran et un téléphone reçoivent la bonne
 * séquence quel que soit le côté affiché.
 */
function Chapitre({
  rang,
  premier,
  dernier,
  paragraphes,
  minutes,
  salon,
  children,
}: {
  rang: number;
  premier: boolean;
  dernier: boolean;
  paragraphes: string[];
  minutes: number;
  salon: PublicSalon;
  children: React.ReactNode;
}) {
  const t = useTranslations("salon");
  const c = useTranslations("commun");
  const texteADroite = rang % 2 === 1;

  return (
    <section className="grid items-start gap-6 sm:gap-8 lg:grid-cols-[1.15fr_1fr]">
      <div className={`min-w-0 ${texteADroite ? "lg:order-2" : ""}`}>
        {premier && (
          <Reveal>
            <p className="mb-5 inline-flex items-center gap-2 rounded-full bg-[var(--salon-accent)] px-3 py-1.5 text-xs font-medium text-[var(--salon-ink-accent)]">
              <SalonIcon name="clock" className="size-3.5" />
              {t("pages.lecture", { n: minutes })}
            </p>
          </Reveal>
        )}

        {/* 62 caractères : la mesure au-delà de laquelle l'œil perd le retour
            à la ligne. Le plafond porte sur le texte, pas sur la colonne. */}
        <div className="max-w-[62ch] space-y-5">
          {paragraphes.map((paragraphe, index) => (
            <Reveal key={index} delay={Math.min(index, 3) * 60}>
              {premier && index === 0 ? (
                <p className="text-lg leading-relaxed text-[var(--site-ink)] first-letter:float-left first-letter:mr-2.5 first-letter:mt-1 first-letter:text-5xl first-letter:font-semibold first-letter:leading-[0.8] first-letter:text-[var(--salon-ink)]">
                  {paragraphe}
                </p>
              ) : (
                <p className="leading-relaxed text-[var(--site-muted)]">
                  {paragraphe}
                </p>
              )}
            </Reveal>
          ))}
        </div>

        {/* La signature ne se met qu'une fois, à la fin du récit. */}
        {dernier && (
          <Reveal className="mt-8 max-w-[62ch]">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-l-2 border-[var(--salon-primary)] pl-4">
              <p className="text-sm text-[var(--site-muted)]">
                <span className="font-medium text-[var(--site-ink)]">
                  {salon.name}
                </span>
                {salon.city && ` · ${salon.city}`}
              </p>
              <Lien
                href="/reserver"
                className="text-sm font-medium text-[var(--salon-ink)] underline-offset-2 hover:underline"
              >
                {c("prendreRdv")} →
              </Lien>
            </div>
          </Reveal>
        )}
      </div>

      <Reveal delay={90} className={texteADroite ? "lg:order-1" : ""}>
        {/*
          Le vis-à-vis reste collé tant que le chapitre défile.

          Un chapitre plus long que son image laisserait sinon réapparaître le
          vide qu'on vient de supprimer — en plus petit, mais au même endroit.
        */}
        <div className="lg:sticky lg:top-24">{children}</div>
      </Reveal>
    </section>
  );
}

function Illustration({ visuel }: { visuel: Visuel }) {
  return (
    <figure className="overflow-hidden rounded-3xl">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={visuel.url}
        alt={visuel.alt}
        loading="lazy"
        className="aspect-[4/5] w-full object-cover"
      />
    </figure>
  );
}

interface Chiffre {
  icon: "scissors" | "star" | "sparkle" | "pin";
  valeur: string;
  libelle: string;
  href: string;
}

/**
 * Le salon en chiffres, à la place d'une image.
 *
 * Aucun n'est saisi à la main : un « 15 ans d'expérience » qu'on écrit
 * soi-même ne prouve rien, alors qu'un nombre de prestations vient du
 * catalogue et se vérifie d'un clic. Chaque ligne mène donc à ce qu'elle
 * annonce — un chiffre qui intrigue sans rien ouvrir est une impasse.
 */
function TableauDeChiffres({ chiffres }: { chiffres: Chiffre[] }) {
  return (
    <div className="overflow-hidden rounded-3xl border border-[var(--site-line)] bg-[var(--site-surface)] shadow-[0_1px_3px_rgb(23_23_28_/_0.05)]">
      <p className="salon-gradient px-5 py-3 text-sm font-medium text-white">
        {/* Le titre dit ce qu'on regarde : sans lui, quatre nombres alignés
            au milieu d'un récit sont une énigme. */}
        Le salon en chiffres
      </p>

      <ul className="divide-y divide-[var(--site-line)]">
        {chiffres.map((chiffre) => (
          <li key={chiffre.libelle}>
            <Lien
              href={chiffre.href}
              className="group flex items-center gap-3.5 px-5 py-3.5 transition hover:bg-[var(--salon-primary)]/[0.04]"
            >
              <span
                className="flex size-9 shrink-0 items-center justify-center rounded-xl transition-transform duration-300 group-hover:scale-110"
                style={{
                  background: "var(--salon-accent)",
                  color: "var(--salon-ink-accent)",
                }}
              >
                <SalonIcon name={chiffre.icon} className="size-4" />
              </span>

              <span className="min-w-0 flex-1">
                <span
                  className={`block font-semibold text-[var(--site-ink)] ${
                    chiffre.valeur.length > 4 ? "text-base" : "tabular text-xl"
                  }`}
                >
                  {chiffre.valeur}
                </span>
                <span className="block truncate text-xs text-[var(--site-muted)]">
                  {chiffre.libelle}
                </span>
              </span>

              <SalonIcon
                name="arrow"
                className="size-4 shrink-0 text-[var(--salon-ink)] opacity-40 transition-all duration-300 group-hover:translate-x-0.5 group-hover:opacity-100"
              />
            </Lien>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* -------------------------------------------------------------------------
 * Assemblage des données
 * ---------------------------------------------------------------------- */

function decouper(paragraphes: string[], taille: number): string[][] {
  const blocs: string[][] = [];
  for (let i = 0; i < paragraphes.length; i += taille) {
    blocs.push(paragraphes.slice(i, i + taille));
  }

  // Un dernier chapitre d'un seul paragraphe pend tristement à côté d'une
  // image pleine hauteur : il rejoint le précédent.
  if (blocs.length > 1 && blocs[blocs.length - 1].length === 1) {
    const orphelin = blocs.pop()!;
    blocs[blocs.length - 1].push(...orphelin);
  }
  return blocs;
}

/**
 * Les images des chapitres, par ordre de légitimité.
 *
 * Celle que le salon a choisie pour sa page ouvre le récit — c'est son
 * intention. Viennent ensuite ses réalisations, qui sont son vrai travail.
 * Les illustrations d'ambiance ne servent qu'à combler, et seulement s'il
 * reste des chapitres sans rien en face.
 */
function rassemblerVisuels(
  salon: PublicSalon,
  title: string,
  combien: number,
): Visuel[] {
  const visuels: Visuel[] = [];

  if (salon.about_image) {
    visuels.push({
      url: salon.about_image.url,
      alt: salon.about_image.alt_text || title,
    });
  }

  for (const media of salon.gallery) {
    if (visuels.length >= combien) break;
    // Les vidéos de la galerie ne conviennent pas ici : elles appellent une
    // lecture, et ce vis-à-vis doit se regarder sans rien demander.
    if (media.content_type.startsWith("video/")) continue;
    visuels.push({ url: media.url, alt: media.alt_text || "" });
  }

  const theme = salon.categories[0]
    ? themeFromCategory(salon.categories[0].name)
    : "salon";

  // Le tirage est déterministe : la même page montre toujours les mêmes
  // images, sinon chaque visite donnerait une page différente sans raison.
  let secours = 0;
  while (visuels.length < Math.max(1, combien)) {
    const choix = pickIllustration(`${salon.slug}-about-${secours}`, theme);
    visuels.push({
      url: illustrationUrl(choix.id, { width: 900, ratio: 1.25 }),
      alt: "",
    });
    secours += 1;
  }

  return visuels;
}

/* Le traducteur arrive en paramètre : ce n'est pas un composant. */
function compterLesChiffres(
  salon: PublicSalon,
  t: (cle: string, vars?: Record<string, string | number | Date>) => string,
): Chiffre[] {
  const prestations = salon.categories.reduce(
    (total, category) => total + category.services.length,
    0,
  );

  return [
    prestations > 0 && {
      icon: "scissors" as const,
      valeur: String(prestations),
      libelle: t("prestationsCatalogue", { n: prestations }),
      href: "/prestations",
    },
    salon.staff_members.length > 0 && {
      icon: "star" as const,
      valeur: String(salon.staff_members.length),
      libelle: t("chiffres.prestataires", { n: salon.staff_members.length }),
      href: "/equipe",
    },
    salon.categories.length > 0 && {
      icon: "sparkle" as const,
      valeur: String(salon.categories.length),
      libelle: t("chiffres.specialites", { n: salon.categories.length }),
      href: "/prestations",
    },
    salon.gallery.length > 0 && {
      icon: "sparkle" as const,
      valeur: String(salon.gallery.length),
      libelle: t("chiffres.realisations"),
      href: "/realisations",
    },
    salon.city && {
      icon: "pin" as const,
      valeur: salon.city,
      libelle: t("chiffres.ouRecevoir"),
      href: "/infos",
    },
  ].filter(Boolean) as Chiffre[];
}
