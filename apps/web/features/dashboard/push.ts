"use client";

/**
 * L'abonnement de cet appareil aux notifications.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'il faut réunir pour qu'une notification arrive
 * ---------------------------------------------------------------------------
 *
 * Quatre conditions, et il suffit qu'une seule manque pour que rien
 * n'arrive — sans le moindre message d'erreur. C'est ce qui rend cette
 * fonctionnalité pénible à diagnostiquer, et c'est pourquoi chaque échec
 * est nommé ici plutôt que renvoyé sous forme de `false` :
 *
 *   1. le navigateur sait faire (`PushManager`) — pas Safari sur macOS avant
 *      16.4, pas un navigateur d'application intégrée ;
 *   2. la page est en contexte sûr : HTTPS, ou `localhost` ;
 *   3. un service worker est installé, c'est lui qui recevra le message ;
 *   4. la personne a accordé la permission, et ne l'a pas refusée une fois
 *      pour toutes — un refus est définitif tant qu'elle ne le change pas
 *      elle-même dans les réglages du navigateur.
 *
 * ---------------------------------------------------------------------------
 * Le cas de l'iPhone
 * ---------------------------------------------------------------------------
 *
 * Safari sur iOS n'expose `PushManager` que lorsque le site a été **ajouté à
 * l'écran d'accueil**. Ouvert dans un onglet, il n'y a rien à demander : la
 * permission n'existe pas. On le dit, plutôt que de laisser un bouton qui ne
 * fait rien.
 */

import { dashboardFetch } from "@/lib/dashboard";

export type Portee = "salon" | "plateforme";

/**
 * Marque d'adhésion, lue par `app/ServiceWorker.tsx`.
 *
 * En développement, le service worker est retiré à chaque chargement : un
 * cache qui traîne pendant qu'on code fait perdre des heures. Mais sans
 * service worker, il n'y a pas de push — et la fonctionnalité deviendrait
 * invérifiable ailleurs qu'en production, c'est-à-dire trop tard.
 *
 * Cette clé est le compromis : qui a demandé les notifications garde son
 * service worker, y compris en développement. Les autres n'en ont pas.
 */
export const CLE_OPTIN = "beauty-salon.push-actif";

export type EtatPush =
  | "pret" // abonné sur cet appareil
  | "possible" // tout est réuni, il reste à demander
  | "refuse" // permission refusée : seuls les réglages du navigateur la rendent
  | "non-installe" // iOS hors écran d'accueil
  | "incompatible" // navigateur ou contexte non sûr
  | "desactive"; // le serveur n'a pas de clés VAPID

interface EtatServeur {
  actif: boolean;
  cle: string;
  appareils: {
    id: string;
    endpoint: string;
    appareil: string;
    portee: string;
    depuis: string;
  }[];
}

/**
 * La clé VAPID arrive en base64url ; `subscribe` veut des octets.
 *
 * Le tableau est alloué puis rempli, plutôt que construit par
 * `Uint8Array.from` : ce dernier produit un `Uint8Array<ArrayBufferLike>`,
 * que `applicationServerKey` refuse — il exige une vue sur un `ArrayBuffer`
 * et non sur une mémoire potentiellement partagée.
 */
function versOctets(base64url: string): Uint8Array<ArrayBuffer> {
  const bourrage = "=".repeat((4 - (base64url.length % 4)) % 4);
  const base64 = (base64url + bourrage).replace(/-/g, "+").replace(/_/g, "/");
  const brut = atob(base64);

  const octets = new Uint8Array(brut.length);
  for (let index = 0; index < brut.length; index += 1) {
    octets[index] = brut.charCodeAt(index);
  }
  return octets;
}

function surIOS(): boolean {
  const ua = navigator.userAgent;
  return (
    /iPad|iPhone|iPod/.test(ua) ||
    (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)
  );
}

function installee(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (window.navigator as { standalone?: boolean }).standalone === true
  );
}

/**
 * Un nom d'appareil qu'on puisse reconnaître dans une liste.
 *
 * « Chrome sur Android » se relit six mois plus tard ; une chaîne d'agent
 * utilisateur de deux cents caractères, non. C'est le seul moyen de savoir
 * lequel révoquer quand on change de téléphone.
 */
function nomAppareil(): string {
  const ua = navigator.userAgent;

  const systeme = /Android/.test(ua)
    ? "Android"
    : /iPhone|iPad|iPod/.test(ua)
      ? "iPhone"
      : /Windows/.test(ua)
        ? "Windows"
        : /Mac OS X/.test(ua)
          ? "Mac"
          : /Linux/.test(ua)
            ? "Linux"
            : "";

  // L'ordre compte : Edge et Opera se déclarent aussi « Chrome », et Chrome
  // se déclare aussi « Safari ». Le premier qui correspond gagne.
  const navigateur = /Edg\//.test(ua)
    ? "Edge"
    : /OPR\//.test(ua)
      ? "Opera"
      : /SamsungBrowser/.test(ua)
        ? "Samsung Internet"
        : /Chrome\//.test(ua)
          ? "Chrome"
          : /Firefox\//.test(ua)
            ? "Firefox"
            : /Safari\//.test(ua)
              ? "Safari"
              : "Navigateur";

  return systeme ? `${navigateur} sur ${systeme}` : navigateur;
}

/** Le service worker, enregistré si besoin. */
async function serviceWorker(): Promise<ServiceWorkerRegistration> {
  const existant = await navigator.serviceWorker.getRegistration("/");
  if (existant) return navigator.serviceWorker.ready;

  await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  return navigator.serviceWorker.ready;
}

