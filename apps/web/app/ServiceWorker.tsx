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
 * La seule exception : les notifications
 * ---------------------------------------------------------------------------
 *
 * Un push ne peut arriver que par un service worker. Le retirer en
 * développement rendrait donc les notifications invérifiables ailleurs qu'en
 * production — c'est-à-dire au moment où il est trop tard pour découvrir
 * qu'elles ne partent pas.
 *
 * Qui a activé les notifications garde donc son service worker, dans les deux
 * environnements. C'est un choix délibéré, et il ne concerne que les postes
 * où quelqu'un a cliqué : les autres retrouvent le nettoyage habituel.
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

import { CLE_OPTIN } from "@/features/dashboard/push";

function notificationsActivees(): boolean {
  try {
    return localStorage.getItem(CLE_OPTIN) === "1";
  } catch {
    // Navigation privée, stockage bloqué : on retombe sur le comportement
    // par défaut, qui est de nettoyer.
    return false;
  }
}

export function ServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    if (process.env.NODE_ENV !== "production" && !notificationsActivees()) {
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
