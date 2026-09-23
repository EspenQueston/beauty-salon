"use client";

/**
 * L'invitation à installer, proposée une fois — pas une bannière.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'on refuse de faire
 * ---------------------------------------------------------------------------
 *
 * Le réflexe est d'afficher un bandeau dès la première seconde. C'est la
 * chose qui fait fermer un onglet : on demande de s'engager à quelqu'un qui
 * ne sait pas encore ce qu'il regarde.
 *
 * L'invitation attend donc un signe d'intérêt — une deuxième visite — et ne
 * se montre qu'une fois. Refusée, elle ne revient pas. On ne peut pas
 * installer deux fois la même chose, et insister ne fait pas changer d'avis.
 *
 * ---------------------------------------------------------------------------
 * Le cas d'iOS
 * ---------------------------------------------------------------------------
 *
 * Safari n'émet pas `beforeinstallprompt` et n'offre aucune API : l'ajout à
 * l'écran d'accueil s'y fait par le menu Partager. On ne peut donc pas
 * l'automatiser — mais on peut l'expliquer, ce que fait la seconde phrase.
 * L'alternative — ne rien montrer sur iPhone — reviendrait à réserver la
 * fonctionnalité à Android, alors que la moitié de la clientèle visée est
 * sur iPhone.
 */

import { useEffect, useState } from "react";

/** L'événement d'Android, absent des types du DOM. */
interface InvitePWA extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const CLE_VISITES = "beauty-salon.visites";
const CLE_REPONSE = "beauty-salon.installation";

function lire(cle: string): string | null {
  try {
    return localStorage.getItem(cle);
  } catch {
    return null;
  }
}

function ecrire(cle: string, valeur: string) {
  try {
    localStorage.setItem(cle, valeur);
  } catch {
    // Sans stockage, on comptera cette visite comme la première à chaque
    // fois — donc on ne proposera jamais rien. C'est le bon échec : on
    // n'insiste pas auprès de quelqu'un qu'on ne peut pas se rappeler.
  }
}

function surIOS(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  // Les iPad récents s'annoncent comme des Mac : le test tactile les
  // rattrape, et un Mac sans écran tactile n'est pas concerné.
  return (
    /iPad|iPhone|iPod/.test(ua) ||
    (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)
  );
}

function dejaInstallee(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    // Le signe propre à iOS, hors norme mais seul disponible.
    (window.navigator as { standalone?: boolean }).standalone === true
  );
}

export function Installer({ nom }: { nom: string }) {
  const [invite, setInvite] = useState<InvitePWA | null>(null);
  const [ios, setIos] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (dejaInstallee() || lire(CLE_REPONSE)) return;

    // Le compteur de visites, avancé une fois par chargement. La deuxième
    // est le premier signe qu'on revient volontairement.
    const visites = Number(lire(CLE_VISITES) ?? "0") + 1;
    ecrire(CLE_VISITES, String(visites));
    if (visites < 2) return;

    /*
      Le délai n'est pas un détour technique, c'est le bon moment.

      Surgir à la seconde où la page s'affiche interrompt quelqu'un qui n'a
      encore rien lu — c'est ce qui fait fermer un onglet. Quelques secondes
      plus tard, la personne a vu de quoi il s'agit, et la proposition
      répond à une question qu'elle commence à se poser.
    */
    const ATTENTE = 5000;

    if (surIOS()) {
      // Pas d'événement à attendre : Safari n'en émet aucun.
      const minuteur = setTimeout(() => {
        setIos(true);
        setVisible(true);
      }, ATTENTE);
      return () => clearTimeout(minuteur);
    }

    let minuteur: ReturnType<typeof setTimeout> | undefined;

    const capter = (evenement: Event) => {
      // Sans cela, Chrome affiche sa propre barre, au moment qu'il choisit.
      evenement.preventDefault();
      setInvite(evenement as InvitePWA);
      minuteur = setTimeout(() => setVisible(true), ATTENTE);
    };

    window.addEventListener("beforeinstallprompt", capter);
    return () => {
      window.removeEventListener("beforeinstallprompt", capter);
      if (minuteur) clearTimeout(minuteur);
    };
  }, []);

  if (!visible) return null;

  function refuser() {
    ecrire(CLE_REPONSE, "refusee");
    setVisible(false);
  }

  async function accepter() {
    if (!invite) return;
    ecrire(CLE_REPONSE, "proposee");
    setVisible(false);
    await invite.prompt();
    // Le verdict ne sert qu'aux journaux : quoi qu'il arrive, on ne
    // reproposera pas.
    await invite.userChoice.catch(() => undefined);
  }

  return (
    <div
      role="dialog"
      aria-label={`Installer ${nom}`}
      /*
        Posé au-dessus de la barre de réservation, pas devant la page.

        Une fenêtre modale au centre bloque la lecture pour une proposition
        dont personne n'a besoin tout de suite. Celle-ci se range en bas,
        au-dessus de la marge système, et se referme d'un geste.
      */
      className="fixed inset-x-3 bottom-3 z-40 rounded-2xl border border-line bg-surface p-4 shadow-float decalage-bas-sur sm:left-auto sm:right-4 sm:w-80"
    >
      <div className="flex items-start gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/icones/192.png"
          alt=""
          width={40}
          height={40}
          className="size-10 shrink-0 rounded-xl"
        />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-ink">Installer {nom}</p>
          <p className="mt-1 text-[0.8rem] leading-relaxed text-muted">
            {ios ? (
              <>
                Touchez <strong>Partager</strong>, puis{" "}
                <strong>Sur l&apos;écran d&apos;accueil</strong>. Vous
                l&apos;ouvrirez ensuite comme une application.
              </>
            ) : (
              "Un accès direct depuis votre écran d'accueil, et vos pages restent lisibles même sans réseau."
            )}
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap justify-end gap-2">
        <button
          type="button"
          onClick={refuser}
          className="rounded-full px-3 py-1.5 text-sm font-medium text-muted transition hover:text-ink"
        >
          {ios ? "J'ai compris" : "Plus tard"}
        </button>
        {!ios && (
          <button
            type="button"
            onClick={accepter}
            className="rounded-full bg-ink px-4 py-1.5 text-sm font-semibold text-bg transition hover:opacity-90"
          >
            Installer
          </button>
        )}
      </div>
    </div>
  );
}
