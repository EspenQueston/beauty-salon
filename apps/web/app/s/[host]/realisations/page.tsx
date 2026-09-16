import { notFound } from "next/navigation";

import { GalleryGrid } from "@/features/salon/GalleryGrid";
import { PageHero } from "@/features/salon/PageHero";
import { PAGE_SLIDES, salonSlides } from "@/features/salon/slides";
import { SalonIcon } from "@/features/salon/icons";
import { PrimaryLink } from "@/features/salon/ui";
import { Reveal } from "@/features/ui/Reveal";
import { fetchSalon } from "@/lib/api";
import {
  illustrationUrl,
  pickIllustrations,
} from "@/lib/illustrations";
import { isVideo, type MediaAsset } from "@/lib/types";

type Props = { params: Promise<{ host: string }> };

export const metadata = { title: "Réalisations" };

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
        eyebrow="Notre travail"
        title="Réalisations"
        icon="sparkle"
        tone="galerie"
      >
        {hasOwnWork && (
          <div className="flex flex-wrap gap-2">
            {photos > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1.5 text-sm backdrop-blur">
                {photos} photo{photos > 1 ? "s" : ""}
              </span>
            )}
            {videos > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1.5 text-sm backdrop-blur">
                <SalonIcon name="play" className="size-3.5" filled />
                {videos} vidéo{videos > 1 ? "s" : ""}
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
                    color: "var(--salon-ink)",
                  }}
                >
                  <SalonIcon name="sparkle" className="size-5" />
                </span>
                <div>
                  <h2 className="font-medium text-[var(--site-ink)]">
                    Images d&apos;ambiance
                  </h2>
                  <p className="mt-1 max-w-lg text-sm leading-relaxed text-[var(--site-muted)]">
                    {hasOwnWork
                      ? `Ces photos illustrent le métier — elles ne sont pas le travail de ${salon.name}, qui publie ses réalisations au fur et à mesure.`
                      : `${salon.name} n'a pas encore publié ses propres photos. Celles-ci illustrent le métier — écrivez au salon pour voir son travail.`}
                  </p>
                </div>
              </div>
              <PrimaryLink href="/reserver" icon="calendar">
                Prendre rendez-vous
              </PrimaryLink>
            </Reveal>

            <GalleryGrid assets={placeholders} salonName={salon.name} />

          </section>
        )}
      </main>
    </>
  );
}
