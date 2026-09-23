/*
 * Service worker de l'administration plateforme.
 *
 * ===========================================================================
 * Pourquoi il en faut un deuxième
 * ===========================================================================
 *
 * Le tableau de bord d'un salon vit sur `app.<domaine>`, l'administration sur
 * le domaine de l'API. Pour un navigateur, ce sont deux sites sans rapport :
 * deux service workers, deux abonnements push, deux boîtes aux lettres. Il
 * n'existe aucun moyen d'en partager un, et c'est heureux — une gérante ne
 * doit pas hériter du service worker de l'administration.
 *
 * ===========================================================================
 * Il ne met rien en cache, et c'est délibéré
 * ===========================================================================
 *
 * Celui du tableau de bord garde les pages pour qu'elles restent lisibles
 * sans réseau. Ici, ce serait une faute : une page d'administration contient
 * la liste des salons, des comptes, des montants. La garder sur le disque
 * d'un portable qu'on laisse dans un train n'apporterait rien à personne —
 * on n'administre pas la plateforme dans le métro.
 *
 * Aucun gestionnaire `fetch`, donc. Ce fichier ne sait faire qu'une chose :
 * afficher une notification.
 */

const REPLI = {
  titre: "Beauty Salon",
  corps: "Nouvelle notification de la plateforme.",
  lien: "/",
};

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (evenement) =>
  evenement.waitUntil(self.clients.claim()),
);

self.addEventListener("push", (evenement) => {
  let donnees = REPLI;
  try {
    if (evenement.data) {
      const lu = evenement.data.json();
      donnees = {
        titre: lu.titre || REPLI.titre,
        corps: lu.corps || "",
        lien: lu.lien || REPLI.lien,
      };
    }
  } catch {
    // Charge illisible : on affiche le repli. Ne rien montrer ferait perdre
    // au site le droit d'envoyer des notifications, définitivement.
  }

  evenement.waitUntil(
    Promise.all([
      prevenirLesOnglets(),
      self.registration.showNotification(donnees.titre, {
        body: donnees.corps,
        icon: "/static/notifications/icone-192.png",
        badge: "/static/notifications/badge.png",
        lang: "fr",
        data: { lien: donnees.lien },
      }),
    ]),
  );
});

self.addEventListener("notificationclick", (evenement) => {
  evenement.notification.close();

  const lien =
    (evenement.notification.data && evenement.notification.data.lien) || "/";
  const cible = new URL(lien, self.location.origin).href;

  evenement.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((fenetres) => {
        for (const fenetre of fenetres) {
          if (new URL(fenetre.url).origin !== self.location.origin) continue;
          if ("navigate" in fenetre) {
            return fenetre.navigate(cible).then((f) => (f || fenetre).focus());
          }
          return fenetre.focus();
        }
        return self.clients.openWindow(cible);
      }),
  );
});

/** Les onglets d'administration ouverts rafraîchissent leur cloche. */
async function prevenirLesOnglets() {
  const fenetres = await self.clients.matchAll({
    type: "window",
    includeUncontrolled: true,
  });
  for (const fenetre of fenetres) {
    fenetre.postMessage({ type: "beauty-salon:notification" });
  }
}
