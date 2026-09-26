"use client";

/**
 * L'accès du salon, partagé par toute la coquille du tableau de bord.
 *
 * Trois choses le lisent : le bandeau en tête des écrans, le bouton
 * « Passer à l'annuel » de la barre du haut, et la page Abonnement. Un seul
 * chargement pour les trois, et une seule vérité : ils ne peuvent pas se
 * contredire.
 *
 * ---------------------------------------------------------------------------
 * Vivant
 * ---------------------------------------------------------------------------
 *
 * L'accès se relit au retour sur l'onglet, toutes les cinq minutes, et dès
 * qu'un événement le signale (un 402 reçu par n'importe quel écran, un
 * paiement déclaré). Le compte à rebours avance chaque minute sans requête.
 *
 * ---------------------------------------------------------------------------
 * Le bandeau
 * ---------------------------------------------------------------------------
 *
 * Il ne parle que lorsqu'il y a quelque chose à faire : fin d'essai ou de
 * période dans les cinq jours, délai de grâce, accès fermé. Toute l'équipe
 * le voit — c'est lui qui explique à une prestataire pourquoi un
 * enregistrement est refusé — mais seul le propriétaire reçoit le lien vers
 * le règlement.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import Link from "next/link";

import { dashboardFetch } from "@/lib/dashboard";
import {
  ABONNEMENT_CHANGE,
  dateLongue,
  joursAvant,
  type AccesSalon,
} from "./abonnement";
import { Icon } from "./icons";

const RELECTURE_MS = 5 * 60_000;
const HORLOGE_MS = 60_000;
const ALERTE_JOURS = 5;

interface AccesContexte {
  acces: AccesSalon | null;
  maintenant: number;
  relire: () => void;
}

const Contexte = createContext<AccesContexte>({
  acces: null,
  maintenant: 0,
  relire: () => undefined,
});

export function useAcces(): AccesContexte {
  return useContext(Contexte);
}

export function AccesProvider({
  tenantId,
  children,
}: {
  tenantId: string;
  children: ReactNode;
}) {
  const [acces, setAcces] = useState<AccesSalon | null>(null);
  const [maintenant, setMaintenant] = useState(() => Date.now());
  const [token, setToken] = useState(0);
  const relire = useCallback(() => setToken((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    dashboardFetch<AccesSalon>("/api/v1/subscription/acces", {}, tenantId)
      .then((data) => {
        if (cancelled) return;
        setAcces(data);
        setMaintenant(Date.now());
      })
      // Muet plutôt qu'une erreur de plus : les écrans disent déjà ce qui
      // ne se charge pas, et un bandeau absent ne bloque rien.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [tenantId, token]);

  useEffect(() => {
    const auRetour = () => {
      if (document.visibilityState === "visible") relire();
    };
    window.addEventListener(ABONNEMENT_CHANGE, relire);
    document.addEventListener("visibilitychange", auRetour);
    const relecture = window.setInterval(relire, RELECTURE_MS);
    const horloge = window.setInterval(() => setMaintenant(Date.now()), HORLOGE_MS);
    return () => {
      window.removeEventListener(ABONNEMENT_CHANGE, relire);
      document.removeEventListener("visibilitychange", auRetour);
      window.clearInterval(relecture);
      window.clearInterval(horloge);
    };
  }, [relire]);

  return (
    <Contexte.Provider value={{ acces, maintenant, relire }}>
      {children}
    </Contexte.Provider>
  );
}

// ---------------------------------------------------------------------------
// Le bouton de la barre du haut
// ---------------------------------------------------------------------------

/**
 * « Choisir une offre », « Passer à l'annuel », « Régler » : l'action du
 * moment, toujours visible, jamais là quand il n'y a rien à faire (offre
 * annuelle en cours, salon suspendu, membre qui ne paie pas). Au mensuel,
 * l'annuel d'abord — l'économie est immédiate ; à l'annuel Standard, Pro.
 */
