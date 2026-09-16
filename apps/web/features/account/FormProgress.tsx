"use client";

/**
 * Avancement d'un formulaire, avec les étapes déjà acquises créditées.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi ne jamais afficher zéro
 * ---------------------------------------------------------------------------
 *
 * Quelqu'un qui arrive de la page d'accueil a déjà nommé son salon, vérifié
 * que son adresse était libre et choisi ses couleurs. Lui présenter « 0 sur
 * 5 » nie ce travail et transforme un formulaire à moitié rempli en une
 * corvée qui commence — c'est exactement là qu'on ferme l'onglet.
 *
 * Le compteur part donc de ce qui est réellement rempli, pré-remplissage
 * compris. Ce n'est pas un artifice de comptage : ces champs contiennent
 * bien une valeur, et elle vient d'un choix fait deux écrans plus tôt.
 *
 * Le décompte est **dérivé** des valeurs du formulaire à chaque rendu, jamais
 * stocké : un compteur mémorisé finirait par diverger de ce que la personne
 * voit à l'écran, et un chiffre faux est pire qu'aucun chiffre.
 */

interface Props {
  /** Étapes du formulaire, dans l'ordre où elles apparaissent. */
  steps: { key: string; label: string; done: boolean }[];
}

export function FormProgress({ steps }: Props) {
  const done = steps.filter((step) => step.done).length;
  const share = Math.round((done / steps.length) * 100);
  const finished = done === steps.length;

  return (
    <div className="mb-5">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <p className="text-sm text-muted">
          {finished ? (
            "Tout est rempli — il ne reste qu'à valider."
          ) : (
            <>
              <span className="tabular font-medium text-ink">{done}</span> sur{" "}
              {steps.length} déjà rempli{done > 1 ? "s" : ""}
            </>
          )}
        </p>
        <span className="tabular text-sm font-semibold text-salon">{share} %</span>
      </div>

      <div
        className="h-1.5 overflow-hidden rounded-full bg-surface-muted"
        role="progressbar"
        aria-valuenow={share}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Avancement du formulaire"
      >
        <span
          className="block h-full rounded-full bg-salon transition-[width] duration-500 ease-out"
          style={{ width: `${share}%` }}
        />
      </div>

      {/* Les libellés disent *quoi* remplir, pas seulement combien il en
          reste : un pourcentage sans destination n'aide pas à agir. */}
      <ul className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1">
        {steps.map((step) => (
          <li
            key={step.key}
            className={`text-xs ${
              step.done ? "text-subtle line-through" : "font-medium text-muted"
            }`}
          >
            {step.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
