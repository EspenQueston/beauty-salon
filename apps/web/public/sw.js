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
