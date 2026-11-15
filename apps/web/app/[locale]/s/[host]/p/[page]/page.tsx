import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { whatsappHref } from "@/features/salon/contact";
import { photo } from "@/features/salon/images";
import { PageHero } from "@/features/salon/PageHero";
import { PAGE_SLIDES, salonSlides } from "@/features/salon/slides";
import { GhostLink, PrimaryLink } from "@/features/salon/ui";
import { Reveal } from "@/features/ui/Reveal";
import { readingMinutes, toParagraphs } from "@/lib/prose";
import { fetchSalon } from "@/lib/salon-serveur";
import type { PagePerso, PublicSalon } from "@/lib/types";

type Props = { params: Promise<{ host: string; page: string }> };

/** La page, si le salon l'a publiée et a toujours l'offre Pro. */
function trouver(salon: PublicSalon | null, slug: string): PagePerso | null {
  return salon?.site_config?.pages?.find((page) => page.slug === slug) ?? null;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { host, page: slug } = await params;
  const page = trouver(await fetchSalon(host), slug);
  if (!page) return {};
  return { title: page.titre, description: page.accroche || undefined };
}

/**
 * Une page écrite par le salon (offre Pro) : « Tarifs », « Formations »…
 *
 * Trois au plus, et du texte brut rendu paragraphe par paragraphe, jamais
 * comme du HTML — exactement comme la page « À propos ». Sans Pro, la page
 * n'est plus publiée : son adresse répond 404 et elle quitte le menu, mais
 * le salon la retrouve intacte en revenant à Pro.
 */
export default async function PagePersoRoute({ params }: Props) {
  const t = await getTranslations("salon");
  const c = await getTranslations("commun");
  const { host, page: slug } = await params;
  const salon = await fetchSalon(host);
  const page = trouver(salon, slug);
  if (!salon || !page) notFound();

  const paragraphes = toParagraphs(page.contenu);
  const minutes = readingMinutes(page.contenu);
  const whatsapp = whatsappHref(salon.whatsapp_number);
  const image = page.image;

  return (
    <>
      <PageHero
        slides={salonSlides(salon, PAGE_SLIDES)}
        eyebrow={t("pages.persoSurtitre", { salon: salon.name })}
        title={page.titre}
        icon="sparkle"
        tone="apropos"
      />

      <main className="mx-auto max-w-5xl px-4 pt-8 sm:pt-12">
        <div
          className={`grid gap-6 sm:gap-10 ${image ? "md:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]" : ""}`}
        >
          {/* L'image passe devant le texte sur téléphone : c'est elle qu'on
              voit en arrivant, le texte suit sous le pouce. */}
          {image && (
            <Reveal className="md:order-2">
              <figure className="overflow-hidden rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] shadow-sm md:sticky md:top-24">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  {...photo(image, "(min-width: 768px) 22rem, 100vw")}
                  alt={image.alt_text || page.titre}
                  width={image.width ?? undefined}
                  height={image.height ?? undefined}
                  loading="lazy"
                  className="aspect-[4/3] w-full object-cover md:aspect-[4/5]"
                />
              </figure>
            </Reveal>
          )}

          <Reveal as="article" className="min-w-0">
            {page.accroche && (
              <p className="text-pretty text-lg font-medium leading-relaxed text-[var(--site-ink)] sm:text-xl">
                {page.accroche}
              </p>
            )}
            {paragraphes.length > 0 && (
              <>
                <p className="mt-3 text-xs uppercase tracking-[0.14em] text-[var(--site-subtle)]">
                  {t("pages.lecture", { n: minutes })}
                </p>
                <div className="mt-4 space-y-4 text-[15px] leading-relaxed text-[var(--site-muted)] sm:text-base">
                  {paragraphes.map((paragraphe, index) => (
                    <p key={index} className="whitespace-pre-line text-pretty">
                      {paragraphe}
                    </p>
                  ))}
                </div>
              </>
            )}
          </Reveal>
        </div>

        <Reveal className="mt-12 rounded-3xl border border-[var(--site-line)] bg-[var(--site-surface)] p-5 text-center shadow-sm sm:mt-16 sm:p-8">
          <h2 className="text-xl font-semibold tracking-tight text-[var(--site-ink)] sm:text-2xl">
            {t("pages.persoQuestion")}
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-[var(--site-muted)] sm:text-base">
            {t("pages.persoQuestionCorps")}
          </p>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-2.5">
            <PrimaryLink href="/reserver" icon="calendar" className="px-6 py-3">
              {salon.site_config?.bouton_reserver || c("prendreRdv")}
            </PrimaryLink>
            {whatsapp && (
              <GhostLink href={whatsapp} icon="whatsapp" external>
                {t("ecrireWhatsApp")}
              </GhostLink>
            )}
          </div>
        </Reveal>
      </main>
    </>
  );
}
