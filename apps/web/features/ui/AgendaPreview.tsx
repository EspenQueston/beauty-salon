/**
 * Un aperçu d'agenda, à côté du formulaire de connexion professionnelle.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'il remplace
 * ---------------------------------------------------------------------------
 *
 * Trois paragraphes qui décrivaient le produit. Personne ne lit la
 * description d'un logiciel à côté du champ où il faut taper son mot de
 * passe — on la contourne. Une journée d'agenda, elle, se comprend sans
 * être lue : trois rendez-vous, une heure chacun, un créneau libre au
 * milieu. C'est l'écran que la gérante ouvrira dans dix secondes.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi il ne peut pas être pris pour de vraies données
 * ---------------------------------------------------------------------------
 *
 * Aucun nom de cliente : uniquement des prestations et des heures. Une
 * capture qui ressemblerait à un agenda réel serait un mensonge tranquille —
 * on croirait voir son propre salon avant même d'être connecté. La mention
 * « Exemple » le dit en toutes lettres, et le bloc entier est `aria-hidden` :
 * un lecteur d'écran n'a rien à faire d'une illustration, et les trois
 * arguments qui suivent portent déjà l'information.
 *
 * Masqué sous `lg` : sur un téléphone, il repousserait les arguments sans
 * rien ajouter, et le panneau passe déjà sous le formulaire.
 */

const SLOTS = [
  { at: "09:00", label: "Tresses collées", span: 2, tone: "salon" },
  { at: "11:00", label: "Pose de perruque", span: 1, tone: "ink" },
  { at: "14:00", label: "Soin profond", span: 1, tone: "salon" },
] as const;

const HOURS = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00"];

export function AgendaPreview() {
  return (
    <div
      aria-hidden
      className="mb-8 hidden overflow-hidden rounded-2xl border border-line bg-surface p-4 shadow-card lg:block"
    >
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium text-ink">Mardi 14</p>
        <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[0.65rem] font-medium uppercase tracking-wider text-muted">
          Exemple
        </span>
      </div>

      <div className="grid grid-cols-[3rem_minmax(0,1fr)] gap-x-3">
        {/*
          La colonne des heures et celle des rendez-vous sont deux grilles
          qui partagent le même pas : six lignes de 2,25 rem. Un rendez-vous
          de deux heures occupe donc deux lignes, sans qu'aucune hauteur ne
          soit écrite deux fois.
        */}
        <ul className="grid grid-rows-6 gap-1">
          {HOURS.map((hour) => (
            <li
              key={hour}
              className="tabular flex h-9 items-start pt-0.5 text-[0.7rem] text-subtle"
            >
              {hour}
            </li>
          ))}
        </ul>

        <div className="relative grid grid-rows-6 gap-1">
          {/* Les filets d'heure : ils donnent l'échelle, donc le sens des
              hauteurs de bloc. */}
          {HOURS.map((hour) => (
            <span key={hour} className="h-9 rounded-lg bg-surface-muted/60" />
          ))}

          <div className="absolute inset-0 grid grid-rows-6 gap-1">
            {SLOTS.map((slot) => {
              const row = HOURS.indexOf(slot.at) + 1;
              return (
                <div
                  key={slot.at}
                  style={{ gridRow: `${row} / span ${slot.span}` }}
                  className={`flex flex-col justify-center rounded-lg px-2.5 ${
                    slot.tone === "salon"
                      ? "bg-salon-soft text-salon"
                      : "bg-surface-muted text-ink"
                  }`}
                >
                  <span className="truncate text-[0.72rem] font-medium leading-tight">
                    {slot.label}
                  </span>
                  <span className="tabular text-[0.62rem] opacity-70">
                    {slot.at}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
