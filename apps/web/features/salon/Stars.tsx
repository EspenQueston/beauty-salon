/**
 * Note en étoiles.
 *
 * Deux usages, un seul composant : affichage d'une note figée, et saisie.
 * Les garder ensemble garantit qu'une note lue et une note saisie se
 * ressemblent — sinon la cliente doute d'avoir bien mis ce qu'elle voit.
 *
 * En saisie, ce sont de vrais boutons radio masqués sous les étoiles : la
 * navigation au clavier et les lecteurs d'écran fonctionnent sans code
 * supplémentaire, là où une rangée de `<div>` cliquables ne donne rien.
 */

import { useTranslations } from "next-intl";
import { SalonIcon } from "./icons";

export function Stars({
  value,
  size = "size-4",
}: {
  value: number;
  size?: string;
}) {
  const t = useTranslations("salon");
  return (
    <span
      className="inline-flex items-center gap-0.5 text-[var(--salon-ink)]"
      aria-label={t("note.surCinq", { note: value })}
    >
      {[1, 2, 3, 4, 5].map((step) => (
        <SalonIcon
          key={step}
          name="star"
          className={size}
          filled={step <= Math.round(value)}
        />
      ))}
    </span>
  );
}

export function StarInput({
  value,
  onChange,
  name = "rating",
  label,
  compact = false,
}: {
  value: number;
  onChange: (value: number) => void;
  name?: string;
  /** Lu par les lecteurs d'écran à la place de « Votre note ». Avec cinq
   *  rangées sur la page, cinq légendes identiques ne situeraient rien. */
  label?: string;
  /**
   * Rangée serrée : étoiles plus petites, pas de mot sous la rangée.
   *
   * Cinq critères empilés avec chacun ses grandes étoiles et son libellé
   * feraient une page de deux écrans, et la moitié des clientes
   * abandonneraient avant le commentaire. Le mot reste accessible — infobulle
   * et texte lu — il ne prend simplement plus de place.
   */
  compact?: boolean;
}) {
  const t = useTranslations("salon");
  /* Les six libellés, de « » à « Excellent » : leur ordre est l'échelle. */
  const notes = t.raw("notes") as string[];
  const intitule = label ?? t("votreNote");
  return (
    <div>
      <fieldset className="flex items-center gap-0.5">
        <legend className="sr-only">{intitule}</legend>
        {[1, 2, 3, 4, 5].map((step) => (
          <label
            key={step}
            className={`cursor-pointer transition hover:scale-110 ${
              compact ? "p-0.5" : "p-1"
            }`}
            title={notes[step]}
          >
            <input
              type="radio"
              name={name}
              value={step}
              checked={value === step}
              onChange={() => onChange(step)}
              className="peer sr-only"
            />
            <SalonIcon
              name="star"
              // L'anneau au clavier est porté par l'étoile, pas par la case
              // masquée : sans lui, tabuler dans la rangée ne montre rien.
              className={`transition peer-focus-visible:ring-2 peer-focus-visible:ring-[var(--salon-primary)] peer-focus-visible:ring-offset-2 rounded-sm ${
                compact ? "size-7" : "size-9"
              } ${
                step <= value
                  ? "text-[var(--salon-ink)]"
                  : "text-[var(--site-line)]"
              }`}
              filled={step <= value}
            />
            <span className="sr-only">{notes[step]}</span>
          </label>
        ))}
      </fieldset>

      {/* Le libellé donne un sens au chiffre : « 3 » ne dit rien, « Correct »
          si. La hauteur est réservée pour que le formulaire ne saute pas au
          premier clic. */}
      {!compact && (
        <p className="mt-1 h-5 text-sm font-medium text-[var(--salon-ink)]">
          {value > 0 ? notes[value] : ""}
        </p>
      )}
    </div>
  );
}
