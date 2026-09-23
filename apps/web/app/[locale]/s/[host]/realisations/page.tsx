import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { GalleryGrid } from "@/features/salon/GalleryGrid";
import { PageHero } from "@/features/salon/PageHero";
import { PAGE_SLIDES, salonSlides } from "@/features/salon/slides";
import { SalonIcon } from "@/features/salon/icons";
import { PrimaryLink } from "@/features/salon/ui";
import { Reveal } from "@/features/ui/Reveal";
import { fetchSalon } from "@/lib/salon-serveur";
import { illustrationUrl, pickIllustrations } from "@/lib/illustrations";
import { isVideo, type MediaAsset } from "@/lib/types";

type Props = { params: Promise<{ host: string }> };

/* Le titre suit la langue de l'adresse : `export const metadata` est figé
   à la compilation et ne peut pas la connaître. */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("salon.titres");
  return { title: t("realisations") };
}

/**
 * Ce que le salon a déjà fait : photos et vidéos courtes.
 *
 * C'est la page qui remplace un avis client tant qu'il n'y en a pas. Une
 * cliente juge une tresse sur une photo, pas sur une description.
 *
 * Quand le salon n'a encore rien publié, la grille montre des images
 * d'ambiance — et **le dit**. Faire passer des photos prises ailleurs pour
 * le travail d'un vrai commerce serait un mensonge sur son savoir-faire,
 * exactement le genre de chose qu'une cliente déçue reproche ensuite au
 * salon et non à la plateforme.
 */
export default async function RealisationsPage({ params }: Props) {
  const t = await getTranslations("salon");
  const c = await getTranslations("commun");
  const { host } = await params;
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  const hasOwnWork = salon.gallery.length > 0;
  const photos = salon.gallery.filter((asset) => !isVideo(asset)).length;
  const videos = salon.gallery.length - photos;

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

      <main className="mx-auto max-w-5xl px-4 pt-10">
        {hasOwnWork && (
          <Reveal as="section" className="mb-14">
            <GalleryGrid assets={salon.gallery} salonName={salon.name} />
          </Reveal>
        )}

        {showAmbience && (
          <section>
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
              <PrimaryLink href="/reserver" icon="calendar">
                {c("prendreRdv")}
              </PrimaryLink>
            </Reveal>

            <GalleryGrid assets={placeholders} salonName={salon.name} />
          </section>
        )}
      </main>
    </>
  );
}
