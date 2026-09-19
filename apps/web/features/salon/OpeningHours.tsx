/**
 * Grille des horaires.
 *
 * Le jour courant est mis en avant : c'est la ligne que 90 % des visiteuses
 * cherchent, et la seule qui réponde à « est-ce ouvert maintenant ? ».
 */

import { shortTime, weekdayLabel } from "@/lib/format";
import type { PublicSalon } from "@/lib/types";
import { hoursByDay, todayIndex } from "./contact";
import { maintenantAuSalon } from "./ouverture";

export function OpeningHours({
  hours,
  compact = false,
  timeZone,
}: {
  hours: PublicSalon["business_hours"];
  /** Version courte : pas de badge, texte plus petit (pied de page). */
  compact?: boolean;
  /**
   * Fuseau du salon.
   *
   * Sans lui, « aujourd'hui » est le jour de la machine qui rend la page —
   * le serveur, pas la cliente, et surtout pas le salon. Un salon de
   * Guangzhou rendu depuis l'Europe voyait la pastille se poser sur la
   * veille pendant huit heures par jour. Facultatif pour ne pas casser les
   * appels existants, mais tout appelant qui connaît le fuseau doit le
   * passer.
   */
  timeZone?: string;
}) {
  const days = hoursByDay(hours);
  const today = timeZone
    ? maintenantAuSalon(timeZone, new Date()).jour
    : todayIndex();

  return (
    <ul className={compact ? "space-y-1 text-sm" : "space-y-2"}>
      {days.map((day) => {
        const isToday = day.weekday === today;
        const closed = day.ranges.length === 0;

        return (
          <li
            key={day.weekday}
            className={`flex items-baseline justify-between gap-4 ${
              isToday
                ? "font-medium text-[var(--site-ink)]"
                : "text-[var(--site-muted)]"
            }`}
          >
            <span className="flex items-center gap-2">
              {weekdayLabel(day.weekday)}
              {isToday && !compact && (
                <span
                  className="rounded-full px-2 py-0.5 text-[0.7rem] font-medium"
                  style={{
                    background: "var(--salon-accent)",
                    color: "var(--salon-ink-accent)",
                  }}
                >
                  aujourd&apos;hui
                </span>
              )}
            </span>

            <span className="tabular text-right">
              {closed ? (
                <span className="text-[var(--site-subtle)]">Fermé</span>
              ) : (
                day.ranges.map((range, index) => (
                  <span key={index} className="block whitespace-nowrap">
                    {shortTime(range.starts_at)} – {shortTime(range.ends_at)}
                  </span>
                ))
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