export function UpgradeButton() {
  const { acces, maintenant } = useAcces();
  if (!acces || !acces.peut_payer) return null;

  const jours = joursAvant(acces.fin_periode, maintenant);
  let libelle = "";
  let pastille = "";
  let ton: "marque" | "alerte" | "neutre" = "marque";

  if (acces.paiement_en_attente) {
    libelle = "Paiement en vérification";
    ton = "neutre";
  } else if (acces.raison === "expire" || acces.raison === "grace") {
    libelle = acces.raison === "expire" ? "Réactiver mon salon" : "Régler l'abonnement";
    ton = "alerte";
  } else if (acces.raison === "essai") {
    libelle = "Choisir une offre";
    pastille = jours <= 1 ? "dernier jour" : `${jours} j`;
  } else if (acces.raison === "periode" && acces.montee_en_gamme) {
    libelle = "Passer à l'annuel";
    pastille = `−${acces.montee_en_gamme.economie.pourcentage} %`;
  } else if (acces.raison === "periode" && acces.pro_disponible) {
    libelle = "Passer à Pro";
    pastille = "Pro";
  } else {
    return null;
  }

  const styles = {
    marque: "salon-gradient text-white shadow-sm hover:brightness-110",
    alerte: "bg-danger text-white shadow-sm hover:brightness-110",
    neutre: "border border-line bg-surface text-ink hover:bg-surface-hover",
  }[ton];

  return (
    <Link
      href="/abonnement#offres"
      title={libelle}
      className={`group inline-flex shrink-0 items-center gap-2 rounded-full py-1.5 pl-2 pr-2 text-sm font-semibold transition sm:pl-3 sm:pr-1.5 ${styles}`}
    >
      <Icon
        name={ton === "neutre" ? "clock" : "sparkles"}
        className="size-4 transition-transform group-hover:scale-110"
      />
      <span className="hidden sm:inline">{libelle}</span>
      <span className="sr-only sm:hidden">{libelle}</span>
      {pastille && (
        <span
          className={`hidden rounded-full px-2 py-0.5 text-[11px] font-bold sm:inline ${
            ton === "marque" ? "bg-white/20" : "bg-surface-muted"
          }`}
        >
          {pastille}
        </span>
      )}
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Le bandeau
// ---------------------------------------------------------------------------

type Ton = "info" | "warning" | "danger";

const TONS: Record<Ton, string> = {
  info: "bg-info-bg text-info",
  warning: "bg-warning-bg text-warning",
  danger: "bg-danger-bg text-danger",
};

export function AccessBanner({ pathname }: { pathname: string }) {
  const { acces, maintenant } = useAcces();

  // La page Abonnement dit tout cela en plus grand.
  if (!acces || pathname.endsWith("/abonnement")) return null;

  const message = messageDe(acces, maintenant);
  if (!message) return null;

  return (
    <div className={`border-b border-line px-4 py-2 sm:px-6 sm:py-2.5 lg:px-8 ${TONS[message.ton]}`}>
      <div className="mx-auto flex max-w-6xl items-center gap-x-3 text-[13px] sm:text-sm">
        <p className="flex min-w-0 flex-1 items-start gap-2">
          <Icon
            name={message.ton === "info" ? "clock" : "receipt"}
            className="mt-0.5 size-4 shrink-0"
          />
          <span className="line-clamp-2 sm:line-clamp-none">{message.texte}</span>
        </p>
        {acces.peut_payer ? (
          <Link
            href="/abonnement#offres"
            className="shrink-0 rounded-lg bg-surface px-2.5 py-1.5 text-xs font-semibold text-ink shadow-sm transition hover:bg-surface-hover sm:px-3 sm:text-sm"
          >
            {message.action}
          </Link>
        ) : (
          <span className="hidden shrink-0 text-xs opacity-90 sm:inline">
            Prévenez le propriétaire du salon.
          </span>
        )}
      </div>
    </div>
  );
}

function messageDe(
  acces: AccesSalon,
  maintenant: number,
): { ton: Ton; texte: string; action: string } | null {
  const fin = acces.fin_periode ? dateLongue.format(new Date(acces.fin_periode)) : "";
  const limite = acces.jusqu_au ? dateLongue.format(new Date(acces.jusqu_au)) : "";
  const jours = joursAvant(acces.fin_periode, maintenant);

  if (acces.raison === "suspendu") {
    return {
      ton: "danger",
      texte:
        "Abonnement suspendu : réservations en ligne fermées, tableau de bord en lecture seule. Contactez l'équipe Beauty Salon.",
      action: "Voir",
    };
  }
  if (acces.raison === "resilie") {
    return {
      ton: "danger",
      texte: "Abonnement résilié : le tableau de bord est en lecture seule.",
      action: "Voir",
    };
  }
  if (acces.paiement_en_attente && (acces.raison === "expire" || acces.raison === "grace")) {
    return {
      ton: "info",
      texte:
        acces.raison === "expire"
          ? "Paiement reçu, en cours de vérification. Tout se rouvre dès sa validation."
          : "Paiement reçu, en cours de vérification.",
      action: "Suivre",
    };
  }
  if (acces.raison === "expire") {
    return {
      ton: "danger",
      texte:
        "Abonnement expiré : réservations en ligne fermées, tableau de bord en lecture seule. Vos données sont intactes.",
      action: "Réactiver",
    };
  }
  if (acces.raison === "grace") {
    return {
      ton: "warning",
      texte: `Votre période s'est terminée le ${fin}. Réglez avant le ${limite} pour garder les réservations ouvertes.`,
      action: "Régler",
    };
  }
  if (acces.paiement_en_attente) return null;
  if (acces.raison === "essai" && jours <= ALERTE_JOURS) {
    return {
      ton: "info",
      texte:
        jours <= 1
          ? `Votre essai gratuit se termine le ${fin}.`
          : `Votre essai gratuit se termine dans ${jours} jours, le ${fin}.`,
      action: "Choisir une offre",
    };
  }
  if (acces.raison === "periode" && jours <= ALERTE_JOURS) {
    return {
      ton: "warning",
      texte: `Votre abonnement se termine le ${fin}.`,
      action: "Prolonger",
    };
  }
  return null;
}
