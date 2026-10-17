import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { GalleryGrid } from "@/features/salon/GalleryGrid";
import { PageHero } from "@/features/salon/PageHero";
import { RealisationsExplorer } from "@/features/salon/RealisationsExplorer";
import { ReviewList } from "@/features/salon/Reviews";
import { whatsappHref } from "@/features/salon/contact";
import { PAGE_SLIDES, salonSlides } from "@/features/salon/slides";
import { SalonIcon } from "@/features/salon/icons";
import { PrimaryLink } from "@/features/salon/ui";
import { Lien } from "@/features/ui/Lien";
import { Reveal } from "@/features/ui/Reveal";
import { fetchReviews } from "@/lib/api";
import { fetchSalon } from "@/lib/salon-serveur";
import { illustrationUrl, pickIllustrations } from "@/lib/illustrations";
import { isVideo, type MediaAsset } from "@/lib/types";

type Props = { params: Promise<{ host: string }> };

// Écrites en entier : Tailwind ne voit que les classes présentes telles quelles.
const COLONNES: Record<number, string> = {
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-3",
  4: "sm:grid-cols-4",
};

/* Le titre suit la langue de l'adresse : `export const metadata` est figé
   à la compilation et ne peut pas la connaître. */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("salon.titres");
  return { title: t("realisations") };
}

/**
 * Ce que le salon a déjà fait : photos et vidéos courtes — et ce qu'on peut
 * en faire.
 *
 * La page ne s'arrête plus à la mosaïque. Dans l'ordre où une cliente se
 * décide :
 *
 *   1. **les preuves** en un coup d'œil : réalisations, note, avis, équipe ;
 *   2. **les coups de cœur** du salon, puis toute la galerie, filtrable par
 *      catégorie, chaque photo reliée à sa prestation (« Réserver ce look »)
 *      et partageable ;
 *   3. **ce qu'en disent les clientes**, à côté du travail qu'elles ont vu ;
 *   4. **le passage à l'acte** : réserver, ou écrire au salon.
 *
 * Quand le salon n'a encore rien publié, la grille montre des images
 * d'ambiance — et **le dit**. Faire passer des photos prises ailleurs pour
 * le travail d'un vrai commerce serait un mensonge sur son savoir-faire.
 */
