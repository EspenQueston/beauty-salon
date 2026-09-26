/**
 * Haut de page du mini-site.
 *
 * Il répond à quatre questions en un écran : qui, où, quoi, et comment
 * réserver. Tout le reste de la page sert à confirmer une décision déjà
 * prise ici.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi la composition n'est plus centrée
 * ---------------------------------------------------------------------------
 *
 * La version précédente empilait tout au centre : logo, pastille, nom,
 * phrase, bouton, trois chiffres. C'est la mise en page par défaut de tous
 * les gabarits de site, et elle a deux défauts qu'on ne voit qu'une fois
 * côte à côte avec autre chose.
 *
 * Le premier : une colonne centrée n'a pas de hiérarchie. Chaque ligne
 * commence à un endroit différent, donc l'œil n'a aucun bord auquel se
 * raccrocher et lit tout avec la même importance — le nom du salon comme le
 * décompte des réalisations.
 *
 * Le second : elle gaspille la largeur. Sur un écran d'ordinateur, la moitié
 * droite ne portait rien, alors que c'est exactement la place d'un bloc de
 * faits — la note, le nombre de prestations, les horaires du jour.
 *
 * D'où deux colonnes alignées à gauche : le discours d'un côté, les faits
 * vérifiables de l'autre. Sur téléphone, les faits passent dessous en grille
 * de deux, et le discours se resserre.
 *
 * ---------------------------------------------------------------------------
 * Le fond
 * ---------------------------------------------------------------------------
 *
 * Toujours le défilé des prestations du salon — pas une photo générique. Une
 * visiteuse qui arrive d'un lien WhatsApp doit voir en trois secondes si on
 * fait des tresses ou des ongles.
 */

import { HeroCarousel } from "./HeroCarousel";
import { HOME_SLIDES, salonSlides } from "./slides";
import { Mots } from "@/features/ui/Accent";
import { shortTime } from "@/lib/format";
import type { PublicSalon } from "@/lib/types";
import { whatsappHref } from "./contact";
import { CountUp } from "./CountUp";
import { SalonIcon } from "./icons";
import { SalonLogo } from "./SalonLogo";
import { horairesDuJour } from "./ouverture";
import { useTranslations } from "next-intl";

import { StatutOuverture } from "./Statut";
import { GhostLink, PrimaryLink } from "./ui";

