"use client";

/**
 * La cloche, et ce qu'elle ouvre.
 *
 * ===========================================================================
 * Deux choses très différentes, dans un seul panneau
 * ===========================================================================
 *
 * En haut, **ce qui attend un geste** : les acomptes à vérifier, les demandes
 * à accepter, les créneaux passés sans rien de noté. Ce sont des *états* —
 * ils ne disparaissent pas parce qu'on les a lus, seulement parce qu'on les a
 * traités. C'est ce que comptait déjà l'ancienne pastille.
 *
 * En dessous, **ce qui est arrivé** : le fil des événements, qu'on lit et
 * qu'on oublie.
 *
 * Les mélanger dans une seule liste rendrait les deux illisibles : on ne
 * saurait plus si une ligne demande quelque chose ou raconte quelque chose.
 * Les séparer, c'est répondre à deux questions distinctes — « qu'est-ce que
 * je dois faire » et « qu'est-ce que j'ai manqué ».
 *
 * ===========================================================================
 * Ce que compte la pastille
 * ===========================================================================
 *
 * Les deux : ce qui attend **et** ce qui n'a pas été lu. Une pastille qui
 * ignorerait l'un des deux ferait manquer l'autre, et une pastille qu'on
 * apprend à ignorer ne sert plus à rien.
 *
 * ===========================================================================
 * Pourquoi aucun `text-subtle` ici
 * ===========================================================================
 *
 * Mesuré : `--ui-text-subtle` donne 2,79:1 en mode clair et 3,86:1 en mode
 * sombre sur la surface des cartes. C'est en dessous du seuil de lisibilité,
 * et ce panneau ne contient que des textes courts qu'on lit en diagonale —
 * exactement ceux qui pardonnent le moins un contraste faible.
 *
 * `--ui-text-muted` passe (5,26 et 7,0) et garde la hiérarchie. Le jeton
 * `subtle` sert ailleurs dans l'application, c'est un sujet à part.
 *
 * ===========================================================================
 * Vivante, sans épuiser la batterie
 * ===========================================================================
 *
 * Trois sources de fraîcheur, par ordre de rapidité :
 *
 *   1. le service worker, qui prévient à la seconde quand un push arrive —
 *      même si l'onglet est en arrière-plan ;
 *   2. le retour sur l'onglet, qui recharge immédiatement ;
 *   3. un rappel toutes les trente secondes, **suspendu** dès que l'onglet
 *      n'est plus visible. Un tableau de bord oublié dans un onglet ne doit
 *      pas réveiller un téléphone toute la journée.
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import { useNow } from "@/lib/useNow";

import { Icon, type IconName } from "./icons";
import { activerPush, desactiverPush, etatPush, type EtatPush } from "./push";

const RAFRAICHISSEMENT = 30_000;

interface Ligne {
  id: string;
  genre: string;
  titre: string;
  corps: string;
  lien: string;
  lue: boolean;
  created_at: string;
}

interface Boite {
  non_lues: number;
  resultats: Ligne[];
  push_actif: boolean;
}

interface Attention {
  deposits: number;
  requests: number;
  overdue: number;
}

/**
 * Le genre décide de l'icône et de la couleur.
 *
 * Trois teintes seulement, et elles veulent dire quelque chose : l'ambre
 * réclame un geste, l'émeraude annonce une bonne nouvelle, le gris raconte.
 * Une palette par genre aurait fait un sapin de Noël où plus rien ne
 * ressort.
 */
const GENRES: Record<
  string,
  { icone: IconName; ton: "agir" | "bon" | "neutre" }
> = {
  reservation: { icone: "calendar", ton: "bon" },
  acompte_a_verifier: { icone: "wallet", ton: "agir" },
  acompte_expire: { icone: "clock", ton: "neutre" },
  annulation: { icone: "close", ton: "agir" },
  avis: { icone: "star", ton: "bon" },
  liste_attente: { icone: "users", ton: "neutre" },
  salon_inscrit: { icone: "sparkles", ton: "bon" },
  facture: { icone: "receipt", ton: "agir" },
  incident: { icone: "bolt", ton: "agir" },
};

const TONS = {
  agir: "bg-warning-bg text-warning",
  bon: "bg-success-bg text-success",
  neutre: "bg-surface-muted text-muted",
} as const;