/**
 * Où en est cet appareil, sans rien demander à personne.
 *
 * Ne déclenche **jamais** la demande de permission : cette fonction est
 * appelée à l'ouverture du panneau, et une fenêtre système qui surgit sans
 * qu'on ait cliqué est ce qui fait refuser définitivement.
 */
export async function etatPush(tenantId?: string): Promise<EtatPush> {
  if (typeof window === "undefined") return "incompatible";

  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    // Sur iPhone, l'absence de PushManager signifie presque toujours « pas
    // encore ajouté à l'écran d'accueil » — une situation qui se règle,
    // contrairement à un navigateur trop ancien.
    return surIOS() && !installee() ? "non-installe" : "incompatible";
  }

  let serveur: EtatServeur;
  try {
    serveur = await dashboardFetch<EtatServeur>("/api/v1/push", {}, tenantId);
  } catch {
    return "incompatible";
  }
  if (!serveur.actif) return "desactive";

  if (Notification.permission === "denied") return "refuse";

  const enregistrement = await navigator.serviceWorker.getRegistration("/");
  const abonnement = await enregistrement?.pushManager.getSubscription();

  /*
    Abonné côté navigateur **et** connu du serveur, sur la même adresse.

    Les deux, parce qu'une base restaurée, un compte changé ou un retrait
    fait ailleurs laissent un abonnement local orphelin : le navigateur se
    croirait inscrit et ne recevrait jamais rien, sans jamais rien signaler.

    Comparer les adresses et non se contenter de « ce compte a un appareil » :
    la gérante en a souvent trois, et celui qu'elle tient en main peut très
    bien être le seul à manquer.
  */
  if (abonnement) {
    const connu = serveur.appareils.some(
      (appareil) => appareil.endpoint === abonnement.endpoint,
    );
    if (connu) return "pret";
  }

  return "possible";
}

/**
 * Demande la permission et inscrit cet appareil.
 *
 * À n'appeler que depuis un clic. Les navigateurs refusent la demande hors
 * d'un geste de l'utilisateur, et l'appeler au chargement ferait refuser par
 * réflexe — un refus qu'on ne peut plus rattraper depuis la page.
 */
export async function activerPush(
  portee: Portee = "salon",
  tenantId?: string,
): Promise<EtatPush> {
  const etat = await etatPush(tenantId);
  if (etat !== "possible" && etat !== "pret") return etat;

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    return permission === "denied" ? "refuse" : "possible";
  }

  // Posée avant l'enregistrement : c'est elle qui empêche le nettoyage de
  // développement de retirer le service worker au prochain chargement.
  try {
    localStorage.setItem(CLE_OPTIN, "1");
  } catch {
    // Stockage refusé (navigation privée) : le service worker sera retiré au
    // prochain chargement en développement. Sans effet en production.
  }

  const enregistrement = await serviceWorker();
  const serveur = await dashboardFetch<EtatServeur>("/api/v1/push", {}, tenantId);
  if (!serveur.actif) return "desactive";

  /*
    Réutiliser l'abonnement existant s'il correspond à la clé courante.

    `subscribe()` échoue avec un abonnement déjà posé sous une **autre** clé
    serveur — ce qui arrive après une régénération des clés VAPID. On retire
    alors l'ancien plutôt que de laisser l'appareil dans un état où il ne
    recevra plus jamais rien.
  */
  const cle = versOctets(serveur.cle);
  let abonnement = await enregistrement.pushManager.getSubscription();
  if (abonnement) {
    const memeCle = comparer(abonnement.options.applicationServerKey, cle);
    if (!memeCle) {
      await abonnement.unsubscribe();
      abonnement = null;
    }
  }

  if (!abonnement) {
    abonnement = await enregistrement.pushManager.subscribe({
      // Obligatoire, et c'est un engagement : chaque message reçu doit
      // produire une notification visible. Un service worker qui l'omet se
      // voit retirer le droit d'en recevoir.
      userVisibleOnly: true,
      applicationServerKey: cle,
    });
  }

  const brut = abonnement.toJSON() as {
    endpoint: string;
    keys: { p256dh: string; auth: string };
  };

  await dashboardFetch(
    "/api/v1/push",
    {
      method: "POST",
      body: JSON.stringify({
        endpoint: brut.endpoint,
        cle_p256dh: brut.keys.p256dh,
        cle_auth: brut.keys.auth,
        appareil: nomAppareil(),
        portee,
      }),
    },
    tenantId,
  );

  return "pret";
}

/** Retire cet appareil, des deux côtés. */
export async function desactiverPush(tenantId?: string): Promise<void> {
  try {
    localStorage.removeItem(CLE_OPTIN);
  } catch {
    // Sans conséquence : le retrait ci-dessous est ce qui compte.
  }

  const enregistrement = await navigator.serviceWorker.getRegistration("/");
  const abonnement = await enregistrement?.pushManager.getSubscription();
  if (!abonnement) return;

  const endpoint = abonnement.endpoint;

  // Le serveur d'abord : si l'on commence par le navigateur et que l'appel
  // échoue, la ligne reste en base et le serveur continuera d'écrire dans
  // une boîte que plus personne ne relève.
  await dashboardFetch(
    "/api/v1/push",
    { method: "DELETE", body: JSON.stringify({ endpoint }) },
    tenantId,
  ).catch(() => undefined);

  await abonnement.unsubscribe();
}

function comparer(a: ArrayBuffer | null, b: Uint8Array): boolean {
  if (!a) return false;
  const gauche = new Uint8Array(a);
  if (gauche.length !== b.length) return false;
  return gauche.every((octet, index) => octet === b[index]);
}