export function Hero({
  salon,
  instantServeur,
}: {
  salon: PublicSalon;
  /** L'instant du rendu, partagé avec la pastille d'ouverture. */
  instantServeur: number;
}) {
  const t = useTranslations("salon");
  const whatsapp = whatsappHref(salon.whatsapp_number);
  const serviceCount = salon.categories.reduce(
    (total, category) => total + category.services.length,
    0,
  );

  // Les diapositives viennent de `slides.ts`, partagé avec les pages
  // intérieures : recopier la logique ici garantirait qu'un jour l'accueil et
  // le reste du site ne montrent plus les mêmes prestations.
  const slides = salonSlides(salon, HOME_SLIDES);

  return (
    // Le bloc se termine par un grand rayon plutôt que par une courbe
    // dessinée : la page qu'il surplombe reparaît dans les deux coins, ce qui
    // pose le haut de page comme une carte et non comme une bande.
    <header className="relative isolate overflow-hidden rounded-b-[2rem] sm:rounded-b-[3rem]">
      {/* Fond défilant : les prestations du salon, pas une photo générique. */}
      <HeroCarousel slides={slides} />

      {/*
        La marge haute laisse passer le menu, posé sur la photo.

        La marge basse réservait la place de la légende du défilé — le nom de
        la prestation affichée, sous une rangée de puces. Les deux ont été
        retirés : elle se resserre d'autant, et le haut de page tient
        maintenant dans un écran de téléphone.
      */}
      <div className="relative mx-auto grid max-w-6xl gap-8 px-4 pb-16 pt-24 text-white sm:gap-10 sm:pb-20 sm:pt-32 lg:grid-cols-[minmax(0,1fr)_19rem] lg:items-end lg:gap-14 lg:pb-24 lg:pt-40">
        <div className="min-w-0">
          {/*
            Le logo sur la ligne du nom, et non au-dessus.

            En pastille de 96 px posée au milieu d'un visage, il se lisait
            comme un autocollant collé sur la photo. À hauteur de la première
            ligne de texte, il redevient ce qu'il est : une marque qui
            introduit un nom.
          */}
          <div className="rise flex items-center gap-3">
            <SalonLogo
              logo={salon.logo}
              name={salon.name}
              className="size-12 text-lg shadow-lg ring-2 ring-white/50 sm:size-14 sm:text-xl"
              rounded="rounded-2xl"
            />
            <StatutOuverture salon={salon} instantServeur={instantServeur} />
          </div>

          {/*
            Le nom monte de derrière la ligne, mot par mot.

            C'est le seul mot de la page qu'une visiteuse doit retenir, et le
            mouvement lui donne son poids : on croit voir le nom arriver, pas
            apparaître.

            L'interligne passe de 1,08 à 1,15 : le masque a besoin d'un cadre
            un peu plus haut que la lettre pour que les jambages ne frôlent
            pas la coupe.
          */}
          <h1 className="mt-5 text-balance text-[2.1rem] font-semibold leading-[1.15] tracking-tight drop-shadow-sm sm:text-6xl">
            <Mots text={salon.name} />
          </h1>

          {/* L'accroche choisie par un salon Pro passe devant la
              description : c'est la phrase qu'il veut voir en premier. */}
          {(salon.site_config?.accroche || salon.description) && (
            <p
              className="rise mt-4 max-w-xl text-pretty text-[0.95rem] leading-relaxed text-white/90 sm:mt-5 sm:text-lg"
              style={{ animationDelay: "160ms" }}
            >
              {salon.site_config?.accroche || salon.description}
            </p>
          )}

          <div
            className="rise mt-7 flex flex-wrap items-center gap-2.5 sm:gap-3"
            style={{ animationDelay: "240ms" }}
          >
            <PrimaryLink
              href="/reserver"
              icon="calendar"
              className="px-6 py-3.5 sm:px-7"
            >
              {salon.site_config?.bouton_reserver || t("reserverRdv")}
            </PrimaryLink>

            {whatsapp && (
              <GhostLink
                href={whatsapp}
                icon="whatsapp"
                external
                className="border-white/35 bg-white/10 text-white backdrop-blur hover:border-white/70"
              >
                WhatsApp
              </GhostLink>
            )}
          </div>
        </div>

        <Faits
          salon={salon}
          serviceCount={serviceCount}
          instantServeur={instantServeur}
        />
      </div>

      {/*
        L'invitation à descendre, et c'est un vrai lien.

        Un haut de page qui occupe tout l'écran ne dit pas s'il y a une
        suite : une cliente peut refermer en croyant avoir tout vu — les
        tarifs, les avis et les horaires sont pourtant plus bas.

        Ce n'était qu'un décor : un `<span aria-hidden>` sur lequel on
        pouvait appuyer sans que rien ne se produise. Un mot et une flèche
        qui pointent vers le bas *invitent* à cliquer ; ne rien faire au clic
        se lit comme une page cassée, pas comme une décoration.

        C'est donc une ancre vers le catalogue, qui fonctionne sans
        JavaScript, se tabule, et glisse doucement grâce au
        `scroll-behavior` de la feuille de style. `ANCRE_CONTENU` est le
        contrat entre ce composant et la page qui pose la cible.
      */}
      <a
        href={`#${ANCRE_CONTENU}`}
        className="absolute inset-x-0 bottom-6 z-10 hidden justify-center sm:flex"
      >
        <span className="group flex flex-col items-center gap-1 rounded-lg px-3 py-1 text-[0.62rem] font-semibold uppercase tracking-[0.22em] text-[var(--site-muted)] transition hover:text-white">
          {t("hero.voirPrestations")}
          <SalonIcon
            name="arrow"
            className="size-3.5 rotate-90 animate-bounce transition-transform group-hover:translate-y-0.5"
          />
        </span>
      </a>
    </header>
  );
}

/**
 * L'ancre posée par la page d'accueil, juste sous le haut de page.
 *
 * Exportée plutôt qu'écrite en dur des deux côtés : un identifiant recopié
 * à la main finit toujours par diverger, et le jour où il diverge le lien ne
 * fait plus rien — sans que rien ne le signale.
 */
export const ANCRE_CONTENU = "contenu";

