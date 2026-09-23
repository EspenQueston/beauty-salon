import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { adresses } from "@/i18n/adresses";
import { LANGUE_PAR_DEFAUT, estLangue } from "@/i18n/langues";
import { locale as segment } from "next/root-params";
import { PLATFORM_DOMAIN } from "@/lib/site";

import { AddressCheck } from "@/features/site/AddressCheck";
import { BarreAction, Progression } from "@/features/site/BarreAction";
import { ATOUTS, ETAPES, Fleche, QUESTIONS } from "@/features/site/contenu";
import { Film } from "@/features/site/Film";
import { BandeauTerritoires, HautMobile } from "@/features/site/HautMobile";
import { RailAtouts } from "@/features/site/RailAtouts";
import { SiteFooter } from "@/features/site/SiteFooter";
import { SiteHeader } from "@/features/site/SiteHeader";
import { SitePreview } from "@/features/site/SitePreview";
import { Relief } from "@/features/ui/Relief";
import { Reveal } from "@/features/ui/Reveal";
import { ScrollTop } from "@/features/ui/ScrollTop";
import { ILLUSTRATIONS, illustrationUrl } from "@/lib/illustrations";
import { appUrl } from "@/lib/site";

/** Salon contemporain : la photo qui dit le métier en un coup d'œil. */
const HERO_IMAGE = ILLUSTRATIONS.find(
  (entry) => entry.id === "photo-1600948836101-f9ffda59d250",
)!;

/**
 * Page de la plateforme, servie sur le domaine racine.
 *
 * Elle a un seul travail : faire comprendre en dix secondes ce que le
 * produit fait, et mener à l'inscription. Tout le reste — tarifs détaillés,
 * témoignages, comparatifs — attend d'avoir des salons pilotes qui
 * pourraient les alimenter honnêtement.
 *
 * ---------------------------------------------------------------------------
 * Deux mises en page, un seul texte
 * ---------------------------------------------------------------------------
 *
 * Sous 640 px la page prend une autre forme, et ce n'est pas la même chose
 * qu'un contenu qui rétrécit. Ce qui change, et pourquoi :
 *
 *   - **le haut de page** est reconstruit (`HautMobile`) : la photo remonte
 *     avant le texte explicatif, et le vérificateur d'adresse descend dans sa
 *     propre section. Avant, il fallait deux écrans pour atteindre le premier
 *     bouton ;
 *   - **les trois atouts** défilent en rail plutôt que de se serrer à deux
 *     colonnes, où chaque ligne tenait quatre mots ;
 *   - **les étapes** deviennent une frise verticale : elles sont ordonnées, et
 *     trois cartes côte à côte ne le disent pas ;
 *   - **une barre d'action** reste au bas de l'écran entre le haut de page et
 *     l'appel final, parce qu'entre les deux il n'y avait rien à toucher.
 *
 * Le texte, lui, vit dans `features/site/contenu.tsx` et n'est écrit qu'une
 * fois : deux mises en page qui liraient chacune leur copie finiraient par ne
 * plus dire la même chose, et personne ne les regarde jamais en même temps.
 *
 * ---------------------------------------------------------------------------
 * La grammaire visuelle
 * ---------------------------------------------------------------------------
 *
 * Trois gestes de mise en page, repris d'un bout à l'autre :
 *
 *   - **Le titre en mots empilés, ponctués d'un point de couleur.** Trois
 *     verbes, un par ligne. Une phrase se lit ; trois mots se retiennent.
 *   - **La numérotation visible** — 01, 02, 03 pour les étapes, 00 à 04 pour
 *     les questions. Elle dit combien il y en a avant qu'on ait fini de lire.
 *   - **Les cartes penchées qui se redressent.** Un empilement de biais se
 *     lit comme une pile d'objets posés ; le redressement dit qu'on les sort
 *     une à une.
 *
 * Et trois matières, définies dans `globals.css` : l'aurore (des masses de
 * couleur qui dérivent derrière le haut de page), le verre (surfaces
 * translucides à 78 %, pour que le contraste reste celui du thème) et le
 * relief (les cartes suivent le curseur, leur contenu décolle du plan).
 *
 * Rien de tout cela n'est décoratif au sens où on pourrait l'enlever sans
 * rien perdre, et chaque matière s'annule proprement sous
 * `prefers-reduced-motion`.
 */

