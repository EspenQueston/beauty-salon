"use client";

/**
 * « Connectée ou pas ? », pour l'icône du compte dans la barre du mini-site.
 *
 * L'icône était la même dans les deux cas : une cliente connectée ne savait
 * pas qu'elle l'était, une autre croyait l'être. La barre lit donc la
 * session au chargement — une requête légère, qui répond 200 aussi aux
 * visiteuses anonymes — puis à chaque fois que l'espace cliente signale un
 * changement (connexion, déconnexion) par `EVENEMENT_SESSION`.
 */

import { useEffect, useState } from "react";

import { api } from "./api";

export const EVENEMENT_SESSION = "espace-cliente:session";

export type EtatSession =
  | { etat: "inconnu" }
  | { etat: "anonyme" }
  | { etat: "connectee"; nom: string; email: string };

interface Reponse {
  connecte?: boolean;
  email?: string;
  display_name?: string;
  is_client?: boolean;
  client?: { full_name?: string } | null;
}

export function useSessionCliente(host: string): EtatSession {
  const [session, setSession] = useState<EtatSession>({ etat: "inconnu" });

  useEffect(() => {
    let annule = false;
    const lire = () => {
      api<Reponse>("/api/v1/public/client/session", host)
        .then((reponse) => {
          if (annule) return;
          // Un compte d'équipe connecté n'a pas d'espace cliente : l'icône
          // reste celle d'une visiteuse, la porte mène à la connexion.
          if (reponse.connecte === false || !reponse.email || !reponse.is_client) {
            setSession({ etat: "anonyme" });
            return;
          }
          setSession({
            etat: "connectee",
            nom: reponse.client?.full_name || reponse.display_name || "",
            email: reponse.email,
          });
        })
        .catch(() => !annule && setSession({ etat: "anonyme" }));
    };
    lire();
    window.addEventListener(EVENEMENT_SESSION, lire);
    return () => {
      annule = true;
      window.removeEventListener(EVENEMENT_SESSION, lire);
    };
  }, [host]);

  return session;
}
