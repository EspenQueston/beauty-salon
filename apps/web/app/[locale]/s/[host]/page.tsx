import { useTranslations } from "next-intl";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { ANCRE_CONTENU, Hero } from "@/features/salon/Hero";
import { ServiceCard } from "@/features/salon/ServiceCard";
import {
  VitrinePrestations,
  type CarteRendue,
} from "@/features/salon/VitrinePrestations";
import { slugCategorie, type CategorieFiltre } from "@/features/salon/catalogue";
import { TeamShowcase } from "@/features/salon/TeamShowcase";
import { GalleryGrid } from "@/features/salon/GalleryGrid";
import { SalonIcon, categoryIcon } from "@/features/salon/icons";
import {
  Card,
  EmptyNote,
  GhostLink,
  InverseLink,
  MoreLink,
  SectionTitle,
} from "@/features/salon/ui";
import { HowItWorks } from "@/features/salon/HowItWorks";
import { Marquee } from "@/features/salon/Marquee";
import { OpeningHours } from "@/features/salon/OpeningHours";
import { StatutOuverture } from "@/features/salon/Statut";
import { contactLinks, emailLink, mapsHref } from "@/features/salon/contact";
import { Reveal } from "@/features/ui/Reveal";
import { ReviewList } from "@/features/salon/Reviews";
import { fetchReviews } from "@/lib/api";
import { fetchSalon } from "@/lib/salon-serveur";
import { serviceIllustrations, themeFromCategory } from "@/lib/illustrations";
import type { PublicSalon } from "@/lib/types";

type Props = { params: Promise<{ host: string }> };

/**
 * Accueil du mini-site.
 *
 * Une vitrine, pas un catalogue : chaque section montre assez pour donner
 * envie, puis renvoie vers sa page dédiée. Le tout doit rester lisible d'un
 * pouce, sur un téléphone d'entrée de gamme, en descendant une fois.
 */