/*
  Le titre, la description et les adresses de cette page, par langue.

  Les `hreflang` sont écrits ici en dur plutôt que lus dans un en-tête
  comme sur les mini-sites : cette page-ci est pré-rendue, une copie par
  langue, et lire un en-tête de requête la ferait basculer au rendu à la
  demande. Elle n'a qu'un chemin — la racine — donc rien à déduire.
*/
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("accueil");
  const brut = await segment();
  const langue = estLangue(brut) ? brut : LANGUE_PAR_DEFAUT;

  return {
    title: t("titreOnglet"),
    description: t("description"),
    alternates: adresses(PLATFORM_DOMAIN, "/", langue),
  };
}

/** Le décor de fond : un calque, aucun contenu. */
function Aurore() {
  return (
    <div aria-hidden className="aurore">
      <span />
      <span />
      <span />
    </div>
  );
}

/** L'intitulé d'une section, plus compact sur téléphone. */
function TitreSection({
  titre,
  ponctuation = ".",
  sous,
  centre = false,
  surtitre,
}: {
  titre: string;
  ponctuation?: string;
  sous: string;
  centre?: boolean;
  surtitre?: string;
}) {
  return (
    <Reveal className={centre ? "mb-7 text-center sm:mb-8" : ""}>
      {surtitre && (
        <p className="mb-2 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-salon-ink sm:text-xs">
          {surtitre}
        </p>
      )}
      <h2 className="texte-aurore text-[1.75rem] font-semibold leading-tight tracking-tight sm:text-5xl">
        {titre}
        <span className="text-salon-ink">{ponctuation}</span>
      </h2>
      <p
        className={`mt-3 text-[0.9rem] leading-relaxed text-muted sm:text-base ${
          centre ? "mx-auto max-w-lg" : "max-w-xl"
        }`}
      >
        {sous}
      </p>
    </Reveal>
  );
}