/** « il y a 5 min », « hier », « le 12/09 ». */
function depuis(iso: string, maintenant: number): string {
  const quand = new Date(iso).getTime();
  if (!maintenant || Number.isNaN(quand)) return "";

  const minutes = Math.max(0, Math.round((maintenant - quand) / 60_000));
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;

  const heures = Math.round(minutes / 60);
  if (heures < 24) return `il y a ${heures} h`;
  if (heures < 48) return "hier";

  return new Date(iso).toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
  });
}

export function Notifications({ tenantId }: { tenantId: string }) {
  const [ouvert, setOuvert] = useState(false);
  const [boite, setBoite] = useState<Boite | null>(null);
  const [attention, setAttention] = useState<Attention | null>(null);
  const [push, setPush] = useState<EtatPush | null>(null);
  const [occupe, setOccupe] = useState(false);
  const panneau = useRef<HTMLDivElement>(null);
  const bouton = useRef<HTMLButtonElement>(null);
  const maintenant = useNow();

  const charger = useCallback(() => {
    dashboardFetch<Boite>("/api/v1/notifications", {}, tenantId)
      .then(setBoite)
      .catch(() => undefined);
    dashboardFetch<{ attention: Attention }>(
      "/api/v1/overview?brief=1",
      {},
      tenantId,
    )
      .then((reponse) => setAttention(reponse.attention))
      .catch(() => undefined);
  }, [tenantId]);

  // Premier chargement, puis rappel tant que l'onglet est visible.
  useEffect(() => {
    charger();

    let minuteur: ReturnType<typeof setInterval> | null = null;

    const battre = () => {
      if (minuteur) clearInterval(minuteur);
      // `document.hidden` plutôt qu'un simple intervalle : un onglet laissé
      // ouvert toute la journée interrogerait le serveur mille fois pour
      // personne, et viderait la batterie d'un téléphone posé sur le comptoir.
      if (document.hidden) return;
      minuteur = setInterval(charger, RAFRAICHISSEMENT);
    };

    const auRetour = () => {
      if (!document.hidden) charger();
      battre();
    };

    // Le service worker prévient à la seconde ; l'intervalle n'est qu'un
    // filet pour les cas où le push n'arrive pas.
    const duServiceWorker = (evenement: MessageEvent) => {
      if (evenement.data?.type === "beauty-salon:notification") charger();
    };

    battre();
    document.addEventListener("visibilitychange", auRetour);
    window.addEventListener("focus", charger);
    navigator.serviceWorker?.addEventListener("message", duServiceWorker);

    return () => {
      if (minuteur) clearInterval(minuteur);
      document.removeEventListener("visibilitychange", auRetour);
      window.removeEventListener("focus", charger);
      navigator.serviceWorker?.removeEventListener("message", duServiceWorker);
    };
  }, [charger]);

  // L'état du push n'est lu qu'à l'ouverture : il coûte un appel réseau et
  // une lecture du service worker, inutiles tant que le panneau est fermé.
  useEffect(() => {
    if (!ouvert) return;
    let annule = false;
    etatPush(tenantId)
      .then((etat) => {
        if (!annule) setPush(etat);
      })
      .catch(() => undefined);
    return () => {
      annule = true;
    };
  }, [ouvert, tenantId]);

  // Fermer : un clic ailleurs, ou Échap.
  useEffect(() => {
    if (!ouvert) return;

    const dehors = (evenement: MouseEvent) => {
      const cible = evenement.target as Node;
      if (panneau.current?.contains(cible) || bouton.current?.contains(cible)) {
        return;
      }
      setOuvert(false);
    };
    const echap = (evenement: KeyboardEvent) => {
      if (evenement.key !== "Escape") return;
      setOuvert(false);
      // Le focus revient sur la cloche : sans cela, il repart au début de la
      // page et la navigation au clavier redémarre de zéro.
      bouton.current?.focus();
    };

    document.addEventListener("mousedown", dehors);
    document.addEventListener("keydown", echap);
    return () => {
      document.removeEventListener("mousedown", dehors);
      document.removeEventListener("keydown", echap);
    };
  }, [ouvert]);

  const enAttente = attention
    ? attention.deposits + attention.requests + attention.overdue
    : 0;
  const nonLues = boite?.non_lues ?? 0;
  const pastille = enAttente + nonLues;

  function marquerTout() {
    if (!nonLues) return;
    // L'affichage change tout de suite : attendre la réponse du serveur pour
    // éteindre une pastille qu'on vient de vider donne une impression de
    // lourdeur sur un réseau lent.
    setBoite((ancien) =>
      ancien
        ? {
            ...ancien,
            non_lues: 0,
            resultats: ancien.resultats.map((l) => ({ ...l, lue: true })),
          }
        : ancien,
    );
    dashboardFetch(
      "/api/v1/notifications",
      {
        method: "POST",
        body: JSON.stringify({ toutes: true }),
      },
      tenantId,
    ).catch(charger);
  }

  function marquer(ligne: Ligne) {
    if (ligne.lue) return;
    setBoite((ancien) =>
      ancien
        ? {
            ...ancien,
            non_lues: Math.max(0, ancien.non_lues - 1),
            resultats: ancien.resultats.map((l) =>
              l.id === ligne.id ? { ...l, lue: true } : l,
            ),
          }
        : ancien,
    );
    dashboardFetch(
      "/api/v1/notifications",
      {
        method: "POST",
        body: JSON.stringify({ ids: [ligne.id] }),
      },
      tenantId,
    ).catch(charger);
  }

  async function basculerPush() {
    setOccupe(true);
    try {
      if (push === "pret") {
        await desactiverPush(tenantId);
        setPush("possible");
      } else {
        setPush(await activerPush("salon", tenantId));
      }
    } catch {
      // Permission refusée au dernier moment, service worker rejeté, réseau
      // coupé : on ne sait pas laquelle, et la personne n'y peut rien de
      // plus. On dit que ça n'a pas marché, sans inventer de raison.
      setPush("incompatible");
    } finally {
      setOccupe(false);
    }
  }

  return (
    <div className="relative">
      <button
        ref={bouton}
        type="button"
        onClick={() => setOuvert((valeur) => !valeur)}
        aria-expanded={ouvert}
        aria-haspopup="dialog"
        aria-label={
          pastille > 0
            ? `Notifications, ${pastille} en attente`
            : "Notifications"
        }
        className="relative rounded-lg p-2 text-muted transition hover:bg-surface-hover hover:text-ink aria-expanded:bg-surface-hover aria-expanded:text-ink"
      >
        <Icon name="bell" className="size-5" />
        {pastille > 0 && (
          /*
            Un rouge fixe, et non `bg-danger`.

            En mode sombre, `--ui-danger` s'éclaircit jusqu'à #fb7185 — ce qui
            est juste pour du texte rouge sur fond sombre, et faux ici : le
            chiffre est blanc et posé **dessus**, où il tombait à 2,69:1.
            L'ancienne cloche portait déjà ce défaut.

            Cette pastille n'appartient pas au thème, c'est un signal : elle
            garde la même couleur dans les deux modes, celle de `--ui-danger`
            en mode clair. Le blanc y est à 6,57:1.
          */
          <span className="tabular absolute -right-0.5 -top-0.5 flex min-w-[1.15rem] items-center justify-center rounded-full bg-[#b42318] px-1 text-[0.65rem] font-semibold leading-[1.15rem] text-white">
            {pastille > 9 ? "9+" : pastille}
          </span>
        )}
      </button>

      {ouvert && (
        <>
          {/*
            Le voile n'existe que sur téléphone.

            Sur grand écran, le panneau se ferme d'un clic ailleurs et
            assombrir la page derrière serait dramatiser une liste. Sur
            téléphone il occupe presque tout l'écran : sans voile, on ne sait
            plus s'il flotte au-dessus ou s'il a remplacé la page.
          */}
          <div
            aria-hidden
            onClick={() => setOuvert(false)}
            className="fixed inset-0 z-30 bg-black/30 sm:hidden"
          />

          <div
            ref={panneau}
            role="dialog"
            aria-label="Notifications"
            /*
              Téléphone : une feuille ancrée en bas. Grand écran : un panneau
              accroché à la cloche.

              Un menu déroulant de 23 rem sur un écran de 360 px déborderait
              des deux côtés ; une feuille pleine largeur sur un écran de
              1400 px serait une bande vide. Les deux mises en page sont donc
              distinctes, et non une seule qui rétrécit.

              En bas et non sous l'en-tête : la liste est alors à portée du
              pouce, et surtout la position ne dépend plus d'une hauteur
              d'en-tête écrite en dur — celle-ci change avec la longueur du
              nom du salon, et une valeur devinée finit toujours par être
              fausse sur un écran qu'on n'avait pas essayé.
            */
            className="fixed inset-x-2 bottom-[max(0.5rem,env(safe-area-inset-bottom))] z-40 flex max-h-[min(75svh,34rem)] flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-float sm:absolute sm:inset-x-auto sm:bottom-auto sm:right-0 sm:top-[calc(100%+0.5rem)] sm:w-[23rem]"
          >
            <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
              <h2 className="text-sm font-semibold text-ink">Notifications</h2>
              {/*
                Affiché seulement quand il y a quelque chose à marquer.

                Il était là en permanence, grisé dès que le fil était lu —
                pendant que la pastille affichait un chiffre venu, lui, des
                éléments à traiter. On voyait donc « 2 » et un bouton mort,
                et l'on en concluait qu'il ne marchait pas. Un bouton qui
                n'existe pas ne se soupçonne pas d'être cassé.
              */}
              {nonLues > 0 && (
                <button
                  type="button"
                  onClick={marquerTout}
                  className="rounded-lg px-2 py-1 text-xs font-medium text-muted transition hover:bg-surface-hover hover:text-ink"
                >
                  Tout marquer lu
                </button>
              )}
            </div>

            <div className="max-h-[min(70svh,30rem)] overflow-y-auto overscroll-contain">
              <ATraiter
                attention={attention}
                onNaviguer={() => setOuvert(false)}
              />

              <Fil
                lignes={boite?.resultats ?? []}
                maintenant={maintenant}
                onOuvrir={(ligne) => {
                  marquer(ligne);
                  setOuvert(false);
                }}
              />
            </div>

            <ReglagePush
              etat={push}
              actifCoteServeur={boite?.push_actif ?? false}
              occupe={occupe}
              onBasculer={basculerPush}
            />
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Ce qui attend un geste.
 *
 * Trois compteurs, en deux colonnes sur téléphone et trois au-delà. Chacun
 * mène à l'endroit où l'on règle la chose — un compteur sur lequel on ne peut
 * pas cliquer oblige à chercher soi-même, et c'est ce qui fait qu'on remet à
 * plus tard.
 */
function ATraiter({
  attention,
  onNaviguer,
}: {
  attention: Attention | null;
  onNaviguer: () => void;
}) {
  if (!attention) return null;

  /*
    Chaque pastille mène à sa propre liste, et non à l'agenda entier.

    Les trois renvoyaient vers `/agenda` : on cliquait sur « 2 acomptes »
    et l'on tombait sur la semaine en cours, à charge de retrouver
    lesquels. La clé `attente` est lue par l'agenda et appliquée par le
    serveur avec **la même** définition que celle qui a produit le
    compte — sinon la pastille et la liste ne diraient pas la même chose.
  */
  const cases = [
    {
      cle: "acomptes",
      libelle: "Acomptes",
      valeur: attention.deposits,
    },
    {
      cle: "demandes",
      libelle: "Demandes",
      valeur: attention.requests,
    },
    {
      cle: "a-noter",
      libelle: "À noter",
      valeur: attention.overdue,
    },
  ].filter((c) => c.valeur > 0);

  if (!cases.length) return null;

  return (
    <div className="border-b border-line bg-surface-muted/50 px-3 py-3">
      <p className="mb-0.5 px-1 text-[0.7rem] font-semibold uppercase tracking-[0.1em] text-muted">
        À traiter
      </p>
      {/* La phrase répond à la question qu'on se pose en voyant que
          « Tout marquer lu » ne fait pas tomber ce compte : ce ne sont pas
          des messages, ce sont des tâches. */}
      <p className="mb-2 px-1 text-[0.68rem] leading-snug text-muted">
        Ces éléments restent tant qu’ils ne sont pas réglés.
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {cases.map((c) => (
          <Link
            key={c.cle}
            href={`/agenda?attente=${c.cle}`}
            onClick={onNaviguer}
            className="rounded-xl border border-line bg-surface px-2.5 py-2 transition hover:border-warning hover:bg-surface-hover"
          >
            <span className="tabular block text-lg font-semibold leading-tight text-ink">
              {c.valeur}
            </span>
            <span className="block truncate text-[0.7rem] text-muted">
              {c.libelle}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}

function Fil({
  lignes,
  maintenant,
  onOuvrir,
}: {
  lignes: Ligne[];
  maintenant: number;
  onOuvrir: (ligne: Ligne) => void;
}) {
  if (!lignes.length) {
    return (
      <div className="px-5 py-9 text-center">
        <p className="text-sm font-medium text-ink">Rien de neuf</p>
        <p className="mt-1 text-[0.78rem] leading-relaxed text-muted">
          Les réservations, acomptes et annulations qui arriveront à partir de
          maintenant s’afficheront ici.
        </p>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-line">
      {lignes.map((ligne) => {
        const genre = GENRES[ligne.genre] ?? { icone: "bell", ton: "neutre" };
        return (
          <li key={ligne.id}>
            <Link
              href={ligne.lien || "/"}
              onClick={() => onOuvrir(ligne)}
              className={`flex gap-3 px-3.5 py-3 transition hover:bg-surface-hover ${
                ligne.lue ? "" : "bg-salon-soft/40"
              }`}
            >
              <span
                aria-hidden
                className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg ${
                  TONS[genre.ton as keyof typeof TONS]
                }`}
              >
                <Icon name={genre.icone} className="size-4" />
              </span>

              <span className="min-w-0 flex-1">
                <span className="flex items-baseline justify-between gap-2">
                  <span
                    className={`truncate text-[0.82rem] leading-snug ${
                      ligne.lue
                        ? "font-medium text-muted"
                        : "font-semibold text-ink"
                    }`}
                  >
                    {ligne.titre}
                  </span>
                  <span className="shrink-0 text-[0.65rem] text-muted">
                    {depuis(ligne.created_at, maintenant)}
                  </span>
                </span>
                {ligne.corps && (
                  // Deux lignes au plus : au-delà, c'est l'écran qu'on doit
                  // ouvrir, pas la notification qu'on doit lire.
                  <span className="mt-0.5 line-clamp-2 text-[0.75rem] leading-snug text-muted">
                    {ligne.corps}
                  </span>
                )}
              </span>

              {!ligne.lue && (
                <span
                  aria-hidden
                  className="mt-2 size-1.5 shrink-0 self-start rounded-full bg-salon"
                />
              )}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * La ligne qui propose — ou explique — les notifications sur l'appareil.
 *
 * Elle dit toujours quelque chose de vrai, y compris quand elle ne peut rien
 * proposer. Un bouton absent laisse chercher ; un bouton qui ne fait rien
 * fait accuser le produit.
 */
function ReglagePush({
  etat,
  actifCoteServeur,
  occupe,
  onBasculer,
}: {
  etat: EtatPush | null;
  actifCoteServeur: boolean;
  occupe: boolean;
  onBasculer: () => void;
}) {
  if (!actifCoteServeur || etat === null || etat === "desactive") return null;

  const messages: Record<EtatPush, { texte: string; action?: string }> = {
    pret: {
      texte: "Notifications activées sur cet appareil.",
      action: "Désactiver",
    },
    possible: {
      texte: "Être prévenue sur cet appareil, même hors du tableau de bord.",
      action: "Activer",
    },
    refuse: {
      texte:
        "Les notifications sont bloquées pour ce site. Rouvrez-les dans les réglages de votre navigateur.",
    },
    "non-installe": {
      texte:
        "Sur iPhone : touchez Partager, puis « Sur l'écran d'accueil ». Les notifications deviendront disponibles.",
    },
    incompatible: {
      texte: "Ce navigateur ne gère pas les notifications.",
    },
    desactive: { texte: "" },
  };

  const { texte, action } = messages[etat];

  return (
    <div className="flex items-center gap-3 border-t border-line bg-surface-muted/50 px-4 py-3">
      <Icon
        name="bell"
        aria-hidden
        className={`size-4 shrink-0 ${etat === "pret" ? "text-success" : "text-muted"}`}
      />
      <p className="min-w-0 flex-1 text-[0.72rem] leading-snug text-muted">
        {texte}
      </p>
      {action && (
        <button
          type="button"
          onClick={onBasculer}
          disabled={occupe}
          className="shrink-0 rounded-lg border border-line px-2.5 py-1 text-[0.7rem] font-semibold text-ink transition hover:bg-surface-hover disabled:opacity-50"
        >
          {occupe ? "…" : action}
        </button>
      )}
    </div>
  );
}