export default async function SalonHome({ params }: Props) {
  const t = await getTranslations("salon");
  const { host } = await params;
  // Les deux lectures partent ensemble : en serie, la page attendrait la
  // somme des deux latences au lieu de la plus longue.
  const [salon, reviews] = await Promise.all([
    fetchSalon(host),
    fetchReviews(host),
  ]);
  if (!salon) notFound();

  /*
   * Quatre prestations, toutes catégories confondues.
   *
   * Quatre et non six : la grille en compte quatre par ligne, et six
   * laissaient une seconde rangée à moitié vide — deux cartes orphelines
   * sous quatre, ce qui se lit comme un contenu tronqué plutôt que comme un
   * aperçu.
   *
   * C'est assez pour situer le niveau de prix, trop peu pour noyer, et le
   * lien « Les N prestations » juste à côté mène au catalogue entier.
   */
  const featured = salon.categories
    .flatMap((category) =>
      category.services.map((service) => ({ service, category })),
    )
    .slice(0, 4);

  const totalServices = salon.categories.reduce(
    (total, category) => total + category.services.length,
    0,
  );

  /*
   * Les illustrations de secours sont réparties au niveau de la grille.
   *
   * Laissées à chaque carte, elles se répétaient : toutes les prestations
   * d'un salon de tresses partagent le même thème, et ce thème ne compte que
   * quatre photos. Les quatre cartes en vedette montraient la même image.
   * Seul cet endroit connaît les quatre voisines à la fois.
   */
  const visuels = serviceIllustrations(
    featured.map(({ service, category }) => ({
      id: service.id,
      theme: themeFromCategory(category.name),
    })),
  );

  /*
   * Le filtre par catégorie de la section prestations.
   *
   * Quatre cartes au plus par catégorie, comme la sélection en vedette, et
   * leurs illustrations réparties catégorie par catégorie : c'est au sein
   * d'une même grille qu'une image répétée se remarque.
   */
  const categoriesAvecPrestations = salon.categories.filter(
    (category) => category.services.length > 0,
  );
  const categoriesFiltre: CategorieFiltre[] = categoriesAvecPrestations.map(
    (category) => ({
      id: category.id,
      slug: slugCategorie(category.name),
      nom: category.name,
      icone: categoryIcon(category.name),
      compte: category.services.length,
    }),
  );
  const parCategorie: Record<string, CarteRendue[]> = Object.fromEntries(
    categoriesAvecPrestations.map((category) => {
      const quatre = category.services.slice(0, 4);
      const theme = themeFromCategory(category.name);
      const illustrations = serviceIllustrations(
        quatre.map((service) => ({ id: service.id, theme })),
      );
      return [
        slugCategorie(category.name),
        quatre.map((service) => ({
          id: service.id,
          carte: (
            <ServiceCard
              service={service}
              icon={categoryIcon(category.name)}
              theme={theme}
              fallback={illustrations.get(service.id)}
            />
          ),
        })),
      ];
    }),
  );

  /*
   * Vitrine de l'accueil.
   *
   * Le salon désigne ses médias « en vedette » depuis son espace. Sans
   * sélection, on prend le début de la galerie — l'accueil ne doit jamais
   * rester vide simplement parce que personne n'a coché d'étoile.
   *
   * Dans les deux cas ce sont **les médias du salon**, dans son ordre : ce
   * que montre l'accueil se retrouve à l'identique sur la page
   * « Réalisations ».
   */
  const featuredMedia = salon.gallery.filter((asset) => asset.featured);
  const showcase = (
    featuredMedia.length > 0 ? featuredMedia : salon.gallery
  ).slice(0, 6);

  /*
   * L'instant du rendu, retenu une seule fois.
   *
   * La pastille d'ouverture et la tuile « aujourd'hui » se calculent toutes
   * deux à partir de lui. Appeler `Date.now()` dans chacune ferait deux
   * instants différents à quelques millisecondes d'écart — sans conséquence
   * la plupart du temps, et faux à 21 h 59 min 59 s. C'est aussi lui que le
   * navigateur reprend au premier rendu, ce qui rend l'hydratation
   * identique au caractère près.
   *
   * La règle de pureté du compilateur React interdit `Date.now()` pendant un
   * rendu, et elle a raison dans le navigateur : un composant qui se
   * re-rend lirait une heure différente à chaque fois. Ici il s'agit d'un
   * composant serveur asynchrone, rendu une seule fois par requête — il n'y
   * a pas de second rendu où l'instant pourrait changer. C'est justement
   * pour cela qu'on le fige ici et qu'on le transmet en propriété : le
   * navigateur reprend cette valeur au lieu d'en lire une autre.
   */
  // eslint-disable-next-line react-hooks/purity -- composant serveur : un seul rendu par requête
  const instantServeur = Date.now();

  return (
    <main>
      <Hero salon={salon} instantServeur={instantServeur} />

      {/*
        La bande défilante, hors du conteneur : elle traverse toute la
        largeur, ce qui est la moitié de son effet.

        Elle répond à « qu'est-ce qu'on fait ici » avant que le catalogue,
        deux écrans plus bas, n'en ait l'occasion — et une visiteuse arrivée
        d'un lien WhatsApp décide avant d'y arriver.
      */}
      <Marquee salon={salon} />

      {/*
        La cible du lien « Voir les prestations », en haut de page.

        `scroll-mt-24` réserve la hauteur du menu, qui reste collé en haut :
        sans elle, l'ancre amène le titre de section *sous* le menu, et on
        atterrit sur une page qui semble avoir sauté une ligne.
      */}
      <div id={ANCRE_CONTENU} className="mx-auto max-w-5xl scroll-mt-24 px-4">
        {featured.length > 0 ? (
          <section className="pt-4">
            {/*
              La section ne se révèle plus en bloc.

              Un `Reveal` sur la section *et* un par carte superposait deux
              fondus : les cartes montaient à l'intérieur d'un bloc qui
              montait lui aussi, et la cascade s'y noyait. Le titre garde son
              apparition, les cartes ont la leur.
            */}
            <Reveal>
              <SectionTitle
                eyebrow={t("titresAccueil.prestationsSurtitre")}
                title={t("titresAccueil.prestationsTitre")}
                action={
                  totalServices > featured.length ? (
                    <MoreLink href="/prestations">
                      {t("titresAccueil.toutesPrestations", {
                        n: totalServices,
                      })}
                    </MoreLink>
                  ) : undefined
                }
              />
            </Reveal>

            {/*
              Chaque carte se révèle pour elle-même.

              Envelopper la grille entière dans un seul `Reveal` faisait
              apparaître les six cartes d'un bloc : le mouvement existait,
              mais il ne se voyait pas — un bloc qui monte se lit comme une
              page qui se charge, pas comme un contenu qui arrive. La
              cascade, elle, se remarque.

              Le décalage est plafonné : au-delà de la sixième carte, on
              attendrait l'animation au lieu de lire.
            */}
            {/*
              Les familles, avant les cartes.

              Quatre prestations en vedette ne disent pas l'étendue du
              catalogue : un salon qui fait aussi les ongles et le maquillage
              passait pour un salon de tresses. La rangée de catégories le dit
              en une ligne, avec le compte de chacune — et, touchée, montre
              sur place les prestations de la famille choisie au lieu
              d'envoyer en haut du catalogue (voir `VitrinePrestations`).
            */}
            <VitrinePrestations
              categories={categoriesFiltre}
              total={totalServices}
              vedette={featured.map(({ service, category }, index) => ({
                id: service.id,
                carte: (
                  <Reveal delay={Math.min(index, 5) * 80}>
                    <ServiceCard
                      service={service}
                      icon={categoryIcon(category.name)}
                      theme={themeFromCategory(category.name)}
                      fallback={visuels.get(service.id)}
                    />
                  </Reveal>
                ),
              }))}
              parCategorie={parCategorie}
            />
          </section>
        ) : (
          <Reveal as="section" className="pt-4">
            <EmptyNote
              icon="scissors"
              title={t("titresAccueil.catalogueVideTitre")}
            >
              {t("titresAccueil.catalogueVideCorps")}
            </EmptyNote>
          </Reveal>
        )}
      </div>

      {/*
        « Comment ça se passe » s'intercale ici, et pas ailleurs.

        On vient de voir ce qu'on peut prendre ; la question suivante est
        comment le prendre. La poser après les réalisations et l'équipe
        reviendrait à y répondre une fois la page quittée.

        -----------------------------------------------------------------
        Pourquoi cette section sort du conteneur
        -----------------------------------------------------------------

        La page enchaînait sept sections identiques : surtitre, grand titre,
        grille de cartes blanches, et on recommence. Rien ne variait — ni la
        largeur, ni le fond, ni la densité — si bien qu'en défilant on ne
        savait plus où l'on en était. C'est précisément ce qui fait qu'un
        site se lit comme un gabarit rempli plutôt que comme une vitrine.

        Une bande teintée sur toute la largeur donne ce repère. Elle tombe au
        bon endroit : c'est la seule section qui explique un mécanisme au
        lieu de montrer un contenu, et le changement de fond dit ce
        changement de nature avant qu'on ait lu le titre.

        La teinte est calculée depuis la couleur du salon, pas fixée : un
        salon émeraude obtient une bande émeraude, et le mode sombre suit
        tout seul puisque `--site-ground` y est déjà inversé.
      */}
      <section
        className="mt-20 border-y border-[var(--site-line)] py-14 sm:py-20"
        style={{
          background:
            "color-mix(in srgb, var(--salon-primary) 7%, var(--site-ground))",
        }}
      >
        <div className="mx-auto max-w-5xl px-4">
          <Reveal>
            <SectionTitle
              eyebrow={t("titresAccueil.etapesSurtitre")}
              title={t("titresAccueil.etapesTitre")}
            />
          </Reveal>
          <HowItWorks salon={salon} />
        </div>
      </section>

      <div className="mx-auto max-w-5xl px-4">
        {showcase.length > 0 && (
          <Reveal as="section" className="pt-20">
            <SectionTitle
              eyebrow={t("titresAccueil.galerieSurtitre")}
              title={t("titresAccueil.galerieTitre")}
              action={
                salon.gallery.length > showcase.length ? (
                  <MoreLink href="/realisations">
                    {t("titresAccueil.toutesRealisations", {
                      n: salon.gallery.length,
                    })}
                  </MoreLink>
                ) : undefined
              }
            />
            <GalleryGrid assets={showcase} salonName={salon.name} />
          </Reveal>
        )}

        {salon.staff_members.length > 0 && (
          <section className="pt-20">
            <Reveal>
              <SectionTitle
                eyebrow={t("titresAccueil.equipeSurtitre")}
                title={t("titresAccueil.equipeTitre")}
                action={
                  salon.staff_members.length > 6 ? (
                    <MoreLink href="/equipe">
                      {t("titresAccueil.touteEquipe")}
                    </MoreLink>
                  ) : undefined
                }
              />
            </Reveal>

            <Reveal>
              {/* Six : deux rangées pleines dans une mosaïque de trois
                  colonnes. Au-delà, la mosaïque s'allonge plus vite que la
                  liste de noms placée à côté, et le bloc se déséquilibre. */}
              <TeamShowcase members={salon.staff_members.slice(0, 6)} />
            </Reveal>
          </section>
        )}

        {reviews.results.length > 0 && (
          <Reveal as="section" className="pt-20">
            <SectionTitle
              eyebrow={t("titresAccueil.avisSurtitre")}
              title={t("titresAccueil.avisTitre")}
            />
            <ReviewList
              reviews={reviews.results.slice(0, 4)}
              rating={{ average: reviews.average, count: reviews.count }}
              timeZone={salon.timezone}
            />
          </Reveal>
        )}

        <Reveal as="section" className="pt-20">
          <SectionTitle
            eyebrow={t("titresAccueil.infosSurtitre")}
            title={t("titresAccueil.infosTitre")}
            action={
              <MoreLink href="/infos">
                {t("titresAccueil.toutLeDetail")}
              </MoreLink>
            }
          />
          <PracticalSummary salon={salon} instantServeur={instantServeur} />
        </Reveal>

        <Reveal as="section" className="pt-20">
          <ClosingCall salon={salon} />
        </Reveal>
      </div>
    </main>
  );
}

