import { notFound } from "next/navigation";

import { PageHero } from "@/features/salon/PageHero";
import { PAGE_SLIDES, salonSlides } from "@/features/salon/slides";
import { StaffCard } from "@/features/salon/StaffCard";
import { EmptyNote } from "@/features/salon/ui";
import { Reveal } from "@/features/ui/Reveal";
import { fetchSalon } from "@/lib/api";

type Props = { params: Promise<{ host: string }> };

export const metadata = { title: "L'équipe" };

export default async function EquipePage({ params }: Props) {
  const { host } = await params;
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  return (
    <>
      <PageHero
        slides={salonSlides(salon, PAGE_SLIDES)}
        eyebrow="Qui vous reçoit"
        title="L'équipe"
        icon="star"
        tone="equipe"
      />

      <main className="mx-auto max-w-5xl px-4 pt-10">
        {salon.staff_members.length === 0 ? (
          <EmptyNote icon="star" title="L'équipe se présente bientôt">
            Ce salon n&apos;a pas encore publié ses prestataires.
          </EmptyNote>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-3 lg:grid-cols-4">
            {salon.staff_members.map((member, index) => (
              <Reveal key={member.id} delay={index * 70} className="h-full">
                <StaffCard member={member} detailed />
              </Reveal>
            ))}
          </div>
        )}
      </main>
    </>
  );
}
