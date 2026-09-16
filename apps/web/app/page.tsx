import type { Metadata } from "next";

import { AddressCheck } from "@/features/site/AddressCheck";
import { SiteFooter } from "@/features/site/SiteFooter";
import { SiteHeader } from "@/features/site/SiteHeader";
import { SitePreview } from "@/features/site/SitePreview";
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
 * La grammaire visuelle
 * ---------------------------------------------------------------------------
 *
 * Trois gestes, repris d'un bout à l'autre :
 *
 *   - **Le titre en mots empilés, ponctués d'un point de couleur.** Trois
 *     verbes, un par ligne. Une phrase se lit ; trois mots se retiennent, et
 *     c'est exactement ce qu'on demande à un haut de page.
 *   - **La numérotation visible** — 01, 02, 03 pour les étapes, 00 à 04 pour
 *     les questions. Elle dit combien il y en a avant qu'on ait fini de
 *     lire, donc elle dit que c'est court.
 *   - **Les cartes penchées qui se redressent.** Un empilement de biais se
 *     lit comme une pile d'objets posés ; le redressement dit qu'on les sort
 *     une à une.
 *
 * Rien de tout cela n'est décoratif au sens où on pourrait l'enlever sans
 * rien perdre : chaque geste porte une information de structure.
 */

export const metadata: Metadata = {
  title: "Beauty Salon — réservation en ligne pour les professionnels de la beauté",
  description:
    "Mini-site, réservation en ligne et agenda pour coiffeuses, prothésistes ongulaires, maquilleuses et barbiers au Congo, en RDC et dans la diaspora.",
};

/** Les trois mots du haut de page. Le point prend la couleur de la marque. */
const PROMESSE = ["Réservez", "Coiffez", "Encaissez"];

/** Là où le produit est utilisé. Trois repères, pas une carte du monde. */
const TERRITOIRES = ["Congo-Brazzaville", "RDC", "Chine"];

const FEATURES = [
  {
    title: "Votre mini-site",
    body: "Une page à votre nom, avec vos photos, vos prix et vos horaires. Un seul lien à partager sur WhatsApp, Instagram ou TikTok.",
    tag: "Vitrine",
    icon: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M3 9h18" />
        <path d="M7 6.5h.01M10 6.5h.01" />
      </>
    ),
  },
  {
    title: "Réservation en ligne",
    body: "Vos clientes réservent à toute heure, sur un créneau réellement libre. Deux personnes ne peuvent pas prendre la même place.",
    tag: "Agenda",
    icon: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M3 10h18M8 3v4M16 3v4" />
        <path d="m9 15 2 2 4-4" />
      </>
    ),
  },
  {
    title: "Agenda et clientes",
    body: "Vos rendez-vous, votre équipe et votre fichier clientes au même endroit. Vos données restent les vôtres, exportables à tout moment.",
    tag: "Gestion",
    icon: (
      <>
        <circle cx="9" cy="8" r="3.2" />
        <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
        <path d="M16 5.2a3.2 3.2 0 0 1 0 5.6M17.5 14.4A5.5 5.5 0 0 1 20.5 20" />
      </>
    ),
  },
];

const STEPS = [
  {
    title: "Créez votre salon",
    body: "Nom, adresse de votre mini-site, pays. Trois minutes, sans carte bancaire.",
  },
  {
    title: "Remplissez votre vitrine",
    body: "Prestations, tarifs, horaires, photos. Vous pouvez commencer avec trois prestations.",
  },
  {
    title: "Partagez votre lien",
    body: "Sur WhatsApp, en story, ou en QR code affiché au salon. Les réservations arrivent dans votre agenda.",
  },
];

