"use client";

/**
 * Changer la devise du salon, et convertir son catalogue.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi un aperçu avant de basculer
 * ---------------------------------------------------------------------------
 *
 * Convertir un catalogue est irréversible en pratique : le taux de demain
 * n'est pas celui d'aujourd'hui, donc revenir en arrière ne rend pas les
 * prix d'origine. Et l'erreur possible est grossière — se tromper de sens —
 * pour une conséquence qui ne l'est pas : une grille tarifaire divisée par
 * quatre-vingt-cinq, sur laquelle le salon facture pendant des semaines.
 *
 * L'écran montre donc d'abord ce que ça ferait, sur un exemple concret :
 * « Pose gel couleur : 280,00 CNY devient 23 863 FCFA ». C'est cette ligne
 * qui fait repérer l'erreur, pas un taux à quatre décimales.
 *
 * ---------------------------------------------------------------------------
 * Ce qui change, et ce qui ne change pas
 * ---------------------------------------------------------------------------
 *
 * Les prix à venir sont convertis. L'historique — rendez-vous passés,
 * écritures comptables — garde sa devise d'origine : une pose encaissée
 * 25 000 francs a rapporté 25 000 francs, et la recalculer réécrirait le
 * livre de comptes. Le bloc le dit, parce que c'est la question que pose
 * n'importe quelle gérante avant d'accepter.
 */

import { useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import { Button, Card, Field, GhostButton, SectionTitle, inputClass } from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { Icon } from "./icons";

interface Choix {
  value: string;
  label: string;
}

interface Apercu {
  de: string;
  vers: string;
  taux: string;
  inverse: string;
  lignes: Record<string, number>;
  exemple: { nom: string; avant: string; apres: string } | null;
}

interface Etat {
  currency: string;
  country: string;
  expected: string | null;
  /** Le pays déclaré et la devise en place ne concordent pas. */
  mismatch: boolean;
  choices: Choix[];
  preview?: Apercu;
}

const PAYS: Record<string, string> = {
  CG: "Congo-Brazzaville",
  CD: "République démocratique du Congo",
  CN: "Chine",
};

/** Les libellés courts, ceux qu'on lit sur un prix. */
const COURT: Record<string, string> = {
  XAF: "FCFA",
  CDF: "FC",
  CNY: "¥",
};

export function CurrencySwitch({
  tenantId,
  canEdit,
  onChanged,
}: {
  tenantId: string;
  canEdit: boolean;
  /** Rappelé après une bascule : les prix affichés ailleurs ont changé. */
  onChanged: () => void;
}) {
  const toast = useToast();
  const [etat, setEtat] = useState<Etat | null>(null);
  const [cible, setCible] = useState("");
  const [apercu, setApercu] = useState<Apercu | null>(null);
  const [occupe, setOccupe] = useState(false);

  // Chargé à l'ouverture du bloc plutôt qu'au montage de la page : cet
  // écran compte déjà six appels, et la devise ne se change presque jamais.
  const [ouvert, setOuvert] = useState(false);

  async function ouvrir() {
    setOuvert(true);
    if (etat) return;
    try {
      const data = await dashboardFetch<Etat>("/api/v1/salon-currency", {}, tenantId);
      setEtat(data);
      setCible(data.expected && data.mismatch ? data.expected : "");
    } catch {
      toast.error("Impossible de lire la devise du salon.");
    }
  }

  async function demanderApercu(vers: string) {
    setCible(vers);
    setApercu(null);
    if (!vers) return;

    setOccupe(true);
    try {
      const data = await dashboardFetch<Etat>(
        `/api/v1/salon-currency?vers=${encodeURIComponent(vers)}`,
        {},
        tenantId,
      );
      setApercu(data.preview ?? null);
    } catch (erreur) {
      // Le serveur explique pourquoi — taux indisponible, devise identique.
      // Le message vient de lui : il sait lequel des deux c'est.
      toast.error(
        erreur instanceof Error && erreur.message
          ? erreur.message
          : "Aperçu impossible pour le moment.",
      );
    } finally {
      setOccupe(false);
    }
  }

  async function basculer() {
    if (!apercu) return;
    setOccupe(true);

    const ok = await toast.run(
      () =>
        dashboardFetch(
          "/api/v1/salon-currency",
          { method: "POST", body: JSON.stringify({ currency: apercu.vers }) },
          tenantId,
        ),
      { success: `Vos tarifs sont désormais en ${nom(apercu.vers)}.` },
    );

    setOccupe(false);
    if (ok) {
      setEtat(null);
      setApercu(null);
      setCible("");
      setOuvert(false);
      onChanged();
    }
  }

  function nom(code: string) {
    return COURT[code] ?? code;
  }

  if (!ouvert) {
    return (
      <Card id="devise">
        <SectionTitle>Devise</SectionTitle>
        <p className="text-sm text-muted">
          Vos tarifs, vos acomptes et votre boutique s&apos;affichent dans une
          seule devise. La changer convertit tout votre catalogue au taux du
          jour.
        </p>
        <div className="mt-4">
          <GhostButton type="button" onClick={ouvrir}>
            Voir ou changer la devise
          </GhostButton>
        </div>
      </Card>
    );
  }

  return (
    <Card id="devise">
      <SectionTitle>Devise</SectionTitle>

      {!etat ? (
        <p className="text-sm text-muted">Chargement…</p>
      ) : (
        <>
          <p className="text-sm text-muted">
            Vos tarifs sont en{" "}
            <strong className="text-ink">
              {etat.choices.find((c) => c.value === etat.currency)?.label ??
                etat.currency}
            </strong>
            .
          </p>

          {/*
            Le détecteur, réduit à ce qu'il peut affirmer.

            Le pays vient de l'inscription. Quand il ne concorde pas avec la
            devise en place, c'est presque toujours une erreur de saisie —
            mais « presque » n'est pas « toujours », et un salon chinois qui
            facture en francs a peut-être ses raisons. On pose donc la
            question, on ne corrige pas d'office.
          */}
          {etat.mismatch && etat.expected && (
            <p className="mt-3 flex items-start gap-2 rounded-lg bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-300">
              <Icon name="bell" className="mt-0.5 size-4 shrink-0" />
              <span>
                Votre salon est déclaré en{" "}
                <strong>{PAYS[etat.country] ?? etat.country}</strong>, où l&apos;on
                facture habituellement en{" "}
                <strong>
                  {etat.choices.find((c) => c.value === etat.expected)?.label}
                </strong>
                . Vous pouvez basculer ci-dessous — ou garder votre devise
                actuelle si c&apos;est voulu.
              </span>
            </p>
          )}

          {canEdit && (
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <Field
                label="Passer à"
                hint="Vos prix seront convertis au taux du jour, arrondis à l'unité de la nouvelle devise."
              >
                <select
                  value={cible}
                  onChange={(event) => demanderApercu(event.target.value)}
                  disabled={occupe}
                  className={inputClass}
                >
                  <option value="">Garder {nom(etat.currency)}</option>
                  {etat.choices
                    .filter((choix) => choix.value !== etat.currency)
                    .map((choix) => (
                      <option key={choix.value} value={choix.value}>
                        {choix.label}
                      </option>
                    ))}
                </select>
              </Field>
            </div>
          )}

          {apercu && (
            <div className="mt-5 rounded-xl border border-line p-4">
              <p className="text-sm font-medium text-ink">
                Ce que la bascule ferait
              </p>

              {/*
                L'exemple d'abord, le taux ensuite. C'est en lisant « 280 ¥
                devient 23 863 FCFA » qu'on repère une erreur de sens ; le
                taux, lui, ne se vérifie pas de tête.
              */}
              {apercu.exemple && (
                <p className="mt-2 text-sm text-muted">
                  <span className="text-ink">{apercu.exemple.nom}</span> :{" "}
                  <span className="tabular">{apercu.exemple.avant}</span>{" "}
                  {nom(apercu.de)} devient{" "}
                  <span className="tabular font-semibold text-ink">
                    {apercu.exemple.apres}
                  </span>{" "}
                  {nom(apercu.vers)}
                </p>
              )}

              <p className="mt-1 text-xs text-muted">
                Taux retenu : 1 {nom(apercu.vers)} ={" "}
                <span className="tabular">{apercu.inverse}</span> {nom(apercu.de)}
              </p>

              {/* Deux colonnes sur téléphone : quatre compteurs courts. */}
              <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {Object.entries(apercu.lignes).map(([nomLigne, combien]) => (
                  <div key={nomLigne} className="rounded-lg bg-surface-muted px-3 py-2">
                    <dt className="text-xs capitalize text-muted">{nomLigne}</dt>
                    <dd className="tabular text-lg font-semibold text-ink">
                      {combien}
                    </dd>
                  </div>
                ))}
              </dl>

              <p className="mt-4 flex items-start gap-2 text-xs text-muted">
                <Icon name="receipt" className="mt-0.5 size-3.5 shrink-0" />
                <span>
                  Vos rendez-vous passés et vos écritures comptables gardent
                  leur devise d&apos;origine : ce qui a été encaissé en{" "}
                  {nom(apercu.de)} reste en {nom(apercu.de)}.
                </span>
              </p>

              {canEdit && (
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button type="button" onClick={basculer} disabled={occupe}>
                    Convertir en {nom(apercu.vers)}
                  </Button>
                  <GhostButton
                    type="button"
                    onClick={() => {
                      setApercu(null);
                      setCible("");
                    }}
                  >
                    Annuler
                  </GhostButton>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </Card>
  );
}