function PracticalSummary({
  salon,
  instantServeur,
}: {
  salon: PublicSalon;
  instantServeur: number;
}) {
  const t = useTranslations("salon");
  const maps = mapsHref(salon);
  const email = emailLink(salon);
  const contacts = [...contactLinks(salon), ...(email ? [email] : [])];

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {salon.business_hours.length > 0 && (
        <Card className="lift">
          {/*
            La réponse d'abord, la grille ensuite.

            « Est-ce ouvert maintenant ? » se lit en haut de la carte ; la
            semaine entière reste dessous pour qui prépare sa venue. L'ordre
            inverse obligeait à comparer deux nombres pour une question
            binaire.
          */}
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h3 className="flex items-center gap-2 font-semibold text-[var(--site-ink)]">
              <SalonIcon
                name="clock"
                className="size-4.5 text-[var(--salon-ink)]"
              />
              Horaires
            </h3>
            <StatutOuverture
              salon={salon}
              instantServeur={instantServeur}
              ton="encre"
            />
          </div>
          <OpeningHours
            hours={salon.business_hours}
            timeZone={salon.timezone}
          />
        </Card>
      )}

      <div className="space-y-4">
        {salon.address && (
          <Card className="lift">
            <h3 className="mb-2 flex items-center gap-2 font-semibold text-[var(--site-ink)]">
              <SalonIcon
                name="pin"
                className="size-4.5 text-[var(--salon-ink)]"
              />
              {t("titresAccueil.adresse")}
            </h3>
            <p className="text-[var(--site-muted)]">
              {salon.address}
              {salon.city && <>, {salon.city}</>}
            </p>
            {maps && (
              <div className="mt-4">
                <GhostLink href={maps} external icon="arrow">
                  {t("titresAccueil.itineraire")}
                </GhostLink>
              </div>
            )}
          </Card>
        )}

        {contacts.length > 0 && (
          <Card className="lift">
            <h3 className="mb-3 flex items-center gap-2 font-semibold text-[var(--site-ink)]">
              <SalonIcon
                name="phone"
                className="size-4.5 text-[var(--salon-ink)]"
              />
              {t("titresAccueil.nousJoindre")}
            </h3>
            <ul className="space-y-2">
              {contacts.map((contact) => (
                <li key={contact.key}>
                  <a
                    href={contact.href}
                    {...(contact.external
                      ? { target: "_blank", rel: "noreferrer noopener" }
                      : {})}
                    className="flex items-center justify-between gap-3 rounded-lg py-1 text-[var(--site-muted)] transition hover:text-[var(--salon-ink)]"
                  >
                    <span className="flex items-center gap-2">
                      <SalonIcon name={contact.icon} className="size-4" />
                      {contact.label}
                    </span>
                    <span className="tabular text-sm">{contact.value}</span>
                  </a>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  );
}

function ClosingCall({ salon }: { salon: PublicSalon }) {
  const t = useTranslations("salon");
  return (
    <div className="salon-gradient relative overflow-hidden rounded-3xl px-6 py-14 text-center text-white sm:px-12">
      {/* Deux cercles très diffus : de la profondeur sans image à charger. */}
      <span
        aria-hidden
        className="pointer-events-none absolute -right-16 -top-20 size-64 rounded-full bg-white/15 blur-3xl"
      />
      <span
        aria-hidden
        className="pointer-events-none absolute -bottom-24 -left-10 size-64 rounded-full bg-black/15 blur-3xl"
      />

      <h2 className="relative text-2xl font-semibold tracking-tight sm:text-3xl">
        {t("titresAccueil.appelTitre")}
      </h2>
      <p className="relative mx-auto mt-3 max-w-md text-white/85">
        {t("titresAccueil.appelCorps", {
          heures: salon.cancellation_deadline_hours,
        })}
      </p>

      <div className="relative mt-7 flex flex-wrap justify-center gap-3">
        <InverseLink href="/reserver" icon="calendar">
          {t("titresAccueil.reserverMaintenant")}
        </InverseLink>
      </div>
    </div>
  );
}
