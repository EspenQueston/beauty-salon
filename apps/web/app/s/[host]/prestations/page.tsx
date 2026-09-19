import { notFound } from "next/navigation";

import { PageHero } from "@/features/salon/PageHero";
import { PAGE_SLIDES, salonSlides } from "@/features/salon/slides";
import { ServiceCard } from "@/features/salon/ServiceCard";
import { SalonIcon, categoryIcon } from "@/features/salon/icons";
import { EmptyNote, Pill } from "@/features/salon/ui";
import { Reveal } from "@/features/ui/Reveal";
import { fetchSalon } from "@/lib/api";
import { themeFromCategory } from "@/lib/illustrations";

type Props = { params: Promise<{ host: string }> };

export const metadata = { title: "Prestations" };

/**
 * Catalogue complet, groupé par catégorie.
 *
 * Un sommaire en tête permet de sauter directement à « Ongles » sans
 * traverser trois sections de coiffure. Il est en ancres HTML et non en
 * JavaScript : il fonctionne avant l'hydratation, et se partage tel quel.
 */
export default async function PrestationsPage({ params }: Props) {
  const { host } = await params;
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  const categories = salon.categories.filter(
    (category) => category.services.length > 0,
  );

  const total = categories.reduce(
    (sum, category) => sum + category.services.length,
    0,
  );

  return (
    <>
      <PageHero
        slides={salonSlides(salon, PAGE_SLIDES)}
        eyebrow={`${total} prestation${total > 1 ? "s" : ""}`}
        title="Nos prestations"
        icon="scissors"
        tone="catalogue"
      />

      <main className="mx-auto max-w-5xl px-4 pt-10">
        {categories.length === 0 ? (
          <EmptyNote icon="scissors" title="Le catalogue arrive">
            Ce salon prépare ses prestations. Écrivez-lui pour connaître ses
            tarifs.
          </EmptyNote>
        ) : (
          <>
            {categories.length > 1 && (
              <nav aria-label="Catégories" className="mb-10">
                <ul className="flex flex-wrap gap-2">
                  {categories.map((category) => (
                    <li key={category.id}>
                      <a
                        href={`#${slug(category.name)}`}
                        className="inline-flex items-center gap-1.5 rounded-full border border-[var(--site-line)] bg-[var(--site-surface)] px-3.5 py-2 text-sm font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)] hover:text-[var(--salon-ink)]"
                      >
                        <SalonIcon
                          name={categoryIcon(category.name)}
                          className="size-4 text-[var(--salon-ink)]"
                        />
                        {category.name}
                      </a>
                    </li>
                  ))}
                </ul>
              </nav>
            )}

            <div className="space-y-16">
              {categories.map((category) => (
                <Reveal
                  key={category.id}
                  as="section"
                  className="scroll-mt-24"
                  id={slug(category.name)}
                >
                  <div className="mb-5 flex flex-wrap items-center gap-3">
                    <span
                      className="flex size-11 items-center justify-center rounded-2xl"
                      style={{
                        background: "var(--salon-accent)",
                        color: "var(--salon-ink-accent)",
                      }}
                    >
                      <SalonIcon
                        name={categoryIcon(category.name)}
                        className="size-5"
                      />
                    </span>
                    <h2 className="text-xl font-semibold tracking-tight text-[var(--site-ink)]">
                      {category.name}
                    </h2>
                    <Pill>
                      {category.services.length} prestation
                      {category.services.length > 1 ? "s" : ""}
                    </Pill>
                  </div>

                  <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 lg:grid-cols-4">
                    {category.services.map((service) => (
                      <ServiceCard
                        key={service.id}
                        service={service}
                        icon={categoryIcon(category.name)}
                        theme={themeFromCategory(category.name)}
                      />
                    ))}
                  </div>
                </Reveal>
              ))}
            </div>
          </>
        )}
      </main>
    </>
  );
}

/** Ancre lisible et stable pour une catégorie. */
function slug(name: string): string {
  return name
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}
