"use client";

/**
 * Le champ mot de passe des écrans d'identification.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi un œil, et pourquoi il n'est pas décoratif
 * ---------------------------------------------------------------------------
 *
 * Un mot de passe saisi à l'aveugle sur un clavier de téléphone se trompe
 * une fois sur trois — et comme rien ne se voit, on recommence le champ
 * entier au lieu de corriger une lettre. Les recommandations
 * d'authentification accessible du W3C en font un point explicite : la
 * personne doit pouvoir vérifier ce qu'elle a tapé.
 *
 * L'implémentation compte autant que l'intention :
 *
 *   - un vrai `<button type="button">`, donc atteignable au clavier et
 *     annoncé — un `<span onClick>` ne l'est ni l'un ni l'autre ;
 *   - `aria-pressed` porte l'état, et le libellé dit l'action à venir ;
 *   - on bascule le `type` du même champ plutôt que d'en échanger deux :
 *     un gestionnaire de mots de passe suit le champ, pas son apparence, et
 *     deux champs alternés lui feraient perdre le fil.
 *
 * `autoComplete` reste à la charge de l'appelant : « mot de passe actuel »
 * et « nouveau mot de passe » ne se remplissent pas de la même façon.
 */

import { useId, useState } from "react";

export function PasswordField({
  label,
  value,
  onChange,
  autoComplete,
  autoFocus = false,
  required = true,
  hint,
  action,
  inputClassName,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: "current-password" | "new-password";
  autoFocus?: boolean;
  required?: boolean;
  hint?: string;
  /** « Mot de passe oublié ? », posé sur la ligne du libellé. */
  action?: React.ReactNode;
  /** Classes du champ, pour suivre l'habillage de l'écran hôte. */
  inputClassName: string;
}) {
  const id = useId();
  const [shown, setShown] = useState(false);

  return (
    <div>
      <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <label htmlFor={id} className="text-sm font-medium text-ink">
          {label}
        </label>
        {action}
      </div>

      <div className="relative">
        <input
          id={id}
          type={shown ? "text" : "password"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          required={required}
          // La place du bouton est réservée dans le champ : sans elle, un
          // mot de passe long passerait sous l'œil.
          className={`${inputClassName} pr-12`}
        />

        <button
          type="button"
          onClick={() => setShown((current) => !current)}
          aria-pressed={shown}
          aria-controls={id}
          aria-label={
            shown ? "Masquer le mot de passe" : "Afficher le mot de passe"
          }
          title={shown ? "Masquer le mot de passe" : "Afficher le mot de passe"}
          className="absolute inset-y-0 right-0 flex w-12 items-center justify-center rounded-r-xl text-muted transition hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--color-salon)]"
        >
          <EyeIcon off={shown} />
        </button>
      </div>

      {hint && <p className="mt-1.5 text-xs text-muted">{hint}</p>}
    </div>
  );
}

/**
 * Œil ouvert / œil barré.
 *
 * La barre oblique est dessinée par-dessus l'œil plutôt qu'en remplaçant le
 * dessin : les deux états gardent la même silhouette, et le changement se lit
 * comme une bascule et non comme deux icônes différentes.
 */
function EyeIcon({ off }: { off: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className="size-5"
    >
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="3" />
      {off && <path d="M4 20 20 4" />}
    </svg>
  );
}
