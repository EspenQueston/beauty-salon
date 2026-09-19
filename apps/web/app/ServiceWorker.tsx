"use client";

/**
 * Enregistrement du service worker.
 *
 * ---------------------------------------------------------------------------
 * Jamais en développement
 * ---------------------------------------------------------------------------
 *
 * Un service worker qui met en cache pendant qu'on code fait perdre plus de
 * temps qu'il n'en fait gagner : on modifie un fichier, on recharge, et l'on
 * regarde la version d'avant en cherchant pourquoi le changement « ne marche
 * pas ». Il ne s'installe donc qu'en production.
 *
 * Et s'il en traîne un d'une visite précédente — un développeur qui a ouvert
 * une version compilée, puis est revenu au serveur de développement — on le
 * retire. Sans ce nettoyage, il survit à l'origine et continue de servir ses
 * fichiers, indéfiniment.
 *
 * ---------------------------------------------------------------------------
 * Après le chargement, pas pendant
 * ---------------------------------------------------------------------------
 *
 * L'enregistrement attend `load`. Lancé pendant le rendu, il entre en
 * concurrence avec les requêtes qui peignent la page — sur un téléphone
 * d'entrée de gamme et un réseau lent, c'est-à-dire exactement là où ce
 * service worker doit aider, il retarderait ce qu'il est censé accélérer.
 */

import { useEffect } from "react";

export function ServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    if (process.env.NODE_ENV !== "production") {
      navigator.serviceWorker
        .getRegistrations()
        .then((anciens) => anciens.forEach((ancien) => ancien.unregister()))
        .catch(() => undefined);
      return;
    }

    const enregistrer = () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
        // Un service worker refusé — mode privé, réglage d'entreprise — ne
        // casse rien : le site fonctionne comme avant, simplement sans
        // cache hors ligne.
      });
    };

    if (document.readyState === "complete") {
      enregistrer();
      return;
    }

    window.addEventListener("load", enregistrer, { once: true });
    return () => window.removeEventListener("load", enregistrer);
  }, []);

  return null;
}
