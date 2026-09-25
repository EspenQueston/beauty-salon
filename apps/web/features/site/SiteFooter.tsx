/**
 * Pied de page du site de la plateforme.
 *
 * ---------------------------------------------------------------------------
 * Ce qui n'a pas changé
 * ---------------------------------------------------------------------------
 *
 * Il ne promet toujours rien qui n'existe pas : pas de page tarifs tant que
 * les tarifs ne sont pas validés marché par marché, pas de blog tant qu'aucun
 * article n'est écrit, pas de réseaux sociaux tant qu'aucun compte n'est
 * tenu. Un lien mort en pied de page coûte plus de confiance qu'une colonne
 * un peu courte.
 *
 * ---------------------------------------------------------------------------
 * Ce qui a changé
 * ---------------------------------------------------------------------------
 *
 * C'était une grille de liens sur fond de surface, c'est-à-dire la même
 * matière que le reste de la page. Rien n'y disait « c'est fini ».
 *
 * Maintenant : une surface sombre dans les deux thèmes, une aurore et un sol
 * en perspective derrière, des liens en cartes de verre plutôt qu'en liste, et
 * le nom en très grand, coupé par le bas. Le pied devient un lieu — le
 * sous-sol du site — au lieu d'être la dernière rangée du tableau.
 *
 * L'heure des trois villes remplace la ligne « Brazzaville · Kinshasa ·
 * Guangzhou », qui ne disait rien qu'on ne sache déjà : voir
 * `features/site/Horloges.tsx`.
 */

import { Horloges } from "@/features/site/Horloges";
import { BeautySalonFooterWordmark, BeautySalonLockup } from "@/features/ui/BeautySalonBrand";
import { getTranslations } from "next-intl/server";

import { appUrl } from "@/lib/site";

/*
  Les colonnes ne portent que des clés et des adresses.

  Les adresses, elles, ne se traduisent pas : `#film` désigne un `id` du
  document, et `appUrl` un autre hôte — l'espace professionnel, qui choisit
  sa langue tout seul.
*/
const COLONNES = [
  {
    cle: "produit",
    liens: [
      { href: "#fonctionnalites", cle: "nav.fonctionnalites" },
      { href: "#film", cle: "nav.film" },
      { href: "#etapes", cle: "nav.etapes" },
      { href: "#questions", cle: "pied.questions" },
    ],
  },
  {
    cle: "monSalon",
    liens: [
      { href: `${appUrl}/inscription`, cle: "creerSalon" },
      { href: appUrl, cle: "seConnecter" },
      { href: `${appUrl}/mot-de-passe-oublie`, cle: "pied.motDePasse" },
    ],
  },
];

export async function SiteFooter() {
  /*
    Deux traducteurs, parce que deux clés du pied vivent ailleurs :
    « Créer mon salon » et « Se connecter » sont les mêmes mots que dans
    l'en-tête, et une seule des deux traductions finirait par changer.
  */
  const t = await getTranslations("site");
  const c = await getTranslations("commun");
  const libelle = (cle: string) => (cle.includes(".") ? t(cle) : c(cle));

  return (
    <footer className="pied grain mt-10 border-t border-white/10">
      {/* Les deux calques de décor. `aria-hidden` : ils ne portent aucun
          contenu, et un lecteur d'écran n'a rien à y annoncer. */}
      <div aria-hidden className="aurore opacity-70">
        <span />
        <span />
        <span />
      </div>
      <div aria-hidden className="sol">
        <i />
      </div>

      <div className="relative z-10 mx-auto max-w-6xl px-4 pb-0 pt-14 sm:px-6 sm:pt-20">
        <div className="grid gap-8 md:grid-cols-[1.15fr_0.85fr] md:gap-12">
          {/* ------------------------------------------------- la marque */}
          <div>
            <span className="sm:hidden">
              <BeautySalonFooterWordmark />
            </span>
            <span className="hidden sm:inline-flex">
              <BeautySalonLockup />
            </span>

            <p className="mt-5 max-w-sm text-sm leading-relaxed text-[var(--pied-doux)]">
              {t("pied.promesse")}
            </p>

            <p className="mt-3 max-w-sm text-sm leading-relaxed text-[var(--pied-doux)]">
              {t("pied.donnees")}
            </p>

            {/* `max-w-md` et non `sm` : à 384 px, « Brazzaville » se faisait
                couper de deux pixels dans sa colonne. */}
            <div className="mt-6 max-w-md">
              <Horloges />
            </div>
          </div>

          {/* -------------------------------------------------- les liens */}
          {/* Deux colonnes dès le téléphone : sept liens en pile unique
              rallongent le pied d'un écran entier pour rien. */}
          <div className="grid grid-cols-2 gap-3 sm:gap-4">
            {COLONNES.map((colonne) => (
              <div
                key={colonne.cle}
                className="verre lisere halo rounded-2xl p-4 sm:p-5"
              >
                <h2 className="relative z-10 text-[0.62rem] font-semibold uppercase tracking-[0.12em] text-[var(--pied-doux)] sm:text-[0.68rem]">
                  {t(`pied.${colonne.cle}`)}
                </h2>
                <ul className="relative z-10 mt-3 space-y-1">
                  {colonne.liens.map((lien) => (
                    <li key={lien.cle}>
                      <a
                        href={lien.href}
                        className="group flex items-center gap-1.5 rounded-lg py-1.5 text-[0.8rem] text-[var(--pied-encre)] transition hover:text-[#f2a6bd] sm:text-sm"
                      >
                        <span
                          aria-hidden
                          className="inline-block size-1 shrink-0 rounded-full bg-[#d9628a] opacity-0 transition group-hover:opacity-100"
                        />
                        <span className="transition-transform group-hover:translate-x-0.5">
                          {libelle(lien.cle)}
                        </span>
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        {/* ------------------------------------------------- la mention */}
        <div className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--pied-ligne)] pt-5 text-[0.78rem] text-[var(--pied-doux)] sm:text-sm">
          <span>© {new Date().getFullYear()} Beauty Salon</span>
          <a
            href="#haut"
            className="group inline-flex items-center gap-1.5 transition hover:text-[var(--pied-encre)]"
          >
            {t("pied.revenirEnHaut")}
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden
              className="size-3.5 transition-transform group-hover:-translate-y-0.5"
            >
              <path d="M12 19V5M6 11l6-6 6 6" strokeLinecap="round" />
            </svg>
          </a>
        </div>

        {/* ------------------------------------------------ la signature */}
        {/* `aria-hidden` : le nom est déjà annoncé en haut du pied. Répété
            ici, il ne dirait rien de plus et couperait la lecture. */}
        <div
          aria-hidden
          className="pied-signature-cadre mt-6 overflow-hidden sm:mt-8"
        >
          <span className="pied-signature block text-center">BEAUTY SALON</span>
        </div>
      </div>
    </footer>
  );
}
