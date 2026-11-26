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
  let donnees = lire({});
  try {
    if (evenement.data) donnees = lire(evenement.data.json());
  } catch {
    // Charge illisible : on affiche le repli. Ne rien montrer ferait perdre
    // au site le droit d'envoyer des notifications, définitivement.
  }

  evenement.waitUntil(Promise.all([prevenirLesOnglets(), montrer(donnees)]));
});

/*
 * Lecture et affichage : la même forme que le service worker du tableau de
 * bord (apps/web/public/sw.js), qui en explique chaque champ. Les deux
 * fichiers vivent sur deux sites distincts et ne peuvent pas partager de
 * code ; ils doivent en revanche rester d'accord sur la charge, que le
 * serveur compose une seule fois (apps/notifications/habillage.py).
 */
function lire(lu) {
  const chaine = (valeur) => (typeof valeur === "string" ? valeur : "");
  const actions = Array.isArray(lu.actions)
    ? lu.actions
        .filter((a) => a && chaine(a.id) && chaine(a.titre) && chaine(a.lien))
        .map((a) => ({ id: a.id, titre: a.titre, lien: a.lien }))
    : [];

  return {
    titre: chaine(lu.titre) || REPLI.titre,
    corps: chaine(lu.corps) || (lu.titre ? "" : REPLI.corps),
    lien: chaine(lu.lien) || REPLI.lien,
    image: adresseWeb(lu.image),
    icone: adresseWeb(lu.icone),
    horodatage: Number.isFinite(lu.horodatage) ? lu.horodatage : Date.now(),
    actions,
  };
}

function adresseWeb(valeur) {
  if (typeof valeur !== "string" || !valeur) return "";
  try {
    const url = new URL(valeur, self.location.origin);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
  } catch {
    return "";
  }
}

function montrer(donnees) {
  const maximum = (self.Notification && self.Notification.maxActions) || 2;
  const actions = donnees.actions.slice(0, maximum);

  const options = {
    body: donnees.corps,
    // Le logo du salon dont il est question, s'il en a un : on sait d'un
    // coup d'oeil de qui l'on parle.
    icon: donnees.icone || "/static/notifications/icone-192.png",
    badge: "/static/notifications/badge.png",
    lang: "fr",
    timestamp: donnees.horodatage,
    actions: actions.map((a) => ({ action: a.id, title: a.titre })),
    data: {
      lien: donnees.lien,
      liens: Object.fromEntries(actions.map((a) => [a.id, a.lien])),
    },
  };
  if (donnees.image) options.image = donnees.image;

  return self.registration.showNotification(donnees.titre, options);
}

self.addEventListener("notificationclick", (evenement) => {
  evenement.notification.close();

  // Le bouton touché décide de la destination, et jamais hors de ce site.
  const donnees = evenement.notification.data || {};
  const lien =
    (evenement.action && donnees.liens && donnees.liens[evenement.action]) ||
    donnees.lien ||
    "/";
  let url = new URL(lien, self.location.origin);
  if (url.origin !== self.location.origin) url = new URL("/", self.location.origin);
  const cible = url.href;

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
