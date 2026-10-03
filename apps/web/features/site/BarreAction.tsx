"use client";

/**
 * La barre d'action du téléphone, et le fil de progression.
 *
 * Deux éléments de chrome, réunis ici parce qu'ils répondent à la même
 * question : sur un écran haut et étroit, où en suis-je et que puis-je faire ?
 *
 * Aucun des deux n'existe au-dessus de 640 px, où le bouton d'inscription
 * reste dans l'en-tête et où la page se voit d'un coup d'œil.
 */

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { Fleche } from "@/features/site/contenu";
import { appUrl } from "@/lib/site";

/**
 * Le fil de progression.
 *
 * L'écouteur est passif et ne fait rien d'autre qu'écrire une variable CSS :
 * la largeur est ensuite obtenue par `transform: scaleX()`, que le navigateur
 * compose sans recalculer la mise en page. Le travail par image se réduit à
 * une division.
 *
 * `requestAnimationFrame` sert de limiteur : sur un défilement rapide,
 * l'événement arrive plus souvent que l'écran ne se rafraîchit, et écrire
 * dix fois la même variable entre deux images est dix fois trop.
 */
export function Progression() {
  const fil = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let demande = 0;

    const mesurer = () => {
      demande = 0;
      const noeud = fil.current;
      if (!noeud) return;
      const parcours =
        document.documentElement.scrollHeight - window.innerHeight;
      // Une page plus courte que l'écran n'a pas d'avancement à montrer.
      const part = parcours > 0 ? window.scrollY / parcours : 0;
      noeud.style.setProperty(
        "--avance",
        String(Math.min(1, Math.max(0, part))),
      );
    };

    const surDefilement = () => {
      if (demande) return;
      demande = requestAnimationFrame(mesurer);
    };

    mesurer();
    window.addEventListener("scroll", surDefilement, { passive: true });
    window.addEventListener("resize", surDefilement, { passive: true });
    return () => {
      if (demande) cancelAnimationFrame(demande);
      window.removeEventListener("scroll", surDefilement);
      window.removeEventListener("resize", surDefilement);
    };
  }, []);

  return <div ref={fil} aria-hidden className="progression sm:hidden" />;
}

/**
 * La barre d'action.
 *
 * Elle apparaît quand le haut de page est passé et s'efface quand le grand
 * appel final entre à l'écran. Les deux bascules viennent d'un même
 * `IntersectionObserver` qui surveille deux repères, plutôt que d'un calcul
 * sur la position de défilement : une position en pixels se trompe dès que le
 * contenu change de hauteur, un repère non.
 */
export function BarreAction({
  apres,
  avant,
  masquePar = [],
}: {
  /** Identifiant de l'élément après lequel la barre apparaît. */
  apres: string;
  /** Identifiant de l'élément dont l'arrivée la fait disparaître,
   *  définitivement — on ne remonte pas au-dessus d'un appel final. */
  avant: string;
  /**
   * Sections qui portent déjà leur propre bouton d'inscription.
   *
   * Tant que l'une d'elles est à l'écran, la barre s'efface. Deux fois le
   * même appel au même instant ne donne pas deux chances de cliquer : ça
   * donne une page qui insiste — et le bouton de la section vaut mieux que
   * celui de la barre, puisqu'il emporte le nom et les couleurs choisis.
   */
  masquePar?: string[];
}) {
  const t = useTranslations("site");
  const c = useTranslations("commun");
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const debut = document.getElementById(apres);
    const fin = document.getElementById(avant);
    if (!debut || typeof IntersectionObserver === "undefined") return;

    const rivales = masquePar
      .map((id) => document.getElementById(id))
      .filter((n): n is HTMLElement => n !== null);

    let passeLeHaut = false;
    let finAtteinte = false;
    const rivaleEnVue = new Set<Element>();
    const appliquer = () =>
      setVisible(passeLeHaut && !finAtteinte && rivaleEnVue.size === 0);

    const observateur = new IntersectionObserver(
      (entrees) => {
        for (const entree of entrees) {
          if (entree.target === debut) {
            // « Passé » et non « invisible » : le haut de page sort par le
            // haut, et on ne doit pas réafficher la barre si quelqu'un
            // atteint la même section par le bas en remontant.
            passeLeHaut = entree.boundingClientRect.bottom < 0;
          } else if (entree.target === fin) {
            /*
             * « Atteinte » et non « visible ».
             *
             * Avec `isIntersecting` seul, la barre revenait dès qu'on
             * dépassait l'appel final — elle se posait alors par-dessus le
             * pied de page, à l'endroit précis où la personne a déjà tout
             * lu et déjà vu le bouton en grand.
             */
            finAtteinte =
              entree.isIntersecting || entree.boundingClientRect.top < 0;
          } else if (entree.isIntersecting) {
            rivaleEnVue.add(entree.target);
          } else {
            rivaleEnVue.delete(entree.target);
          }
        }
        appliquer();
      },
      { threshold: 0 },
    );

    observateur.observe(debut);
    if (fin) observateur.observe(fin);
    for (const rivale of rivales) observateur.observe(rivale);
    return () => observateur.disconnect();
    // `masquePar` est une liste littérale, stable d'un rendu à l'autre :
    // la comparer par identité recréerait l'observateur à chaque fois.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apres, avant, masquePar.join(",")]);

  return (
    <div
      className="barre-action sm:hidden"
      data-visible={visible}
      // Hors écran, la barre sort du parcours du clavier : un bouton qu'on ne
      // voit pas ne doit pas pouvoir recevoir le focus.
      aria-hidden={!visible}
      inert={!visible}
    >
      <a
        href={`${appUrl}/inscription`}
        tabIndex={visible ? undefined : -1}
        className="salon-gradient eclat flex items-center justify-center gap-2 rounded-2xl px-6 py-3.5 text-[0.95rem] font-semibold text-white shadow-lg"
      >
        <span className="relative z-10">{c("creerSalon")}</span>
        <Fleche className="relative z-10 size-4" />
      </a>
      <p className="mt-1.5 text-center text-[0.68rem] text-muted">
        {t("essaiCourt")}
      </p>
    </div>
  );
}
