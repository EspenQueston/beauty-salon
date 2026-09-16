import { notFound } from "next/navigation";
import type { Metadata } from "next";

import { BookingBar } from "@/features/salon/BookingBar";
import { SalonFooter } from "@/features/salon/SalonFooter";
import { SalonNav } from "@/features/salon/SalonNav";
import { InlineScript } from "@/app/InlineScript";
import { ScrollTop } from "@/features/ui/ScrollTop";
import { fetchSalon } from "@/lib/api";
import { themeToCssVars } from "@/lib/format";

type Props = {
  children: React.ReactNode;
  params: Promise<{ host: string }>;
};

/**
 * Métadonnées par salon : c'est ce qui s'affiche quand une cliente partage
 * le lien sur WhatsApp ou Instagram. Un aperçu correct compte autant que la
 * page elle-même dans ces marchés, où le lien circule de main en main.
 */
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { host } = await params;
  const salon = await fetchSalon(host);
  if (!salon) return { title: "Salon introuvable" };

  const title = salon.city ? `${salon.name} — ${salon.city}` : salon.name;
  const description =
    salon.description || `Réservez votre rendez-vous chez ${salon.name}.`;

  return {
    title: { default: title, template: `%s · ${salon.name}` },
    description,
    // Le mini-site reste atteignable par son chemin interne ; la canonique
    // désigne le sous-domaine du salon comme seule adresse de référence.
    alternates: { canonical: `https://${host}/` },
    openGraph: {
      title,
      description,
      type: "website",
      images: salon.banner ? [{ url: salon.banner.url }] : undefined,
    },
    twitter: { card: "summary_large_image", title, description },
  };
}

/**
 * Coquille commune aux pages d'un salon.
 *
 * La navigation, le pied de page et la barre de réservation vivent ici :
 * elles ne dépendent pas de la page affichée, et les remonter au layout
 * évite qu'une page nouvelle les oublie.
 */
export default async function SiteLayout({ children, params }: Props) {
  const { host } = await params;
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  const show = {
    prestations: salon.categories.length > 0,
    realisations: salon.gallery.length > 0,
    equipe: salon.staff_members.length > 0,
    // La page « À propos » n'apparaît que si le salon l'a écrite : un lien
    // vers une page vide dessert plus qu'il n'aide.
    apropos: Boolean(salon.about_content?.trim()),
  };

  /*
   * Le mode clair/sombre est posé avant le premier pixel.
   *
   * Le laisser à React ferait afficher la page en clair, puis basculer au
   * sombre à l'hydratation — un éclair blanc en pleine nuit, exactement ce
   * que la personne cherchait à éviter en choisissant le sombre.
   *
   * `suppressHydrationWarning` : le script modifie l'attribut avant que
   * React ne compare son rendu au DOM.
   */
  const boot =
    `(function(){try{var k="beauty-salon.mode.${salon.slug}",v=localStorage.getItem(k);` +
    `if(v!=="light"&&v!=="dark"){v=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}` +
    `document.currentScript.parentElement.dataset.mode=v}catch(e){}})()`;

  return (
    <div
      style={themeToCssVars(salon.theme_config) as React.CSSProperties}
      className="salon-site flex min-h-svh flex-col"
      data-mode="light"
      suppressHydrationWarning
    >
      <InlineScript html={boot} />

      <SalonNav
        name={salon.name}
        slug={salon.slug}
        logo={salon.logo}
        show={show}
      />

      {/* La marge basse laisse la place à la barre de réservation fixe. */}
      <div className="flex-1 pb-24">{children}</div>

      <SalonFooter salon={salon} />

      {/* Marqués comme habillage : ils disparaissent sur l'écran
          d'identification, où toute sortie autre que « retour au site »
          fait abandonner le formulaire. */}
      <div data-site-chrome>
        <BookingBar salon={salon} />
      </div>

      {/* Décalé de la hauteur de la barre de réservation, pour ne pas la
          recouvrir sur mobile. */}
      <div data-site-chrome>
        <ScrollTop offset="6.5rem" />
      </div>
    </div>
  );
}
