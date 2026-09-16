import { notFound } from "next/navigation";

import { AboutStory } from "@/features/salon/AboutStory";
import { PageHero } from "@/features/salon/PageHero";
import { PAGE_SLIDES, salonSlides } from "@/features/salon/slides";
import { EmptyNote, PrimaryLink } from "@/features/salon/ui";
import { Reveal } from "@/features/ui/Reveal";
import { fetchSalon } from "@/lib/api";
import { readingMinutes, toParagraphs } from "@/lib/prose";

type Props = { params: Promise<{ host: string }> };

export const metadata = { title: "À propos" };

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
  const { host } = await params;
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  const title = salon.about_title?.trim() || `À propos de ${salon.name}`;

  const content = salon.about_content ?? "";
  const paragraphs = toParagraphs(content);
  const minutes = readingMinutes(content);

  return (
    <>
      <PageHero
        slides={salonSlides(salon, PAGE_SLIDES)}
        eyebrow="Notre histoire"
        title={title}
        icon="star"
        tone="apropos"
      />

      <main className="mx-auto max-w-5xl px-4 pt-10">
        {paragraphs.length === 0 ? (
          <EmptyNote icon="star" title="La présentation arrive">
            {salon.name} n&apos;a pas encore rédigé sa présentation. En
            attendant, son catalogue et ses horaires sont à jour.
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
            Prendre rendez-vous
          </PrimaryLink>
        </Reveal>
      </main>
    </>
  );
}
