/*
 * Service worker — ce qui reste lisible quand le réseau lâche.
 *
 * ===========================================================================
 * Ce qu'il fait, et pourquoi il est aussi prudent
 * ===========================================================================
 *
 * Le produit s'adresse à des téléphones sur des réseaux qui coupent : un
 * 3G de Brazzaville dans un immeuble, un métro de Guangzhou. Sans lui, une
 * coupure d'une seconde pendant une navigation donne une page blanche et le
 * dinosaure du navigateur.
 *
 * Mais un cache mal réglé est pire qu'aucun cache. Deux dangers, et ce
 * fichier est écrit autour d'eux :
 *
 *   1. **Servir les données d'un salon à un autre.** Chaque sous-domaine est
 *      une origine distincte pour le navigateur : `blondrose.localhost` et
 *      `nailsbyfaty.localhost` ont chacun leur service worker et leur cache,
 *      sans passerelle possible. L'isolation est donc structurelle, pas une
 *      règle qu'on écrirait ici et qu'on pourrait oublier.
 *
 *   2. **Garder une réponse authentifiée sur un téléphone partagé.** Rien de
 *      ce qui vient de l'API n'est mis en cache : elle répond sur une autre
 *      origine, donc toutes ses réponses sont écartées par le premier test
 *      ci-dessous. Ce qu'on garde, ce sont les fichiers de l'application —
 *      styles, scripts, polices, images — et le squelette des pages, qui ne
 *      contiennent aucune donnée de cliente.
 *
 * ===========================================================================
 * Les stratégies
 * ===========================================================================
 *
 *   - **Fichiers versionnés** (`/_next/static/…`) : cache d'abord. Leur nom
 *     contient une empreinte du contenu, donc une réponse en cache ne peut
 *     pas être périmée — elle appartient à une version qui ne changera plus.
 *
 *   - **Navigations** : réseau d'abord, cache ensuite, page hors ligne en
 *     dernier. L'inverse ferait lire hier à qui a du réseau aujourd'hui.
 *
 *   - **Le reste** (images, polices, icônes) : cache d'abord, en rafraîchis-
 *     sant en arrière-plan. Une photo de coiffure ne change pas d'un jour à
 *     l'autre, et c'est ce qui coûte le plus cher sur un forfait à la donnée.
 */

const VERSION = "v1";
const CACHE = `beauty-salon-${VERSION}`;
const HORS_LIGNE = "/hors-ligne";

/*
 * Le strict minimum, mis de côté à l'installation.
 *
 * Seulement la page hors ligne : le reste se remplit à l'usage. Précharger
 * un catalogue entier consommerait le forfait de quelqu'un pour des pages
 * qu'il n'ouvrira peut-être jamais.
 */
self.addEventListener("install", (evenement) => {
  evenement.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll([HORS_LIGNE]))
      // Une installation ne doit jamais échouer sur un détail : sans la page
      // hors ligne, le service worker sert encore le reste.
      .catch(() => undefined)
      .then(() => self.skipWaiting()),
  );
});

/*
 * `skipWaiting` + `claim` : la nouvelle version prend la main tout de suite.
 *
 * C'est sans danger ici parce que les fichiers versionnés portent leur
 * empreinte dans leur nom : une page déjà ouverte continue de demander les
 * siens, qui existent toujours. Le risque classique — une page ancienne
 * servie par des scripts neufs — ne se présente pas.
 */