/**
 * Le bloc de faits.
 *
 * Quatre tuiles, et pas une de plus : la note, le catalogue, l'équipe et les
 * horaires du jour. Ce sont les quatre choses qu'une cliente vérifie avant
 * d'appuyer sur « Réserver », et elles sont toutes tirées des données du
 * salon — rien n'est affiché qui ne soit vrai.
 *
 * Deux colonnes sur téléphone, une seule colonne à partir de `lg` où le bloc
 * devient la colonne de droite. C'est la même grille dans les deux cas : un
 * `grid-cols-2 lg:grid-cols-1`, pas deux mises en page à maintenir.
 */
function Faits({
  salon,
  serviceCount,
  instantServeur,
}: {
  salon: PublicSalon;
  serviceCount: number;
  instantServeur: number;
}) {
  const t = useTranslations("salon");
  const plages = horairesDuJour(salon, new Date(instantServeur));
  const note = salon.rating;

  return (
    /*
      La dernière tuile prend la ligne entière quand elle s'y retrouve seule.

      Un salon sans avis n'en a que trois : deux en haut, une en bas à gauche,
      et un trou à droite qui se lit comme une tuile qui n'a pas fini de
      charger. La règle vaut pour trois comme pour cinq, et ne s'applique
      qu'en dessous de `lg`, où le bloc redevient une colonne.
    */
    <div
      className="rise grid grid-cols-2 gap-2.5 [&>*:last-child:nth-child(odd)]:col-span-2 lg:grid-cols-1 lg:[&>*:last-child:nth-child(odd)]:col-span-1"
      style={{ animationDelay: "320ms" }}
    >
      {note.average != null && note.count > 0 && (
        <Tuile libelle={t("hero.avis", { n: note.count })}>
          {/*
            Une étoile, pas cinq.

            `Stars` peint en `--salon-ink`, une encre de marque foncée : sur
            le voile sombre du défilé, les cinq étoiles disparaissaient. Le
            chiffre sur cinq dit la même chose et se lit de loin.
          */}
          <span className="flex items-baseline gap-1.5">
            <SalonIcon
              name="star"
              className="size-4 shrink-0 self-center opacity-80"
            />
            <span className="tabular text-2xl font-semibold leading-none">
              {note.average.toFixed(1)}
            </span>
            <span className="text-sm text-white/65">/ 5</span>
          </span>
        </Tuile>
      )}

      {serviceCount > 0 && (
        <Tuile libelle={t("hero.prestations", { n: serviceCount })}>
          <span className="flex items-center gap-2 text-2xl font-semibold leading-none">
            <SalonIcon name="scissors" className="size-4 opacity-70" />
            <CountUp value={serviceCount} />
          </span>
        </Tuile>
      )}

      {salon.staff_members.length > 0 && (
        <Tuile
          libelle={t("hero.prestataires", { n: salon.staff_members.length })}
        >
          <span className="flex items-center gap-2 text-2xl font-semibold leading-none">
            <SalonIcon name="star" className="size-4 opacity-70" />
            <CountUp value={salon.staff_members.length} />
          </span>
        </Tuile>
      )}

      {salon.business_hours.length > 0 && (
        <Tuile libelle={t("hero.aujourdhui")}>
          {plages.length === 0 ? (
            <span className="text-base font-semibold">{t("statut.ferme")}</span>
          ) : (
            <span className="tabular flex flex-col gap-0.5 text-sm font-semibold leading-tight">
              {plages.map((plage, index) => (
                <span key={index}>
                  {shortTime(plage.starts_at)} – {shortTime(plage.ends_at)}
                </span>
              ))}
            </span>
          )}
        </Tuile>
      )}
    </div>
  );
}

function Tuile({
  libelle,
  children,
}: {
  libelle: string;
  children: React.ReactNode;
}) {
  return (
    /*
      Verre plutôt qu'aplat : la photo continue de vivre sous les tuiles.

      Un bloc opaque posé sur le défilé l'aurait masqué au tiers, et c'est
      justement le défilé qui montre le travail du salon. Le flou garde la
      lisibilité sans effacer ce qu'il y a derrière.
    */
    <div className="rounded-2xl border border-white/15 bg-white/10 p-3.5 backdrop-blur-md sm:p-4">
      {children}
      <p className="mt-1.5 text-[0.7rem] uppercase tracking-[0.12em] text-white/65">
        {libelle}
      </p>
    </div>
  );
}
