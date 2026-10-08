"use client";

/**
 * Le chrome du parcours d'inscription : avancement, accusés de réception,
 * force du mot de passe.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi un segment par étape et pas une barre unique
 * ---------------------------------------------------------------------------
 *
 * Une barre unique répond à « combien reste-t-il ? ». Un segment par étape
 * répond en plus à « où suis-je ? » — et quand on ne voit qu'une étape à la
 * fois, c'est la seconde question qui inquiète. Les segments déjà pleins
 * restent à l'écran : ils sont la preuve du travail déjà fait, et c'est ce
 * qui retient de fermer l'onglet.
 *
 * Le nombre de segments suit le plan courant — deux sur un écran d'ordinateur,
 * trois sur un téléphone. Ce composant ne connaît pas cette règle : il compte
 * ce qu'on lui donne.
 *
 * ---------------------------------------------------------------------------
 * Une ligne, pas quatre
 * ---------------------------------------------------------------------------
 *
 * L'en-tête affichait « Étape 1 sur 2 », « 0 % », « 0 sur 5 » et « trois
 * minutes suffisent » : quatre façons de dire où l'on en est, empilées
 * au-dessus de trois champs. Un indicateur rassure, quatre donnent
 * l'impression d'un formulaire qui se surveille lui-même.
 *
 * Il reste le numéro d'étape — la seule information qu'on ne déduit pas —
 * et le mot d'avancement à droite, là où était le pourcentage. La
 * proportion, elle, se voit : c'est le rôle des segments.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi le compteur ne part jamais de zéro s'il peut l'éviter
 * ---------------------------------------------------------------------------
 *
 * Quelqu'un qui arrive de la page d'accueil a déjà nommé son salon et
 * vérifié que son adresse était libre. Lui afficher « 0 sur 5 » nie ce
 * travail et transforme un formulaire à moitié rempli en corvée qui
 * commence. Le décompte crédite donc le pré-remplissage — ces champs
 * contiennent bien une valeur, issue d'un choix fait deux écrans plus tôt.
 *
 * Il est **dérivé** des valeurs à chaque rendu, jamais stocké : un compteur
 * mémorisé finit par diverger de ce que la personne voit, et un chiffre faux
 * vaut moins que pas de chiffre.
 */

import type { ReactNode } from "react";

export interface PasDuParcours {
  cle: string;
  titre: string;
  /** Champs obligatoires de l'étape, et combien sont remplis. */
  requis: number;
  faits: number;
}

/**
 * Un mot qui accompagne l'avancement.
 *
 * Sobre volontairement : « Bravo ! » à chaque champ rempli se lit comme une
 * machine qui applaudit, et on cesse de le croire au troisième. Ces
 * formulations-ci constatent, elles ne félicitent pas.
 */
function encouragement(faits: number, total: number): string {
  if (faits === 0) return "trois minutes suffisent";
  if (faits === total) return "tout y est";
  const reste = total - faits;
  if (reste === 1) return "plus qu'un champ";
  if (reste === 2) return "plus que deux";
  return faits === 1 ? "bon début" : "vous avancez";
}