self.addEventListener("activate", (evenement) => {
  evenement.waitUntil(
    caches
      .keys()
      .then((noms) =>
        Promise.all(
          noms.filter((nom) => nom !== CACHE).map((nom) => caches.delete(nom)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

function versionne(url) {
  return url.pathname.startsWith("/_next/static/");
}

function statique(requete) {
  return ["image", "font", "style", "script"].includes(requete.destination);
}

self.addEventListener("fetch", (evenement) => {
  const { request } = evenement;
  const url = new URL(request.url);

  // Une seule origine, la nôtre. Tout ce qui part vers l'API — donc toute
  // donnée de salon ou de cliente — sort d'ici sans être touché.
  if (url.origin !== self.location.origin) return;

  // On ne met en cache que ce qui se relit : un POST change l'état du
  // serveur, le rejouer depuis un cache serait une faute.
  if (request.method !== "GET") return;

  if (versionne(url)) {
    evenement.respondWith(cacheDAbord(request));
    return;
  }

  if (request.mode === "navigate") {
    evenement.respondWith(reseauDAbord(request));
    return;
  }

  if (statique(request)) {
    evenement.respondWith(cacheDAbord(request));
  }
});

async function cacheDAbord(request) {
  const cache = await caches.open(CACHE);
  const garde = await cache.match(request);
  if (garde) return garde;

  try {
    const reponse = await fetch(request);
    // Seules les réponses complètes et réussies entrent. Une 404 ou une
    // réponse partielle mise en cache se reservirait indéfiniment.
    if (reponse.ok && reponse.type === "basic") {
      cache.put(request, reponse.clone());
    }
    return reponse;
  } catch (erreur) {
    // Rien en cache, rien sur le réseau : on laisse le navigateur dire ce
    // qu'il sait dire. Inventer une réponse vide masquerait la panne.
    throw erreur;
  }
}

async function reseauDAbord(request) {
  const cache = await caches.open(CACHE);

  try {
    const reponse = await fetch(request);
    if (reponse.ok && reponse.type === "basic") {
      cache.put(request, reponse.clone());
    }
    return reponse;
  } catch {
    const garde = await cache.match(request);
    if (garde) return garde;

    const secours = await cache.match(HORS_LIGNE);
    if (secours) return secours;

    return new Response(
      "<!doctype html><meta charset=utf-8><title>Hors ligne</title>" +
        "<p style=\"font:16px system-ui;padding:2rem\">Pas de connexion. " +
        "Réessayez dans un moment.</p>",
      { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } },
    );
  }
}

/* ===========================================================================
 * Notifications push
 * ===========================================================================
 *
 * C'est ici que le service worker cesse d'être un cache. Ces deux
 * gestionnaires sont réveillés par le navigateur **alors qu'aucun onglet du
 * site n'est ouvert** — c'est tout l'intérêt : une gérante dont le téléphone
 * est dans sa poche apprend qu'un acompte vient d'arriver.
 *
 * Le message est déjà déchiffré quand il nous parvient. Le service de push
 * de l'éditeur du navigateur l'a transporté sans pouvoir le lire : le
 * chiffrement est fait côté serveur avec les clés que ce navigateur a
 * fournies en s'abonnant. C'est la norme, pas une précaution maison.
 */

/** Ce qu'on affiche quand la charge est illisible ou absente. */
const REPLI = {
  titre: "Beauty Salon",
  corps: "Vous avez une nouvelle notification.",
  lien: "/",
};

/*
 * Les genres qui font vibrer.
 *
 * Un seul : l'acompte à vérifier. De l'argent est parti et quelqu'un attend
 * une réponse — c'est la seule alerte du produit qui justifie de sortir un
 * téléphone de la poche. Faire vibrer pour un avis habituerait à ignorer la
 * vibration, y compris le jour où elle compte.
 */
const URGENTS = new Set(["acompte_a_verifier"]);

self.addEventListener("push", (evenement) => {
  /*
    Une charge vide n'est pas une erreur.

    Certains navigateurs réveillent le service worker sans données — pour
    vérifier qu'il répond, ou quand la charge a été perdue. La norme exige
    qu'on affiche **quelque chose** : ne rien montrer fait perdre au site le
    droit d'envoyer des notifications, silencieusement et définitivement.
  */
  let donnees = lire({});
  try {
    if (evenement.data) donnees = lire(evenement.data.json());
  } catch {
    // Charge non-JSON : on garde le repli plutôt que de ne rien montrer.
  }

  evenement.waitUntil(Promise.all([prevenirLesOnglets(), montrer(donnees)]));
});

/**
 * La charge reçue, remise en forme et vérifiée.
 *
 * Elle vient de notre serveur, mais transite par celui de l'éditeur du
 * navigateur : on ne recopie donc que ce qu'on attend, avec le type qu'on
 * attend. Une adresse d'image qui ne serait pas http(s) est écartée.
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
    genre: chaine(lu.genre),
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

/**
 * L'affichage.
 *
 * Ce que le système sait montrer, et ce qu'on lui donne :
 *
 *   - `image` : la grande image en tête — la photo de la prestation, la
 *     bannière du salon, ou l'image composée à ses couleurs. Windows, Android
 *     et ChromeOS l'affichent ; macOS et iOS l'ignorent sans rien casser ;
 *   - `icon` : le logo du salon, à défaut l'icône de l'application ;
 *   - `actions` : les boutons, deux au plus — c'est ce qu'affichent Chrome et
 *     Edge. Un navigateur qui n'en affiche pas garde le clic sur la
 *     notification entière ;
 *   - `timestamp` : l'heure de l'événement. Un message remis le matin,
 *     téléphone éteint la nuit, dit « 23:14 » et non « à l'instant ».
 */
function montrer(donnees) {
  const maximum =
    (self.Notification && self.Notification.maxActions) || 2;
  const actions = donnees.actions.slice(0, maximum);

  const options = {
    body: donnees.corps,
    icon: donnees.icone || "/icones/192.png",
    // Le badge est la petite forme monochrome de la barre d'état Android.
    // Sans lui, le système affiche un carré gris générique.
    badge: "/icones/badge.png",
    lang: "fr",
    timestamp: donnees.horodatage,
    actions: actions.map((a) => ({ action: a.id, title: a.titre })),
    /*
      Pas de `tag`.

      Un `tag` partagé fait remplacer la notification précédente par la
      suivante : deux clientes qui réservent à une minute d'intervalle, et
      la première disparaît sans avoir été lue. Chaque événement mérite sa
      ligne.

      Ni `requireInteraction` : il garde la notification à l'écran jusqu'à
      ce qu'on la touche — ce qui, sur un téléphone, revient à prendre
      l'écran en otage. Le système connaît le mode « ne pas déranger ».
    */
    data: {
      lien: donnees.lien,
      liens: Object.fromEntries(actions.map((a) => [a.id, a.lien])),
    },
  };
  if (donnees.image) options.image = donnees.image;
  if (URGENTS.has(donnees.genre)) options.vibrate = [200, 100, 200];

  return self.registration.showNotification(donnees.titre, options);
}

self.addEventListener("notificationclick", (evenement) => {
  evenement.notification.close();

  /*
    Le bouton touché décide de la destination ; un clic sur la notification
    elle-même mène au lien principal.

    Jamais hors du site : un lien absolu vers une autre origine, s'il en
    arrivait un, ramène à l'accueil du tableau de bord plutôt que d'ouvrir
    une page inconnue depuis une alerte qui paraît venir du salon.
  */
  const donnees = evenement.notification.data || {};
  const lien =
    (evenement.action && donnees.liens && donnees.liens[evenement.action]) ||
    donnees.lien ||
    "/";
  let url = new URL(lien, self.location.origin);
  if (url.origin !== self.location.origin) url = new URL("/", self.location.origin);
  const cible = url.href;

  /*
    Réutiliser l'onglet déjà ouvert plutôt que d'en empiler un.

    Une gérante qui reçoit six notifications dans la journée se retrouverait
    avec six onglets du même tableau de bord. On cherche donc une fenêtre de
    cette origine, on l'amène au premier plan et on l'emmène au bon endroit ;
    on n'en ouvre une que s'il n'y en a aucune.
  */
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

/*
 * Prévenir les onglets ouverts.
 *
 * Le panneau de notifications interroge le serveur toutes les trente
 * secondes. C'est assez pour ne rien manquer, mais pas pour donner
 * l'impression que la page est vivante : une gérante qui a le tableau de
 * bord sous les yeux verrait la pastille apparaître avec une demi-minute de
 * retard sur la notification de son téléphone.
 *
 * Le service worker, lui, sait à la seconde. Il le dit aux onglets ouverts,
 * qui rechargent leur liste immédiatement.
 */
async function prevenirLesOnglets() {
  const fenetres = await self.clients.matchAll({
    type: "window",
    includeUncontrolled: true,
  });
  for (const fenetre of fenetres) {
    fenetre.postMessage({ type: "beauty-salon:notification" });
  }
}