export default async function RealisationsPage({ params }: Props) {
  const t = await getTranslations("salon");
  const g = await getTranslations("salon.galeriePlus");
  const c = await getTranslations("commun");
  const { host } = await params;
  const [salon, avis] = await Promise.all([
    fetchSalon(host),
    fetchReviews(host),
  ]);
  if (!salon) notFound();

  const hasOwnWork = salon.gallery.length > 0;
  const photos = salon.gallery.filter((asset) => !isVideo(asset)).length;
  const videos = salon.gallery.length - photos;
  const reservable = salon.reservations_ouvertes !== false;
  const whatsapp = salon.whatsapp_number
    ? whatsappHref(salon.whatsapp_number)
    : null;

  // En dessous de quatre médias, la mosaïque a l'air d'un accident. On la
  // complète — mais dans un bloc distinct, jamais mélangée aux vraies
  // réalisations.
  const SPARSE = 4;
  const topUp = Math.max(0, SPARSE * 2 - salon.gallery.length);

  // Illustrations converties au format des médias, pour réutiliser la même
  // mosaïque et la même visionneuse.
  const placeholders: MediaAsset[] = pickIllustrations(
    salon.slug,
    hasOwnWork ? topUp : 8,
  ).map((entry, index) => ({
    id: entry.id,
    url: illustrationUrl(entry.id, { width: 1000 }),
    content_type: "image/jpeg",
    alt_text: entry.alt,
    width: 1000,
    height: 750,
    kind: "gallery",
    position: index,
    featured: false,
  }));

  const showAmbience = !hasOwnWork || salon.gallery.length < SPARSE;

  // Les preuves, toutes calculées : rien d'écrit à la main qui puisse mentir.
  const specialites = salon.categories.filter(
    (categorie) => categorie.services.length > 0,
  ).length;
  const chiffres = [
    hasOwnWork && {
      valeur: String(salon.gallery.length),
      libelle: g("chiffreRealisations", { n: salon.gallery.length }),
      icone: "sparkle" as const,
    },
    salon.rating.average != null && {
      valeur: salon.rating.average.toFixed(1),
      libelle: g("chiffreNote", { n: salon.rating.count }),
      icone: "star" as const,
    },
    salon.staff_members.length > 0 && {
      valeur: String(salon.staff_members.length),
      libelle: t("chiffres.prestataires", { n: salon.staff_members.length }),
      icone: "user" as const,
    },
    specialites > 0 && {
      valeur: String(specialites),
      libelle: t("chiffres.specialites", { n: specialites }),
      icone: "scissors" as const,
    },
  ].filter(Boolean) as {
    valeur: string;
    libelle: string;
    icone: "sparkle" | "star" | "user" | "scissors";
  }[];

  return (
    <>
      <PageHero
        slides={salonSlides(salon, PAGE_SLIDES)}
        eyebrow={t("pages.realisationsSurtitre")}
        title={t("pages.realisationsTitre")}
        icon="sparkle"
        tone="galerie"
      >
        {hasOwnWork && (
          <div className="flex flex-wrap gap-2">
            {photos > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1.5 text-sm backdrop-blur">
                {t("pages.photos", { n: photos })}
              </span>
            )}
            {videos > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1.5 text-sm backdrop-blur">
                <SalonIcon name="play" className="size-3.5" filled />
                {t("pages.videos", { n: videos })}
              </span>
            )}
          </div>
        )}
      </PageHero>

      <main className="mx-auto max-w-5xl px-4 pt-8 sm:pt-10">
        {/* ----- 1. Les preuves ------------------------------------------ */}
        {chiffres.length >= 2 && (
          <Reveal as="section" className="mb-10 sm:mb-12">
            {/* Deux colonnes sur téléphone (la dernière tuile d'un nombre
                impair prend toute la ligne), autant que de chiffres au-delà. */}
            <dl
              className={`grid grid-cols-2 gap-2.5 sm:gap-3 [&>*:last-child:nth-child(odd)]:col-span-2 sm:[&>*:last-child:nth-child(odd)]:col-span-1 ${
                COLONNES[chiffres.length] ?? "sm:grid-cols-4"
              }`}
            >
              {chiffres.map((chiffre) => (
                <div
                  key={chiffre.libelle}
                  className="flex items-center gap-3 rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] p-3 sm:p-4"
                >
                  <span
                    className="flex size-9 shrink-0 items-center justify-center rounded-xl sm:size-10"
                    style={{
                      background: "var(--salon-accent)",
                      color: "var(--salon-ink-accent)",
                    }}
                  >
                    <SalonIcon
                      name={chiffre.icone}
                      className="size-4 sm:size-5"
                      filled={chiffre.icone === "star"}
                    />
                  </span>
                  <div className="min-w-0">
                    <dd className="tabular text-lg font-semibold leading-none text-[var(--site-ink)] sm:text-xl">
                      {chiffre.valeur}
                    </dd>
                    <dt className="mt-1 truncate text-[0.72rem] text-[var(--site-muted)] sm:text-xs">
                      {chiffre.libelle}
                    </dt>
                  </div>
                </div>
              ))}
            </dl>
          </Reveal>
        )}

        {/* ----- 2. Le travail ------------------------------------------- */}
        {hasOwnWork && (
          <section className="mb-14">
            <RealisationsExplorer
              assets={salon.gallery}
              salonName={salon.name}
              reservable={reservable}
            />
          </section>
        )}

        {showAmbience && (
          <section className="mb-14">
            <Reveal className="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-dashed border-[var(--site-line)] bg-[var(--site-surface)] p-5">
              <div className="flex items-start gap-3">
                <span
                  className="flex size-10 shrink-0 items-center justify-center rounded-xl"
                  style={{
                    background: "var(--salon-accent)",
                    color: "var(--salon-ink-accent)",
                  }}
                >
                  <SalonIcon name="sparkle" className="size-5" />
                </span>
                <div>
                  <h2 className="font-medium text-[var(--site-ink)]">
                    {t("pages.imagesAmbiance")}
                  </h2>
                  <p className="mt-1 max-w-lg text-sm leading-relaxed text-[var(--site-muted)]">
                    {hasOwnWork
                      ? t("pages.ambianceAvecTravail", { salon: salon.name })
                      : t("pages.ambianceSansTravail", { salon: salon.name })}
                  </p>
                </div>
              </div>
              {reservable && (
                <PrimaryLink href="/reserver" icon="calendar">
                  {c("prendreRdv")}
                </PrimaryLink>
              )}
            </Reveal>

            <GalleryGrid
              assets={placeholders}
              salonName={salon.name}
              reservable={reservable}
            />
          </section>
        )}

        {/* ----- 3. Ce qu'en disent les clientes ------------------------- */}
        {avis.results.length > 0 && (
          <Reveal as="section" className="mb-14">
            <p className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-[var(--salon-ink)]">
              {g("avisSurtitre")}
            </p>
            <h2 className="mb-5 mt-1 font-display text-xl font-semibold tracking-tight text-[var(--site-ink)] sm:text-2xl">
              {g("avisTitre")}
            </h2>
            <ReviewList
              reviews={avis.results.slice(0, 3)}
              rating={{ average: avis.average, count: avis.count }}
              timeZone={salon.timezone}
            />
          </Reveal>
        )}

        {/* ----- 4. Le passage à l'acte ---------------------------------- */}
        {(reservable || whatsapp) && (
          <Reveal as="section" className="mb-6">
            <div className="salon-gradient relative overflow-hidden rounded-3xl px-5 py-7 text-white sm:px-10 sm:py-10">
              <span
                aria-hidden
                className="pointer-events-none absolute -right-16 -top-16 size-56 rounded-full bg-white/10 blur-2xl"
              />
              <h2 className="relative font-display text-2xl font-semibold tracking-tight sm:text-3xl">
                {g("ctaTitre")}
              </h2>
              <p className="relative mt-2 max-w-xl text-sm leading-relaxed text-white/85 sm:text-base">
                {g("ctaCorps", { salon: salon.name })}
              </p>
              <div className="relative mt-5 grid grid-cols-2 gap-2.5 sm:flex sm:flex-wrap">
                {reservable && (
                  <Lien
                    href="/reserver"
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-4 py-3 text-sm font-semibold text-[var(--salon-ink-white)] shadow-sm transition hover:brightness-95 sm:px-6"
                  >
                    <SalonIcon name="calendar" className="size-4" />
                    {g("ctaReserver")}
                  </Lien>
                )}
                {whatsapp && (
                  <a
                    href={whatsapp}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/40 px-4 py-3 text-sm font-semibold text-white transition hover:bg-white/10 sm:px-6"
                  >
                    <SalonIcon name="whatsapp" className="size-4" />
                    WhatsApp
                  </a>
                )}
              </div>
            </div>
          </Reveal>
        )}
      </main>
    </>
  );
}
