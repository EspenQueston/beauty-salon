import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import {
  CatalogueExplorer,
  type SectionCatalogue,
} from "@/features/salon/CatalogueExplorer";
import { normaliser, slugCategorie } from "@/features/salon/catalogue";
import { PageHero } from "@/features/salon/PageHero";
import { PAGE_SLIDES, salonSlides } from "@/features/salon/slides";
import { ServiceCard } from "@/features/salon/ServiceCard";
import { categoryIcon } from "@/features/salon/icons";
import { EmptyNote } from "@/features/salon/ui";
import { fetchSalon } from "@/lib/salon-serveur";
import { themeFromCategory } from "@/lib/illustrations";

type Props = {
  params: Promise<{ host: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

/* Le titre suit la langue de l'adresse : `export const metadata` est figé
   à la compilation et ne peut pas la connaître. */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("salon.titres");
  return { title: t("prestations") };
}

/**
 * Catalogue complet, groupé par catégorie, avec recherche et filtre.
 *
 * Le sommaire d'ancres qui ouvrait la page est devenu un filtre : une
 * recherche et une rangée de catégories, collées sous le menu (voir
 * `CatalogueExplorer`). Les cartes restent rendues ici, par le serveur, et
 * la page complète arrive dans le HTML : sans JavaScript, elle se lit comme
 * avant, et les anciennes ancres (`#ongles`) mènent toujours à leur section.
 */
export default async function PrestationsPage({ params, searchParams }: Props) {
  const t = await getTranslations("salon");
  const { host } = await params;
  const recherche = await searchParams;
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  const categories = salon.categories.filter(
    (category) => category.services.length > 0,
  );

  const total = categories.reduce(
    (sum, category) => sum + category.services.length,
    0,
  );

  /*
    Chaque carte, rendue une fois ici, et le texte dans lequel la recherche
    la retrouvera : son nom, sa description et sa catégorie, sans casse ni
    accents — dans la langue de la page, puisque le salon les a traduits.
  */
  const sections: SectionCatalogue[] = categories.map((category) => ({
    categorie: {
      id: category.id,
      slug: slugCategorie(category.name),
      nom: category.name,
      icone: categoryIcon(category.name),
      compte: category.services.length,
    },
    prestations: category.services.map((service) => ({
      id: service.id,
      texte: normaliser(
        `${service.name} ${service.description ?? ""} ${category.name}`,
      ),
      carte: (
        <ServiceCard
          service={service}
          icon={categoryIcon(category.name)}
          theme={themeFromCategory(category.name)}
        />
      ),
    })),
  }));

  return (
    <>
      <PageHero
        slides={salonSlides(salon, PAGE_SLIDES)}
        eyebrow={t("pages.prestationsCompte", { n: total })}
        title={t("pages.prestationsTitre")}
        icon="scissors"
        tone="catalogue"
      />

      <main className="mx-auto max-w-5xl px-4 pt-10">
        {categories.length === 0 ? (
          <EmptyNote icon="scissors" title={t("pages.prestationsVideTitre")}>
            {t("pages.prestationsVideCorps")}
          </EmptyNote>
        ) : (
          <CatalogueExplorer
            sections={sections}
            initiale={{
              categorie: premiere(recherche.categorie),
              q: premiere(recherche.q)?.slice(0, 80) ?? "",
            }}
          />
        )}
      </main>
    </>
  );
}

/** Un paramètre d'adresse peut être répété : on n'en garde que le premier. */
function premiere(valeur: string | string[] | undefined): string | null {
  const seule = Array.isArray(valeur) ? valeur[0] : valeur;
  return seule ? seule : null;
}