export default async function PlatformHome() {
  const t = await getTranslations("accueil");
  const c = await getTranslations("commun");
  const brut = await segment();
  const langue = estLangue(brut) ? brut : LANGUE_PAR_DEFAUT;
  /* `raw` et non `t` : ces trois clés portent des listes, pas des phrases.
     Leur longueur peut changer d'une langue à l'autre — et la mise en page
     ne compte jamais dessus. */
  const promesse = t.raw("promesse") as string[];
  const territoires = t.raw("territoires") as string[];

  const photo = illustrationUrl(HERO_IMAGE.id, { width: 1100, ratio: 1.05 });
  const photoMobile = illustrationUrl(HERO_IMAGE.id, {
    width: 900,
    ratio: 0.7,
  });

  return (
    <div id="haut" className="flex min-h-svh flex-col bg-bg">
      <Progression />
      <SiteHeader />

      {/* ----------------------------------------------- haut de page, mobile */}
      <div id="accroche">
        <HautMobile photo={photoMobile} />
        <div className="px-4 sm:hidden">
          <BandeauTerritoires lieux={territoires} />
        </div>
      </div>

      {/* ---------------------------------------------- haut de page, bureau */}
      {/*
        Deux colonnes, les mots à gauche. `isolate` crée un contexte
        d'empilement : l'aurore reste derrière le contenu de cette section
        sans qu'aucun z-index n'ait à courir sur le reste de la page.
      */}
      <section className="relative isolate hidden overflow-hidden px-4 pb-10 pt-28 sm:block sm:px-6 sm:pt-36">
        <Aurore />

        <div className="relative z-10 mx-auto w-full max-w-6xl">
          <div className="grid items-center gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:gap-12">
            <div>
              <h1 className="text-[2.75rem] font-semibold leading-[0.95] tracking-tight text-ink sm:text-6xl lg:text-7xl">
                {promesse.map((mot, index) => (
                  <span
                    key={mot}
                    className="rise block"
                    style={{ animationDelay: `${index * 90}ms` }}
                  >
                    {mot}
                    <span className="text-salon-ink">.</span>
                  </span>
                ))}
              </h1>

              <p
                className="rise mt-5 max-w-lg text-base leading-relaxed text-muted sm:text-lg"
                style={{ animationDelay: "300ms" }}
              >
                {t("intro")}
              </p>

              <div
                className="rise mt-7 flex flex-wrap items-center gap-3"
                style={{ animationDelay: "380ms" }}
              >
                <a
                  href={`${appUrl}/inscription`}
                  className="salon-gradient group inline-flex items-center justify-center gap-2 rounded-xl px-6 py-3.5 font-semibold text-white shadow-lg transition hover:-translate-y-0.5 hover:brightness-110"
                >
                  {c("creerSalon")}
                  <Fleche className="size-4 transition-transform group-hover:translate-x-1" />
                </a>

                <a
                  href="#film"
                  className="verre lisere group inline-flex items-center justify-center gap-2 rounded-xl px-6 py-3.5 font-medium text-ink transition hover:-translate-y-0.5"
                >
                  <span className="grid size-5 place-items-center rounded-full bg-salon text-white">
                    <svg
                      viewBox="0 0 24 24"
                      fill="currentColor"
                      aria-hidden
                      className="size-2.5 translate-x-px"
                    >
                      <path d="M8 5.2 19 12 8 18.8Z" />
                    </svg>
                  </span>
                  {t("voirFilm")}
                  {/* `text-muted` et non `text-subtle` : à 12 px, le gris
                      discret ne donnait que 3,83:1 en thème sombre. */}
                  <span className="tabular text-xs text-muted">
                    {t("dureeFilm")}
                  </span>
                </a>
              </div>

              <p
                className="rise mt-3.5 text-sm text-muted"
                style={{ animationDelay: "440ms" }}
              >
                {t("essai")}
              </p>

              {/* Un résultat utile avant toute inscription : savoir si son
                  adresse est libre. La personne repart avec l'information même
                  si elle ne crée pas de compte. */}
              <div
                className="rise mt-8 max-w-lg"
                style={{ animationDelay: "500ms" }}
              >
                <AddressCheck />
              </div>
            </div>

            {/* La photo, arrondie et détourée du fond. Les deux pastilles
                posées dessus sont de l'interface, pas du texte de vente — ce
                sont les mêmes éléments que le film montre en grand. */}
            <div className="rise" style={{ animationDelay: "160ms" }}>
              <Relief force={0.6} reflet={false}>
                <div className="relative">
                  <div className="lisere relative overflow-hidden rounded-3xl border border-line shadow-float">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={photo}
                      alt=""
                      className="aspect-[4/3] size-full object-cover lg:aspect-[5/6]"
                    />
                  </div>

                  <span className="couche-3 verre absolute left-2 top-4 flex items-center gap-2 rounded-xl px-3 py-2 shadow-float sm:-left-4 sm:top-10">
                    <span
                      aria-hidden
                      className="pouls size-2 shrink-0 rounded-full bg-salon"
                    />
                    <span className="tabular text-[0.72rem] font-semibold text-ink sm:text-sm">
                      10:30 · Cornrows
                    </span>
                  </span>

                  <span className="couche-2 verre absolute bottom-6 right-2 flex max-w-[calc(100%-1rem)] items-center gap-2 rounded-xl px-3 py-2 shadow-float sm:-right-4 sm:bottom-8">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      aria-hidden
                      className="size-3.5 shrink-0 text-salon-ink"
                    >
                      <path
                        d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"
                        strokeLinecap="round"
                      />
                    </svg>
                    <span className="truncate text-[0.72rem] font-medium text-ink sm:text-sm">
                      aminata.beauty-salon.com
                    </span>
                  </span>
                </div>
              </Relief>
            </div>
          </div>

          <Reveal className="mt-12 border-t border-line pt-6">
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-subtle">
              {t("utilisePar")}
            </p>
            <ul className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2">
              {territoires.map((lieu) => (
                <li
                  key={lieu}
                  className="flex items-center gap-2 text-sm font-medium text-muted"
                >
                  <span
                    aria-hidden
                    className="pouls size-1.5 rounded-full bg-salon"
                  />
                  {lieu}
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </section>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 sm:px-6">
        {/* --------------------------------------------------------- atouts */}
        <section id="fonctionnalites" className="scroll-mt-24 py-12 sm:py-24">
          <TitreSection titre={t("atouts.titre")} sous={t("atouts.sous")} />

          <div className="mt-6 sm:mt-8">
            {/* Téléphone : un rail qu'on fait glisser au pouce. */}
            <RailAtouts atouts={ATOUTS} />

            {/* Grand écran : la grille, inchangée. */}
            <div className="hidden gap-5 sm:grid sm:grid-cols-2 lg:grid-cols-3">
              {ATOUTS.map((atout, index) => (
                <Reveal
                  key={atout.cle}
                  variant="tilt"
                  angle={index % 2 === 0 ? -3.5 : 3.5}
                  delay={index * 110}
                  className="h-full"
                >
                  {/*
                    `Relief` remplace ici le survol `.lift`. Les deux jouaient
                    sur `transform` : le soulèvement annulait l'inclinaison, et
                    la carte sautait au lieu de tourner.

                    `reflet={false}` : le reflet de `Relief` et `.halo` sont la
                    même lumière, et le premier revendique `::after`, que
                    `.lisere` utilise pour son anneau. Une lumière par carte.
                  */}
                  <Relief reflet={false} className="h-full">
                    <article className="verre lisere halo relative flex h-full flex-col overflow-hidden rounded-2xl p-6 shadow-card">
                      {/* Le numéro en contour, derrière : il situe la carte
                          dans la série sans concurrencer son titre. */}
                      <span
                        aria-hidden
                        className="chiffre-fantome tabular pointer-events-none absolute -right-1 -top-2 z-0 text-7xl font-bold"
                      >
                        {String(index + 1).padStart(2, "0")}
                      </span>

                      <span className="couche-1 relative z-10 inline-flex size-11 items-center justify-center rounded-xl bg-salon-soft text-salon-ink">
                        <svg
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.7"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          aria-hidden
                          className="size-5"
                        >
                          {atout.icone}
                        </svg>
                      </span>

                      <h3 className="relative z-10 mt-5 text-lg font-semibold text-ink">
                        {t(`atouts.${atout.cle}.titre`)}
                      </h3>
                      <p className="relative z-10 mt-2 flex-1 text-sm leading-relaxed text-muted">
                        {t(`atouts.${atout.cle}.corps`)}
                      </p>

                      <span className="relative z-10 mt-4 inline-flex w-fit rounded-full bg-salon-soft px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-wide text-salon-ink">
                        {t(`atouts.${atout.cle}.etiquette`)}
                      </span>
                    </article>
                  </Relief>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        {/* ------------------------------------------------------------ film */}
        {/*
          Le film dit en vingt-neuf secondes ce que les trois cartes
          ci-dessus disent en trois paragraphes. Il vient après et non avant :
          on lit plus vite qu'on ne regarde, et une personne pressée doit
          pouvoir repartir sans avoir rien lancé.
        */}
        <section id="film" className="scroll-mt-24 py-12 sm:py-24">
          <TitreSection
            centre
            surtitre={t("film.surtitre")}
            titre={t("film.titre")}
            sous={t("film.sous")}
          />
          <Reveal>
            <Film />
          </Reveal>
        </section>

        {/* -------------------------------------------- l'adresse, téléphone */}
        {/*
          Sur grand écran, ce bloc est dans le haut de page — il y a la place.
          Sur téléphone il occupait un écran entier avant qu'on ait compris de
          quoi il s'agit, alors il descend ici : on vient de voir le produit,
          la question « mon nom est-il libre ? » a enfin un sens.
        */}
        <section className="py-4 sm:hidden">
          <Reveal>
            <div className="verre lisere rounded-3xl p-5 shadow-card">
              <AddressCheck nu />
            </div>
          </Reveal>
        </section>

        {/* ---------------------------------------------------------- aperçu */}
        {/*
          On rend quelque chose d'utile avant de demander quoi que ce soit :
          le nom, les couleurs, et une vérification réelle de l'adresse.
        */}
        <section id="apercu" className="scroll-mt-24 py-12 sm:py-24">
          {/* L'espace insécable avant le point d'interrogation est une
              règle française ; l'anglais n'en met pas. */}
          <TitreSection
            centre
            surtitre={t("apercu.surtitre")}
            titre={t("apercu.titre")}
            ponctuation={langue === "fr" ? "\u00a0?" : "?"}
            sous={t("apercu.sous")}
          />
          <Reveal>
            <SitePreview />
          </Reveal>
        </section>

        {/* ---------------------------------------------------------- étapes */}
        <section id="etapes" className="scroll-mt-24 py-12 sm:py-24">
          <TitreSection titre={t("etapes.titre")} sous={t("etapes.sous")} />

          {/* Téléphone : une frise verticale. L'ordre est l'information — la
              troisième étape n'a aucun sens avant la première. */}
          <ol className="frise mt-7 space-y-4 sm:hidden">
            {ETAPES.map((etape, index) => (
              <Reveal key={etape} as="li" delay={index * 90}>
                <span aria-hidden className="frise-noeud">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="verre lisere rounded-2xl p-4 shadow-card">
                  <h3 className="text-[0.98rem] font-semibold text-ink">
                    {t(`etapes.${etape}.titre`)}
                  </h3>
                  <p className="mt-1.5 text-[0.84rem] leading-relaxed text-muted">
                    {t(`etapes.${etape}.corps`)}
                  </p>
                </div>
              </Reveal>
            ))}
          </ol>

          {/* Grand écran : trois colonnes. */}
          <ol className="mt-8 hidden gap-6 sm:grid sm:grid-cols-3">
            {ETAPES.map((etape, index) => (
              <Reveal key={etape} as="li" delay={index * 110}>
                <Relief reflet={false} className="h-full">
                  <div className="verre lisere halo relative h-full overflow-hidden rounded-2xl p-6 shadow-card">
                    {/* Le numéro en grand plutôt qu'en pastille : il dit
                        combien il reste d'étapes avant qu'on ait fini de lire
                        la première. */}
                    <span className="couche-1 tabular relative z-10 block text-5xl font-semibold leading-none text-salon-ink/25">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <h3 className="relative z-10 mt-3 text-lg font-semibold text-ink">
                      {t(`etapes.${etape}.titre`)}
                    </h3>
                    <p className="relative z-10 mt-1.5 text-sm leading-relaxed text-muted">
                      {t(`etapes.${etape}.corps`)}
                    </p>
                  </div>
                </Relief>
              </Reveal>
            ))}
          </ol>
        </section>

        {/* -------------------------------------------------------- questions */}
        <section id="questions" className="scroll-mt-24 py-12 sm:py-24">
          <TitreSection
            titre={t("questions.titre")}
            sous={t("questions.sous")}
          />

          <div className="mt-6 space-y-2.5 sm:mt-8">
            {QUESTIONS.map((cle, index) => (
              <Reveal key={cle} delay={index * 60}>
                {/* <details> plutôt qu'un accordéon en JavaScript : le contenu
                    reste dans la page pour la recherche et pour qui n'a pas
                    de script. */}
                <details className="verre lisere halo group rounded-2xl px-4 shadow-card open:shadow-float sm:px-6">
                  <summary className="relative z-10 flex cursor-pointer list-none items-center gap-3 py-4 font-medium text-ink [&::-webkit-details-marker]:hidden sm:gap-4">
                    <span className="tabular shrink-0 text-sm font-semibold text-salon-ink/45">
                      {String(index).padStart(2, "0")}
                    </span>
                    <span className="flex-1 text-[0.92rem] sm:text-base">
                      {t(`questions.${cle}.q`)}
                    </span>
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      aria-hidden
                      className="size-5 shrink-0 text-subtle transition-transform group-open:rotate-180"
                    >
                      <path d="M12 5v14M6 13l6 6 6-6" strokeLinecap="round" />
                    </svg>
                  </summary>
                  <p className="relative z-10 pb-5 text-[0.86rem] leading-relaxed text-muted sm:pl-9 sm:text-sm">
                    {t(`questions.${cle}.a`)}
                  </p>
                </details>
              </Reveal>
            ))}
          </div>
        </section>

        {/* -------------------------------------------------------------- CTA */}
        <Reveal>
          <section
            id="appel"
            className="relative mb-16 overflow-hidden rounded-3xl border border-line shadow-card sm:mb-20"
          >
            <div className="salon-gradient grain relative overflow-hidden px-5 py-12 text-center text-white sm:px-12 sm:py-16">
              {/* Le sol en perspective sous l'appel : le dégradé seul est
                  plat, et cette section est la dernière chose qu'on voit
                  avant le formulaire. */}
              <div aria-hidden className="sol opacity-60">
                <i />
              </div>

              <div className="relative z-10">
                <h2 className="text-[1.7rem] font-semibold leading-tight tracking-tight sm:text-4xl">
                  {t("appel.titre")}
                </h2>
                <p className="mx-auto mt-3 max-w-md text-[0.9rem] text-white/85 sm:text-base">
                  {t("appel.sous")}
                </p>
                {/*
                  `text-salon` — ni `text-ink`, ni `text-salon-ink`.

                  Ce bouton est blanc dans les deux thèmes — il est posé sur le
                  dégradé, qui reste coloré en clair comme en sombre. Son texte
                  ne peut donc suivre **aucun** des deux jetons qui changent
                  avec le thème :

                    - `--ui-text` passe à #f2f2f5 en sombre : le libellé
                      devenait du blanc sur du blanc, et disparaissait
                      purement et simplement de l'unique bouton
                      d'inscription de la page ;
                    - `--salon-ink` s'éclaircit en sombre, pour rester
                      lisible sur un fond noir. Ici le fond est blanc : la
                      même correction donne 3,4:1, donc le défaut inverse.

                  `--salon-primary` (#b4436c) ne change pas d'un thème à
                  l'autre : 5,6:1 sur blanc, et c'est la teinte du dégradé qui
                  l'entoure.
                */}
                <a
                  href={`${appUrl}/inscription`}
                  className="mt-7 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-white px-6 py-4 font-semibold text-salon shadow-sm transition hover:-translate-y-0.5 hover:shadow-float sm:w-auto sm:rounded-xl sm:py-3.5"
                >
                  {c("creerSalon")}
                  <Fleche />
                </a>
              </div>
            </div>
          </section>
        </Reveal>
      </main>

      <SiteFooter />

      {/*
        Le bouton « remonter » et la barre d'action occupent le même coin. Sur
        téléphone c'est la barre qui gagne : elle mène quelque part, lui ne
        fait que défiler. `sm:contents` efface l'enveloppe au-dessus de 640 px,
        où le bouton reprend sa place.
      */}
      <div className="hidden sm:contents">
        <ScrollTop offset="1.5rem" />
      </div>

      {/* `#apercu` porte son propre bouton d'inscription, qui emporte le
          nom et les couleurs que la personne vient de choisir : la barre
          s'efface pendant ce temps plutôt que de le doubler. */}
      <BarreAction apres="accroche" avant="appel" masquePar={["apercu"]} />
    </div>
  );
}
