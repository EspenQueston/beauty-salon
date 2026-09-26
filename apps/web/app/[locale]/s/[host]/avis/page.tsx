import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { PageHero } from "@/features/salon/PageHero";
import { PAGE_SLIDES, salonSlides } from "@/features/salon/slides";
import { ReviewForm } from "@/features/salon/ReviewForm";
import { Reveal } from "@/features/ui/Reveal";
import { fetchSalon } from "@/lib/salon-serveur";

type Props = {
  params: Promise<{ host: string }>;
  searchParams: Promise<{ token?: string }>;
};

export const metadata = {
  title: "Votre avis",
  // Une page atteinte par un lien personnel n'a rien à faire dans un index
  // de moteur de recherche.
  robots: { index: false, follow: false },
};

export default async function AvisPage({ params, searchParams }: Props) {
  const t = await getTranslations("salon");
  const [{ host }, query] = await Promise.all([params, searchParams]);
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  return (
    <>
      <PageHero
        slides={salonSlides(salon, PAGE_SLIDES)}
        eyebrow={t("pages.avisSurtitre")}
        title={t("pages.avisTitre")}
        icon="star"
        tone="equipe"
      />

      <main className="mx-auto max-w-xl px-4 pt-10">
        <Reveal>
          <ReviewForm
            host={host}
            token={query.token ?? ""}
            timeZone={salon.timezone}
          />
        </Reveal>
      </main>
    </>
  );
}
