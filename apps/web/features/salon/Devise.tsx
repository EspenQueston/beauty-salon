"use client";

/**
 * Lire les prix d'un salon dans sa propre devise.
 *
 * ---------------------------------------------------------------------------
 * À qui ça sert
 * ---------------------------------------------------------------------------
 *
 * La diaspora. Une cliente à Brazzaville qui regarde un salon de Guangzhou
 * lit « 280 ¥ » et n'a aucune idée de ce que ça représente — elle ouvre un
 * autre onglet, cherche un convertisseur, et souvent ne revient pas. Le
 * chemin inverse existe aussi : une Congolaise installée en Chine qui
 * compare les tarifs de son ancien salon.
 *
 * ---------------------------------------------------------------------------
 * Ce que ça ne fait pas, et pourquoi c'est dit à l'écran
 * ---------------------------------------------------------------------------
 *
 * Le salon facture dans sa devise. Toujours. La conversion est une aide à
 * la lecture, pas un prix : le montant converti porte donc un « ≈ », et le
 * bouton affiche une mention quand un autre affichage est actif.
 *
 * Confondre les deux serait grave. Une cliente qui croit payer 23 900 francs
 * et à qui l'on demande 280 yuans a l'impression qu'on a changé le prix — et
 * le taux du jour de la réservation ne sera pas celui du jour du paiement.
 * C'est pour ça que le parcours de réservation, lui, n'est jamais converti :
 * à partir du moment où l'on s'engage, un seul chiffre compte.
 *
 * ---------------------------------------------------------------------------
 * Ce qui se passe quand le taux manque
 * ---------------------------------------------------------------------------
 *
 * Rien. Les prix restent dans la devise du salon, ce qui est toujours exact.
 * Un service de taux indisponible ne doit pas laisser une page à moitié
 * convertie, ni un montant vide.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { browserApi } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import { SalonIcon } from "./icons";

/**
 * Le taux, demandé à l'API du salon.
 *
 * `browserApi()` et non un chemin relatif : le mini-site est servi par Next
 * sur un port, l'API répond sur un autre. Un `/api/v1/...` nu partait vers
 * Next, qui répondait 404 — la conversion échouait en silence et la page
 * gardait la devise du salon. Exact, mais pas ce qu'on avait demandé.
 *
 * L'hôte est déduit de celui de la page : depuis `blondrose.localhost`, le
 * tenant se résout tout seul côté serveur.
 */
async function lireTaux(vers: string): Promise<number> {
  const reponse = await fetch(
    `${browserApi()}/api/v1/public/rate?vers=${encodeURIComponent(vers)}`,
  );
  if (!reponse.ok) throw new Error("taux indisponible");
  const data = await reponse.json();
  const valeur = Number(data.taux);
  if (!valeur || !Number.isFinite(valeur)) throw new Error("taux inexploitable");
  return valeur;
}

/** Ce qu'on propose de lire, au-delà de la devise du salon. */
const PROPOSEES = [
  { code: "XAF", label: "Franc CFA", court: "FCFA" },
  { code: "CNY", label: "Yuan", court: "¥" },
  { code: "CDF", label: "Franc congolais", court: "FC" },
  { code: "EUR", label: "Euro", court: "€" },
  { code: "USD", label: "Dollar", court: "$" },
];

function court(code: string): string {
  return PROPOSEES.find((d) => d.code === code)?.court ?? code;
}

interface Contexte {
  /** La devise du salon. Celle dans laquelle il encaisse. */
  reelle: string;
  /** Celle que la visiteuse a choisi de lire. Égale à `reelle` par défaut. */
  affichee: string;
  choisir: (code: string) => void;
  /** Formate un montant dans la devise affichée, avec « ≈ » si converti. */
  prix: (montant: string | number) => string;
  /** Vrai pendant l'aller-retour vers le taux. */
  occupe: boolean;
}

const DeviseContext = createContext<Contexte | null>(null);

export function useDevise(): Contexte {
  const contexte = useContext(DeviseContext);
  if (!contexte) {
    throw new Error("useDevise doit être utilisé dans DeviseProvider.");
  }
  return contexte;
}

