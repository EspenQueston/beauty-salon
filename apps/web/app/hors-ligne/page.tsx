import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Hors ligne",
  // Elle ne doit jamais apparaître dans un moteur de recherche : c'est une
  // page de secours, pas une page du site.
  robots: { index: false, follow: false },
};

/**
 * Ce qu'on voit quand le réseau a disparu.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'elle dit, et ce qu'elle ne dit pas
 * ---------------------------------------------------------------------------
 *
 * Elle ne s'excuse pas et ne parle pas de « service worker ». Elle répond aux
 * deux questions qu'on se pose vraiment à ce moment-là : est-ce que ça vient
 * de moi, et qu'est-ce que je fais maintenant.
 *
 * Elle ne promet rien non plus. Dire « vos pages restent consultables » alors
 * que cette visiteuse n'a peut-être ouvert qu'une seule page ferait chercher
 * un contenu qui n'existe pas.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi elle est entièrement statique
 * ---------------------------------------------------------------------------
 *
 * Elle est mise de côté par le service worker à son installation, et servie
 * depuis le cache alors qu'il n'y a plus de réseau. Le moindre appel — une
 * police distante, une image, une lecture d'API — la ferait s'afficher à
 * moitié, exactement dans la situation où elle doit être irréprochable.
 */
export default function HorsLignePage() {
  return (
    <main className="mx-auto flex min-h-svh max-w-md flex-col items-center justify-center px-6 text-center">
      <span
        aria-hidden
        className="flex size-14 items-center justify-center rounded-2xl bg-surface-muted text-2xl"
      >
        {/* Un glyphe, pas une image : il s'affiche sans rien télécharger. */}
        ⌁
      </span>

      <h1 className="mt-5 text-xl font-semibold text-ink">
        Pas de connexion
      </h1>

      <p className="mt-2 text-sm leading-relaxed text-muted">
        Votre téléphone n&apos;arrive pas à joindre le réseau. Les pages que
        vous avez déjà ouvertes restent consultables ; les autres reviendront
        dès que la connexion sera rétablie.
      </p>

      {/*
        Un rechargement, et rien d'autre.

        `<a>` plutôt qu'un bouton avec du JavaScript : si le script de la
        page n'a pas pu se charger — ce qui est le cas le plus probable
        ici —, un bouton ne ferait rien du tout, et l'on aurait donné à
        cliquer sur du vide.
      */}
      {/* eslint-disable-next-line @next/next/no-html-link-for-pages --
          `<Link>` ferait une navigation côté client : sans réseau elle
          échoue et l'on reste sur cette page, bouton qui ne fait rien à
          l'appui. Un `<a>` recharge tout, ce qui est exactement le sens de
          « réessayer » — et fonctionne même si le script n'a pas pu se
          charger. */}
      <a
        href="/"
        className="mt-6 inline-flex items-center justify-center rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-bg transition hover:opacity-90"
      >
        Réessayer
      </a>
    </main>
  );
}
