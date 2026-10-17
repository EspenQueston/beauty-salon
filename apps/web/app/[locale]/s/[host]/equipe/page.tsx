import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { PageHero } from "@/features/salon/PageHero";
import { PAGE_SLIDES, salonSlides } from "@/features/salon/slides";
import { TeamShowcase } from "@/features/salon/TeamShowcase";
import { EmptyNote } from "@/features/salon/ui";
import { Reveal } from "@/features/ui/Reveal";
import { fetchSalon } from "@/lib/salon-serveur";

type Props = { params: Promise<{ host: string }> };

/* Le titre suit la langue de l'adresse : `export const metadata` est figé
   à la compilation et ne peut pas la connaître. */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("salon.titres");
  return { title: t("equipe") };
}

export default async function EquipePage({ params }: Props) {
  const t = await getTranslations("salon");
  const { host } = await params;
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  return (
    <>
      <PageHero
        slides={salonSlides(salon, PAGE_SLIDES)}
        eyebrow={t("pages.equipeSurtitre")}
        title={t("pages.equipeTitre")}
        icon="star"
        tone="equipe"
      />

      <main className="mx-auto max-w-5xl px-4 pt-10">
        {salon.staff_members.length === 0 ? (
          <EmptyNote icon="star" title={t("pages.equipeVideTitre")}>
            {t("pages.equipeVideCorps")}
          </EmptyNote>
        ) : (
          <Reveal>
            <TeamShowcase members={salon.staff_members} detailed />
          </Reveal>
        )}
      </main>
    </>
  );
}