export function Parcours({
  etapes,
  etape,
}: {
  etapes: PasDuParcours[];
  /** Index de l'étape affichée. */
  etape: number;
}) {
  const total = etapes.reduce((n, g) => n + g.requis, 0);
  const faits = etapes.reduce((n, g) => n + Math.min(g.faits, g.requis), 0);

  return (
    <div className="mb-5">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        {/*
          `aria-live` : le changement d'étape n'est signalé par aucun
          rechargement de page. Sans annonce, quelqu'un qui navigue au lecteur
          d'écran voit le formulaire changer sous lui sans savoir pourquoi.
        */}
        <p className="text-sm text-muted" aria-live="polite">
          <span className="font-medium text-ink">
            Étape {etape + 1} sur {etapes.length}
          </span>{" "}
          · {etapes[etape]?.titre.toLowerCase()}
        </p>

        <span className="shrink-0 text-xs text-muted">
          {encouragement(faits, total)}
        </span>
      </div>

      <div
        className="flex gap-1.5"
        role="progressbar"
        aria-valuenow={faits}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-label="Avancement de l'inscription"
      >
        {etapes.map((pas) => (
          <span key={pas.cle} className="segment">
            <i
              style={{
                transform: `scaleX(${Math.min(1, pas.faits / pas.requis)})`,
              }}
            />
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * L'accusé de réception d'un champ correctement rempli.
 *
 * Il ne dit pas « c'est bon » — il dit ce que la valeur **produit** : le nom
 * qui s'affichera, l'adresse qui est libre, la monnaie qui sera appliquée.
 * Une coche seule confirme une syntaxe ; une conséquence confirme un choix,
 * et c'est ce qui donne envie d'aller au champ suivant.
 */
export function Acquis({
  actif,
  ton = "vert",
  children,
}: {
  actif: boolean;
  /** « vert » pour un acquis, « neutre » pour une simple conséquence. */
  ton?: "vert" | "neutre";
  children: ReactNode;
}) {
  if (!actif) return null;

  return (
    <p
      className={`acquis mt-1.5 flex items-start gap-1.5 text-xs leading-relaxed ${
        ton === "vert" ? "text-success" : "text-muted"
      }`}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
        className="mt-0.5 size-3 shrink-0"
      >
        <path d="M20 6 9 17l-5-5" />
      </svg>
      <span className="min-w-0">{children}</span>
    </p>
  );
}

/**
 * La force du mot de passe, mesurée sur ce qui compte vraiment.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi la longueur pèse plus que les symboles
 * ---------------------------------------------------------------------------
 *
 * Les règles de composition — une majuscule, un chiffre, un caractère
 * spécial — produisent des mots de passe que les machines devinent bien et
 * que les humains oublient : « Salon2024! » les satisfait toutes. Le NIST a
 * cessé de les recommander pour cette raison, et retient la longueur.
 *
 * L'indicateur suit donc la longueur d'abord, la variété ensuite, et il ne
 * bloque rien : le seul refus vient du schéma de validation, à dix
 * caractères. Le reste est une information, pas une barrière.
 */
export function ForceMotDePasse({ valeur }: { valeur: string }) {
  if (!valeur) return null;

  const varietes =
    (/[a-z]/.test(valeur) ? 1 : 0) +
    (/[A-Z]/.test(valeur) ? 1 : 0) +
    (/[0-9]/.test(valeur) ? 1 : 0) +
    (/[^a-zA-Z0-9]/.test(valeur) ? 1 : 0);

  const niveau =
    valeur.length < 10
      ? 0
      : valeur.length >= 16 || (valeur.length >= 12 && varietes >= 3)
        ? 2
        : 1;

  const mots = [
    {
      texte: `Encore ${10 - valeur.length} caractère${10 - valeur.length > 1 ? "s" : ""}`,
      ton: "text-muted",
    },
    { texte: "Correct", ton: "text-success" },
    { texte: "Solide", ton: "text-success" },
  ] as const;

  const largeur = Math.min(100, Math.round((valeur.length / 16) * 100));

  return (
    <div className="mt-2">
      <div className="h-1 overflow-hidden rounded-full bg-surface-muted">
        <span
          className={`block h-full rounded-full transition-[width,background-color] duration-300 ${
            niveau === 0 ? "bg-warning" : "bg-success"
          }`}
          style={{ width: `${Math.max(8, largeur)}%` }}
        />
      </div>
      <p className={`mt-1.5 text-xs ${mots[niveau].ton}`} aria-live="polite">
        {mots[niveau].texte}
        {niveau > 0 && valeur.length < 16 && (
          <span className="text-muted">
            {" "}
            · un mot de plus le rendrait solide
          </span>
        )}
      </p>
    </div>
  );
}