export function DeviseProvider({
  salonSlug,
  devise,
  children,
}: {
  salonSlug: string;
  /** La devise du salon. */
  devise: string;
  children: ReactNode;
}) {
  const [affichee, setAffichee] = useState(devise);
  const [taux, setTaux] = useState(1);
  const [occupe, setOccupe] = useState(false);

  const cle = `beauty-salon.devise.${salonSlug}`;

  /*
    Le choix est relu au montage, pas pendant le rendu du serveur.

    Le serveur ne peut pas connaître le choix d'une visiteuse : rendre les
    prix convertis côté serveur produirait un écart d'hydratation à chaque
    chargement. On part donc toujours de la devise du salon, et l'on
    convertit après — ce qui a l'avantage d'être la valeur exacte tant que
    le taux n'est pas arrivé.
  */
  useEffect(() => {
    let perime = false;

    let voulue = devise;
    try {
      voulue = localStorage.getItem(cle) || devise;
    } catch {
      // Stockage refusé (navigation privée) : on reste sur la devise du
      // salon, ce qui est le comportement par défaut de toute façon.
    }
    if (voulue === devise) return;

    /*
      Pas d'indicateur d'attente ici, contrairement à `choisir`.

      Le poser demanderait un `setState` synchrone dans le corps de l'effet,
      donc un rendu en cascade au montage de chaque page — et il n'aurait
      rien à signaler : tant que le taux n'est pas arrivé, la page affiche
      les prix dans la devise du salon, c'est-à-dire la valeur exacte. Il
      n'y a rien à faire patienter.

      `choisir`, lui, répond à un clic : là, l'attente se voit et se dit.
    */
    lireTaux(voulue)
      .then((valeur) => {
        if (perime) return;
        setTaux(valeur);
        setAffichee(voulue);
      })
      .catch(() => {
        // Taux indisponible : on garde la devise du salon. Une page à
        // moitié convertie serait pire qu'une page non convertie.
      });

    return () => {
      perime = true;
    };
  }, [cle, devise]);

  const choisir = useCallback(
    (code: string) => {
      try {
        localStorage.setItem(cle, code);
      } catch {
        // Sans stockage, le choix ne survit pas au changement de page. Il
        // vaut mieux que rien.
      }

      if (code === devise) {
        setAffichee(devise);
        setTaux(1);
        return;
      }

      setOccupe(true);
      lireTaux(code)
        .then((valeur) => {
          setTaux(valeur);
          setAffichee(code);
        })
        .catch(() => {
          // On revient à la devise du salon plutôt que de laisser un
          // affichage à moitié converti.
          setAffichee(devise);
          setTaux(1);
        })
        .finally(() => setOccupe(false));
    },
    [cle, devise],
  );

  const valeur = useMemo<Contexte>(
    () => ({
      reelle: devise,
      affichee,
      choisir,
      occupe,
      prix: (montant) => {
        const brut = typeof montant === "string" ? Number(montant) : montant;
        if (affichee === devise) return formatPrice(brut, devise);
        // Le « ≈ » n'est pas décoratif : il dit que ce chiffre n'est pas
        // celui qui sera facturé.
        return `≈ ${formatPrice(brut * taux, affichee)}`;
      },
    }),
    [affichee, choisir, devise, occupe, taux],
  );

  return (
    <DeviseContext.Provider value={valeur}>{children}</DeviseContext.Provider>
  );
}

/**
 * Le bouton, dans la barre du haut.
 *
 * Il affiche la devise lue actuellement — c'est l'information utile — et
 * ouvre une liste courte. Fermé, il n'occupe que trois caractères : la barre
 * en compte déjà quatre éléments sur téléphone.
 */
export function DeviseToggle({ className = "" }: { className?: string }) {
  const { reelle, affichee, choisir, occupe } = useDevise();
  const [ouvert, setOuvert] = useState(false);

  // La devise du salon d'abord, puis les autres : on lit son prix réel avant
  // de lire une estimation.
  const options = useMemo(() => {
    const autres = PROPOSEES.filter((d) => d.code !== reelle);
    const sienne = PROPOSEES.find((d) => d.code === reelle) ?? {
      code: reelle,
      label: reelle,
      court: reelle,
    };
    return [sienne, ...autres];
  }, [reelle]);

  return (
    <div className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOuvert((o) => !o)}
        aria-expanded={ouvert}
        aria-label={`Afficher les prix en une autre devise (actuellement ${court(affichee)})`}
        className={`flex h-9 items-center gap-1 rounded-full border px-2.5 text-xs font-semibold transition ${
          affichee === reelle
            ? "border-[var(--site-line)] text-[var(--site-muted)] hover:border-[var(--salon-primary)] hover:text-[var(--salon-ink)]"
            : "border-[var(--salon-primary)] text-[var(--salon-ink)]"
        }`}
      >
        <SalonIcon name="sparkle" className={`size-3.5 ${occupe ? "animate-pulse" : ""}`} />
        {court(affichee)}
      </button>

      {ouvert && (
        <>
          {/* Capte le clic à côté. Un menu qui ne se referme pas piège le
              pouce sur téléphone. */}
          <button
            type="button"
            aria-hidden
            tabIndex={-1}
            onClick={() => setOuvert(false)}
            className="fixed inset-0 z-40 cursor-default"
          />
          <div className="absolute right-0 z-50 mt-2 w-52 overflow-hidden rounded-xl border border-[var(--site-line)] bg-[var(--site-surface)] shadow-lg">
            <p className="border-b border-[var(--site-line)] px-3 py-2 text-[0.7rem] leading-snug text-[var(--site-subtle)]">
              Lire les prix en…
            </p>
            <ul>
              {options.map((option) => (
                <li key={option.code}>
                  <button
                    type="button"
                    onClick={() => {
                      choisir(option.code);
                      setOuvert(false);
                    }}
                    className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm transition hover:bg-[var(--salon-primary)]/[0.06] ${
                      option.code === affichee
                        ? "font-semibold text-[var(--salon-ink)]"
                        : "text-[var(--site-ink)]"
                    }`}
                  >
                    <span className="truncate">{option.label}</span>
                    <span className="shrink-0 text-xs text-[var(--site-subtle)]">
                      {option.code === reelle ? "facturé" : option.court}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            {affichee !== reelle && (
              <p className="border-t border-[var(--site-line)] px-3 py-2 text-[0.68rem] leading-snug text-[var(--site-subtle)]">
                Conversion indicative, au taux du jour. Le salon encaisse en{" "}
                {court(reelle)}.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Un prix, dans la devise que la visiteuse a choisi de lire.
 *
 * Composant plutôt qu'appel direct à `formatPrice` : les cartes de
 * prestation sont rendues côté serveur, qui ne peut pas connaître ce choix.
 * Seul le prix devient client, pas la carte entière.
 */
export function Prix({
  montant,
  prefixe = "",
  className = "",
}: {
  montant: string | number;
  /** « À partir de », le cas échéant. */
  prefixe?: string;
  className?: string;
}) {
  const { prix } = useDevise();
  return (
    <span className={className}>
      {prefixe ? `${prefixe} ` : ""}
      {prix(montant)}
    </span>
  );
}
