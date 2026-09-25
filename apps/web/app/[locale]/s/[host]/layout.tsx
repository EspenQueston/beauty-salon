import { getTranslations } from "next-intl/server";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { locale as segment } from "next/root-params";
import type { Metadata } from "next";

import { adresses, ENTETE_CHEMIN } from "@/i18n/adresses";
import { estLangue, LANGUE_PAR_DEFAUT } from "@/i18n/langues";

import { BookingBar } from "@/features/salon/BookingBar";
import {
  BandeauFermeture,
  reservationsFermees,
} from "@/features/salon/ReservationsFermees";
import { SalonFooter } from "@/features/salon/SalonFooter";
import { DeviseProvider } from "@/features/salon/Devise";
import { SalonNav } from "@/features/salon/SalonNav";
import { InlineScript } from "@/app/InlineScript";
import { Installer } from "@/features/ui/Installer";
import { ScrollTop } from "@/features/ui/ScrollTop";
import { fetchSalon } from "@/lib/salon-serveur";
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
  const tSalon = await getTranslations("salon");
  const { host } = await params;
  const salon = await fetchSalon(host);
  if (!salon) return { title: tSalon("pages.introuvable") };

  const title = salon.city ? `${salon.name} — ${salon.city}` : salon.name;
  const description =
    salon.description || tSalon("pages.reservezChez", { salon: salon.name });

  /*
    L'adresse de référence, et celle de la même page dans l'autre langue.

    Le chemin public vient du proxy : la page ne reçoit que son chemin
    interne, `/fr/s/blondrose.com/prestations`, dont aucune adresse publique
    ne se déduit.

    La canonique désignait jusqu'ici l'accueil du salon pour **toutes** les
    pages — chaque page de prestations se déclarait donc doublon de
    l'accueil. Il fallait de toute façon la corriger pour poser les
    `hreflang` : une page canonique vers une autre annule les balises de
    langue posées à côté d'elle.
  */
  const enTetes = await headers();
  const chemin = enTetes.get(ENTETE_CHEMIN) ?? "/";
  const brut = await segment();
  const langue = estLangue(brut) ? brut : LANGUE_PAR_DEFAUT;

  return {
    title: { default: title, template: `%s · ${salon.name}` },
    description,
    alternates: adresses(host, chemin, langue),
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

  const ferme = reservationsFermees(salon);
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
  /*
    Le slug passe par `JSON.stringify`, jamais brut.

    Il est interpolé dans une chaîne JavaScript à l'intérieur d'un `<script>`
    : un slug contenant un guillemet ou `</script>` s'échapperait du littéral
    et deviendrait du code exécuté sur toutes les pages du mini-site.

    Aucun slug ne peut en contenir — le modèle impose
    `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`. Mais cette garantie vit dans un
    validateur Django, à deux couches d'ici, et rien sur cette ligne ne la
    rappelle : il suffirait qu'on assouplisse un jour la règle des adresses
    pour ouvrir une faille sans que personne ne relie les deux. L'échappement
    est donc fait ici, où l'injection a lieu.

    `JSON.stringify` seul n'y suffit pas : il laisse passer `</script>`, que
    l'analyseur HTML lit avant le JavaScript. Les chevrons ouvrants sont donc
    écrits en séquence d'échappement Unicode, que le JavaScript relit à
    l'identique.
  */
  const slug = JSON.stringify(salon.slug).replace(/</g, "\\u003c");
  const boot =
    `(function(){try{var k="beauty-salon.mode."+${slug},v=localStorage.getItem(k);` +
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

      {/*
        Le choix de lecture des prix couvre tout le mini-site.

        Ici plutôt que page par page : une visiteuse qui a demandé à lire en
        francs ne veut pas le redemander en changeant d'onglet, et le bouton
        vit dans la barre du haut, qui est elle aussi commune.

        Le pied de page reste dedans : il ne montre pas de prix aujourd'hui,
        mais rien ne garantit qu'il n'en montrera jamais.
      */}
      <DeviseProvider salonSlug={salon.slug} devise={salon.currency}>
        <SalonNav
          name={salon.name}
          slug={salon.slug}
          logo={salon.logo}
          show={show}
        />

        {/* Réservations fermées : dit dès le haut de page, et la barre de
            réservation du bas disparaît — elle mènerait à un refus. */}
        {ferme && <BandeauFermeture />}

        {/* La marge basse laisse la place à la barre de réservation fixe. */}
        <div className="flex-1 pb-24">{children}</div>

        <SalonFooter salon={salon} />
      </DeviseProvider>

      {/* Marqués comme habillage : ils disparaissent sur l'écran
          d'identification, où toute sortie autre que « retour au site »
          fait abandonner le formulaire. */}
      {!ferme && (
        <div data-site-chrome>
          <BookingBar salon={salon} />
        </div>
      )}

      {/* Décalé de la hauteur de la barre de réservation, pour ne pas la
          recouvrir sur mobile. */}
      <div data-site-chrome>
        <ScrollTop offset="6.5rem" />
      </div>

      {/* Proposée à la deuxième visite seulement, et une seule fois. */}
      <div data-site-chrome>
        <Installer nom={salon.name} />
      </div>
    </div>
  );
}