const QUESTIONS = [
  {
    q: "Faut-il payer pour commencer ?",
    a: "Non. L'inscription est gratuite et sans carte bancaire. Vous disposez d'une période d'essai complète, et aucune facture n'est émise avant sa fin.",
  },
  {
    q: "Mon mini-site est-il en ligne tout de suite ?",
    a: "Votre adresse est réservée dès l'inscription, mais la page devient publique après une vérification de notre équipe. Vous pouvez préparer votre catalogue et vos horaires pendant ce temps.",
  },
  {
    q: "Et si je travaille seule ?",
    a: "C'est le cas le plus courant. Créez simplement votre propre fiche de prestataire : ce sont vos horaires et vos rendez-vous qui s'y rattachent.",
  },
  {
    q: "Comment mes clientes me paient-elles ?",
    a: "Comme aujourd'hui : espèces, Mobile Money ou virement. La plateforme suit les acomptes demandés et vous notez l'encaissement en un clic.",
  },
  {
    q: "Puis-je récupérer mes données ?",
    a: "Oui, à tout moment. Votre fichier clientes et votre historique de rendez-vous vous appartiennent.",
  },
];

export default function PlatformHome() {
  return (
    <div id="haut" className="flex min-h-svh flex-col bg-bg">
      <SiteHeader />

      {/* ------------------------------------------------------------- hero */}
      {/*
        Deux colonnes sur grand écran, une seule sur téléphone — et dans ce
        cas les mots passent avant la photo. On vient lire une promesse, pas
        regarder une image : la faire précéder le titre repousserait sous la
        ligne de flottaison la seule phrase qui doit être lue.
      */}
      <section className="mx-auto w-full max-w-6xl px-4 pb-10 pt-28 sm:px-6 sm:pt-36">
        <div className="grid items-center gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:gap-12">
          <div>
            <h1 className="text-[2.75rem] font-semibold leading-[0.95] tracking-tight text-ink sm:text-6xl lg:text-7xl">
              {PROMESSE.map((mot, index) => (
                <span
                  key={mot}
                  className="rise block"
                  style={{ animationDelay: `${index * 90}ms` }}
                >
                  {mot}
                  <span className="text-salon">.</span>
                </span>
              ))}
            </h1>

            <p
              className="rise mt-5 max-w-lg text-base leading-relaxed text-muted sm:text-lg"
              style={{ animationDelay: "300ms" }}
            >
              La plateforme de réservation des professionnels de la beauté :
              coiffure, ongles, maquillage, barbier. Un mini-site, un agenda,
              zéro double réservation.
            </p>

            <div
              className="rise mt-7 flex flex-wrap items-center gap-3"
              style={{ animationDelay: "380ms" }}
            >
              <a
                href={`${appUrl}/inscription`}
                className="salon-gradient group inline-flex items-center justify-center gap-2 rounded-xl px-6 py-3.5 font-semibold text-white shadow-lg transition hover:-translate-y-0.5 hover:brightness-110"
              >
                Créer mon salon
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden
                  className="size-4 transition-transform group-hover:translate-x-1"
                >
                  <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" />
                </svg>
              </a>
              <a
                href={appUrl}
                className="inline-flex items-center justify-center rounded-xl border border-line bg-surface px-6 py-3.5 font-medium text-ink transition hover:-translate-y-0.5 hover:border-salon"
              >
                J&apos;ai déjà un compte
              </a>
            </div>

            <p
              className="rise mt-3.5 text-sm text-subtle"
              style={{ animationDelay: "440ms" }}
            >
              Essai gratuit. Aucune carte bancaire demandée.
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

          {/* La photo, arrondie et détourée du fond. Elle illustre, elle ne
              porte aucun texte : la moitié des visiteuses la verront sur un
              écran de 360 px, où une incrustation serait illisible. */}
          <div
            className="rise order-first lg:order-none"
            style={{ animationDelay: "160ms" }}
          >
            <div className="relative overflow-hidden rounded-3xl border border-line shadow-float">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={illustrationUrl(HERO_IMAGE.id, { width: 1100, ratio: 1.05 })}
                alt=""
                fetchPriority="high"
                className="aspect-[4/3] size-full object-cover lg:aspect-[5/6]"
              />
            </div>
          </div>
        </div>

        {/* ----- La bande de confiance ------------------------------------ */}
        <Reveal className="mt-12 border-t border-line pt-6">
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-subtle">
            Utilisé par des salons au
          </p>
          <ul className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2">
            {TERRITOIRES.map((lieu) => (
              <li
                key={lieu}
                className="flex items-center gap-2 text-sm font-medium text-muted"
              >
                <span
                  aria-hidden
                  className="size-1.5 rounded-full bg-salon"
                />
                {lieu}
              </li>
            ))}
          </ul>
        </Reveal>
      </section>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 sm:px-6">
        {/* -------------------------------------------------------- features */}
        <section id="fonctionnalites" className="scroll-mt-28 py-16 sm:py-24">
          <Reveal>
            <h2 className="text-3xl font-semibold tracking-tight text-ink sm:text-5xl">
              Ce que ça vous apporte<span className="text-salon">.</span>
            </h2>
            <p className="mt-3 max-w-xl text-muted">
              Trois choses, et elles tiennent ensemble : une vitrine qui se
              partage, un agenda qui ne se trompe pas, un fichier clientes qui
              vous appartient.
            </p>
          </Reveal>

          {/* Deux colonnes dès le téléphone : ces cartes sont courtes, et une
              colonne unique les ferait défiler trois fois pour trois idées. */}
          <div className="mt-8 grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-3">
            {FEATURES.map((feature, index) => (
              <Reveal
                key={feature.title}
                variant="tilt"
                angle={index % 2 === 0 ? -3.5 : 3.5}
                delay={index * 110}
                className="h-full"
              >
                <article className="lift flex h-full flex-col rounded-2xl border border-line bg-surface p-4 shadow-card sm:p-6">
                  <span className="inline-flex size-9 items-center justify-center rounded-xl bg-salon-soft text-salon sm:size-11">
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
                      {feature.icon}
                    </svg>
                  </span>

                  <h3 className="mt-3 text-[0.95rem] font-semibold text-ink sm:mt-5 sm:text-lg">
                    {feature.title}
                  </h3>
                  <p className="mt-2 flex-1 text-[0.8rem] leading-relaxed text-muted sm:text-sm">
                    {feature.body}
                  </p>

                  <span className="mt-4 inline-flex w-fit rounded-full bg-salon-soft px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-wide text-salon">
                    {feature.tag}
                  </span>
                </article>
              </Reveal>
            ))}
          </div>
        </section>

        {/* ---------------------------------------------------------- aperçu */}
        {/*
          On rend quelque chose d'utile avant de demander quoi que ce soit :
          le nom, les couleurs, et une vérification réelle de l'adresse. Ce
          qui est composé ici accompagne l'inscription.
        */}
        <section id="apercu" className="scroll-mt-28 py-16 sm:py-24">
          <Reveal className="mb-8 text-center">
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-salon">
              Essayez avant de vous inscrire
            </p>
            <h2 className="text-3xl font-semibold tracking-tight text-ink sm:text-5xl">
              À quoi ressemblera votre page<span className="text-salon">&nbsp;?</span>
            </h2>
            <p className="mx-auto mt-3 max-w-lg text-muted">
              Tapez le nom de votre salon, choisissez vos couleurs. Aucune
              inscription, aucun e-mail demandé.
            </p>
          </Reveal>

          <Reveal>
            <SitePreview />
          </Reveal>
        </section>

        {/* ----------------------------------------------------------- étapes */}
        <section id="etapes" className="scroll-mt-28 py-16 sm:py-24">
          <Reveal>
            <h2 className="text-3xl font-semibold tracking-tight text-ink sm:text-5xl">
              Comment ça marche<span className="text-salon">.</span>
            </h2>
            <p className="mt-3 max-w-xl text-muted">
              Trois étapes. La plus longue dure trois minutes.
            </p>
          </Reveal>

          <ol className="mt-8 grid grid-cols-2 gap-3 sm:gap-6 lg:grid-cols-3">
            {STEPS.map((step, index) => (
              <Reveal key={step.title} as="li" delay={index * 110}>
                <div className="lift h-full rounded-2xl border border-line bg-surface p-4 shadow-card sm:p-6">
                  {/* Le numéro en grand plutôt qu'en pastille : il dit
                      combien il reste d'étapes avant qu'on ait fini de lire
                      la première. */}
                  <span className="tabular block text-3xl font-semibold leading-none text-salon/25 sm:text-5xl">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <h3 className="mt-3 text-[0.95rem] font-semibold text-ink sm:text-lg">
                    {step.title}
                  </h3>
                  <p className="mt-1.5 text-[0.8rem] leading-relaxed text-muted sm:text-sm">
                    {step.body}
                  </p>
                </div>
              </Reveal>
            ))}
          </ol>
        </section>

        {/* --------------------------------------------------------- questions */}
        <section id="questions" className="scroll-mt-28 py-16 sm:py-24">
          <Reveal>
            <h2 className="text-3xl font-semibold tracking-tight text-ink sm:text-5xl">
              Questions fréquentes<span className="text-salon">.</span>
            </h2>
            <p className="mt-3 max-w-xl text-muted">
              Cinq réponses, et rien qui vous engage.
            </p>
          </Reveal>

          <div className="mt-8 space-y-2.5">
            {QUESTIONS.map((item, index) => (
              <Reveal key={item.q} delay={index * 60}>
                {/* <details> plutôt qu'un accordéon en JavaScript : le contenu
                    reste dans la page pour la recherche et pour qui n'a pas
                    de script. */}
                <details className="lift group rounded-2xl border border-line bg-surface px-4 shadow-card open:shadow-float sm:px-6">
                  <summary className="flex cursor-pointer list-none items-center gap-3 py-4 font-medium text-ink [&::-webkit-details-marker]:hidden sm:gap-4">
                    <span className="tabular shrink-0 text-sm font-semibold text-salon/45">
                      {String(index).padStart(2, "0")}
                    </span>
                    <span className="flex-1 text-[0.92rem] sm:text-base">
                      {item.q}
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
                  <p className="pb-5 pl-0 text-sm leading-relaxed text-muted sm:pl-9">
                    {item.a}
                  </p>
                </details>
              </Reveal>
            ))}
          </div>
        </section>

        {/* -------------------------------------------------------------- CTA */}
        <Reveal>
          <section className="mb-20 overflow-hidden rounded-3xl border border-line bg-surface shadow-card">
            <div className="salon-gradient px-6 py-10 text-center text-white sm:px-12 sm:py-14">
              <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                Prête à ouvrir votre agenda ?
              </h2>
              <p className="mx-auto mt-3 max-w-md text-white/85">
                Créez votre salon aujourd&apos;hui, partagez votre lien demain.
              </p>
              {/*
                `text-salon` et non `text-ink`.

                Ce bouton est blanc dans les deux thèmes — il est posé sur le
                dégradé, qui reste coloré en clair comme en sombre. Son texte
                ne peut donc pas suivre le thème : `--ui-text` passe à
                #f2f2f5 en mode sombre, et le libellé devenait du blanc sur
                du blanc. Il disparaissait purement et simplement, sur
                l'unique bouton d'inscription de la page d'accueil.

                `--salon-primary` (#b4436c) ne change pas d'un thème à
                l'autre : 5,6:1 sur blanc, et c'est la teinte du dégradé qui
                l'entoure.
              */}
              <a
                href={`${appUrl}/inscription`}
                className="mt-7 inline-flex items-center justify-center gap-2 rounded-xl bg-white px-6 py-3.5 font-semibold text-salon shadow-sm transition hover:-translate-y-0.5 hover:shadow-float"
              >
                Créer mon salon
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden
                  className="size-4"
                >
                  <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" />
                </svg>
              </a>
            </div>
          </section>
        </Reveal>
      </main>

      <SiteFooter />

      {/* Pas de barre fixe sur cette page : le bouton peut coller au bas. */}
      <ScrollTop offset="1.5rem" />
    </div>
  );
}
