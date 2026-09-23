import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { AboutStory } from "@/features/salon/AboutStory";
import { PageHero } from "@/features/salon/PageHero";
import { PAGE_SLIDES, salonSlides } from "@/features/salon/slides";
import { EmptyNote, PrimaryLink } from "@/features/salon/ui";
import { Reveal } from "@/features/ui/Reveal";
import { fetchSalon } from "@/lib/salon-serveur";
import { readingMinutes, toParagraphs } from "@/lib/prose";

type Props = { params: Promise<{ host: string }> };

/* Le titre suit la langue de l'adresse : `export const metadata` est figé
   à la compilation et ne peut pas la connaître. */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("salon.titres");
  return { title: t("aPropos") };
}

/**
 * Page « À propos », rédigée par le salon depuis son espace.
 *
 * L'accroche du haut de page tient en trois lignes ; elle ne dit pas depuis
 * quand le salon existe, ni pourquoi il coiffe comme il coiffe. C'est
 * pourtant ce récit qui décide une cliente qui hésite entre deux adresses.
 *
 * Le texte saisi est rendu paragraphe par paragraphe, jamais comme du HTML :
 * un salon écrit dans un champ de texte, pas dans un éditeur, et interpréter
 * sa saisie comme du balisage ouvrirait une injection sur sa propre page.
 *
 * La mise en page — chapitres alternés, images, tableau de chiffres — vit
 * dans `AboutStory` : elle a ses propres règles, et elles méritaient d'être
 * expliquées ailleurs que dans une page qui ne fait que charger des données.
 */
export default async function AProposPage({ params }: Props) {
  const t = await getTranslations("salon");
  const c = await getTranslations("commun");
  const { host } = await params;
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  const title =
    salon.about_title?.trim() || t("pages.aProposDe", { salon: salon.name });

  const content = salon.about_content ?? "";
  const paragraphs = toParagraphs(content);
  const minutes = readingMinutes(content);

  return (
    <>
      <PageHero
        slides={salonSlides(salon, PAGE_SLIDES)}
        eyebrow={t("pages.aProposSurtitre")}
        title={title}
        icon="star"
        tone="apropos"
      />

      <main className="mx-auto max-w-5xl px-4 pt-10">
        {paragraphs.length === 0 ? (
          <EmptyNote icon="star" title={t("pages.aProposVideTitre")}>
            {t("pages.aProposVideCorps", { salon: salon.name })}
          </EmptyNote>
        ) : (
          <AboutStory
            paragraphs={paragraphs}
            minutes={minutes}
            salon={salon}
            title={title}
          />
        )}

        <Reveal className="mt-14 text-center">
          <PrimaryLink href="/reserver" icon="calendar" className="px-7 py-3.5">
            {c("prendreRdv")}
          </PrimaryLink>
        </Reveal>
      </main>
    </>
  );
}
