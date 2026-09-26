"use client";

/**
 * Passer d'une langue à l'autre, sans quitter la page où l'on est.
 *
 * ---------------------------------------------------------------------------
 * Deux boutons, et non un menu
 * ---------------------------------------------------------------------------
 *
 * Le voisin de ce bouton — le sélecteur de devise — est un menu, parce qu'il
 * propose six monnaies. Ici il y en a deux, et un menu pour deux entrées
 * demande deux gestes là où un suffit : ouvrir pour découvrir, cliquer pour
 * choisir.
 *
 * Un unique bouton bascule aurait tenu en moins de place encore, mais il pose
 * la question à laquelle personne ne répond juste : « EN » veut-il dire « vous
 * lisez l'anglais » ou « passez à l'anglais » ? Les deux langues affichées
 * côte à côte, l'une marquée comme active, ne laissent pas ce doute.
 *
 * Elles portent leur propre nom — *Français*, *English* — et jamais un
 * drapeau : une langue n'est pas un pays. L'anglais n'appartient ni au
 * Royaume-Uni ni aux États-Unis, et le français de cette plateforme se parle
 * surtout à Brazzaville et à Kinshasa.
 *
 * ---------------------------------------------------------------------------
 * Ce que le clic fait vraiment
 * ---------------------------------------------------------------------------
 *
 * Il change l'adresse — `/prestations` devient `/en/prestations` — parce que
 * la langue d'une page doit se lire dans son URL : c'est ce qui rend un lien
 * partageable et une page indexable.
 *
 * Il écrit aussi le cookie, et cet ordre compte. Sans cookie, le proxy
 * continuerait de négocier d'après `Accept-Language` à la visite suivante et
 * renverrait la personne dans la langue qu'elle vient justement de quitter.
 */

import { useLocale, useTranslations } from "next-intl";
import { usePathname } from "next/navigation";
import { useCallback } from "react";

import {
  COOKIE_LANGUE,
  DUREE_COOKIE,
  LANGUES,
  NOM_LANGUE,
  traduireChemin,
  type Langue,
} from "@/i18n/langues";

export function SelecteurLangue({
  className = "",
  classeActive = "",
  classeInactive = "",
  /** Occupe toute la largeur : dans un menu déroulant plutôt qu'une barre. */
  large = false,
}: {
  className?: string;
  classeActive?: string;
  classeInactive?: string;
  large?: boolean;
}) {
  const actuelle = useLocale() as Langue;
  const t = useTranslations("langue");
  const chemin = usePathname();

  const changer = useCallback(
    (vers: Langue) => {
      if (vers === actuelle) return;

      /*
        Le cookie est posé avant la navigation.

        Le proxy le lit à la requête suivante — celle que le chargement
        ci-dessous déclenche à l'instant. Le poser après reviendrait à se
        faire renégocier la langue qu'on vient de quitter.

        `SameSite=Lax` : le cookie doit survivre à l'arrivée depuis un lien
        WhatsApp, qui est une navigation venue d'un autre site. `Strict` le
        retiendrait précisément là.
      */
      document.cookie = `${COOKIE_LANGUE}=${vers}; path=/; max-age=${DUREE_COOKIE}; SameSite=Lax`;

      /*
        Un chargement complet, et non une navigation du routeur.

        Changer de langue traverse le segment `[locale]`, donc la mise en page
        racine. React la refabrique alors côté client — avec le `<script>` de
        thème qu'elle contient, qu'il refuse d'exécuter et signale en console
        à chaque bascule.

        Rien n'est perdu à recharger : la page change entièrement de toute
        façon — son texte, son titre d'onglet, ses balises `hreflang`, l'attribut
        `lang` de la racine. Et l'on ne change pas de langue deux fois dans une
        visite.
      */
      window.location.assign(traduireChemin(chemin, vers));
    },
    [actuelle, chemin],
  );

  return (
    <div
      role="group"
      aria-label={t("choisir")}
      className={`inline-flex items-center gap-0.5 rounded-full border p-0.5 ${
        large ? "w-full" : ""
      } ${className}`}
    >
      {LANGUES.map((langue) => {
        const active = langue === actuelle;
        return (
          <button
            key={langue}
            type="button"
            onClick={() => changer(langue)}
            // `aria-current` et non `aria-pressed` : ce n'est pas un
            // interrupteur, c'est le repère de l'endroit où l'on se trouve.
            aria-current={active ? "true" : undefined}
            // Le nom complet reste annoncé même si l'écran n'affiche que deux
            // lettres : « FR » se lit « éfe-erre » à la synthèse vocale.
            aria-label={NOM_LANGUE[langue]}
            lang={langue}
            className={`rounded-full px-2.5 py-1 text-xs font-semibold uppercase transition ${
              large ? "flex-1" : ""
            } ${active ? classeActive : classeInactive}`}
          >
            {langue}
          </button>
        );
      })}
    </div>
  );
}
