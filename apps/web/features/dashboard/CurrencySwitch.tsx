"use client";

/**
 * La devise du salon : celle qu'il affiche, et celle qu'il facture.
 *
 * ---------------------------------------------------------------------------
 * Ce que ce bloc a d'abord raté
 * ---------------------------------------------------------------------------
 *
 * Il demandait une action là où il fallait montrer un état. Un menu déroulant
 * « Passer à » dont la première option était « Garder ¥ » : on y lisait une
 * commande à exécuter, pas la devise en vigueur — et le texte d'aide parlait
 * de conversion même quand on ne changeait rien. S'y ajoutait un bouton
 * « Voir ou changer la devise » qui n'apportait qu'un clic.
 *
 * Les devises sont maintenant posées à plat, comme les palettes de couleurs
 * plus haut : celle du salon est marquée, les autres se choisissent. On voit
 * où l'on est avant de se demander où aller.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi un aperçu avant de basculer
 * ---------------------------------------------------------------------------
 *
 * Convertir un catalogue est irréversible en pratique : le taux de demain
 * n'est pas celui d'aujourd'hui, donc revenir en arrière ne rend pas les prix
 * d'origine. Et l'erreur possible est grossière — se tromper de sens — pour
 * une conséquence qui ne l'est pas : une grille tarifaire divisée par
 * quatre-vingt-cinq, sur laquelle le salon facture pendant des semaines.
 *
 * L'écran montre donc ce que ça ferait, sur un exemple concret : « Pose gel
 * couleur : 280,00 ¥ devient 23 863 FCFA ». C'est cette ligne qui fait
 * repérer l'erreur, pas un taux à quatre décimales.
 *
 * ---------------------------------------------------------------------------
 * Ce qui change, et ce qui ne change pas
 * ---------------------------------------------------------------------------
 *
 * Les prix à venir sont convertis. L'historique — rendez-vous passés,
 * écritures comptables — garde sa devise d'origine : une pose encaissée
 * 25 000 francs a rapporté 25 000 francs, et la recalculer réécrirait le
 * livre de comptes.
 *
 * Et c'est bien cette devise-là que lisent les mini-sites : une visiteuse
 * peut demander à lire les prix autrement, mais son choix est abandonné dès
 * que le salon change de devise. C'est le salon qui facture.
 */

import { useEffect, useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import { Button, Card, GhostButton, SectionTitle } from "@/features/ui";
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

/** Le symbole qu'on lit sur un prix, plus court que le nom. */
const COURT: Record<string, string> = {
  XAF: "FCFA",
  CDF: "FC",
  CNY: "¥",
  EUR: "€",
  USD: "$",
};

function court(code: string): string {
  return COURT[code] ?? code;
}

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
  const [apercu, setApercu] = useState<Apercu | null>(null);
  const [occupe, setOccupe] = useState(false);

  useEffect(() => {
    let perime = false;
    dashboardFetch<Etat>("/api/v1/salon-currency", {}, tenantId)
      .then((data) => {
        if (!perime) setEtat(data);
      })
      .catch(() => {
        // Le bloc reste sur son squelette : le reste de la page, lui,
        // fonctionne. Un écran de profil qui refuse de s'afficher parce
        // qu'une lecture accessoire a échoué serait pire.
      });
    return () => {
      perime = true;
    };
  }, [tenantId]);

  async function demanderApercu(vers: string) {
    setApercu(null);
    setOccupe(true);
    try {
      const data = await dashboardFetch<Etat>(
        `/api/v1/salon-currency?vers=${encodeURIComponent(vers)}`,
        {},
        tenantId,
      );
      setApercu(data.preview ?? null);
    } catch (erreur) {
      // Le message vient du serveur : lui seul sait si c'est le taux qui
      // manque ou la devise qui est refusée.
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
      { success: `Vos tarifs sont désormais en ${court(apercu.vers)}.` },
    );

    setOccupe(false);
    if (ok) {
      setEtat((actuel) =>
        actuel ? { ...actuel, currency: apercu.vers, mismatch: false } : actuel,
      );
      setApercu(null);
      onChanged();
    }
  }

  if (!etat) {
    return (
      <Card id="devise">
        <SectionTitle>Devise</SectionTitle>
        <p className="text-sm text-muted">Chargement…</p>
      </Card>
    );
  }

  const actuelle = etat.choices.find((c) => c.value === etat.currency);

  return (
    <Card id="devise">
      <SectionTitle>Devise</SectionTitle>

      <p className="text-sm text-muted">
        Vos tarifs, vos acomptes et votre boutique sont en{" "}
        <strong className="text-ink">{actuelle?.label ?? etat.currency}</strong>
        . C&apos;est aussi la devise affichée par défaut sur votre mini-site.
      </p>

      {/*
        Le détecteur, réduit à ce qu'il peut affirmer.

        Le pays vient de l'inscription. Quand il ne concorde pas avec la
        devise en place, c'est presque toujours une erreur de saisie — mais
        « presque » n'est pas « toujours », et un salon chinois qui facture
        en francs a peut-être ses raisons. On pose la question, on ne corrige
        pas d'office.
      */}
      {etat.mismatch && etat.expected && (
        <p className="mt-4 flex items-start gap-2 rounded-lg bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-300">
          <Icon name="bell" className="mt-0.5 size-4 shrink-0" />
          <span>
            Votre salon est déclaré en{" "}
            <strong>{PAYS[etat.country] ?? etat.country}</strong>, où l&apos;on
            facture habituellement en{" "}
            <strong>
              {etat.choices.find((c) => c.value === etat.expected)?.label}
            </strong>
            . Choisissez-la ci-dessous si c&apos;est une erreur — ou gardez la
            vôtre si c&apos;est voulu.
          </span>
        </p>
      )}

      {/*
        Les devises à plat plutôt qu'en menu déroulant.

        Deux colonnes sur téléphone, trois ensuite : c'est une grille de cinq
        options courtes, pas une liste à dérouler. Celle du salon porte sa
        marque et n'est pas cliquable — on ne « choisit » pas là où l'on est
        déjà.
      */}
      <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-3">
        {etat.choices.map((choix) => {
          const sienne = choix.value === etat.currency;
          const visee = apercu?.vers === choix.value;

          return (
            <button
              key={choix.value}
              type="button"
              disabled={!canEdit || sienne || occupe}
              onClick={() => demanderApercu(choix.value)}
              aria-pressed={visee}
              className={`flex flex-col items-start gap-0.5 rounded-xl border px-3 py-2.5 text-left transition ${
                sienne
                  ? "border-accent bg-accent/10"
                  : visee
                    ? "border-accent bg-accent/5"
                    : "border-line hover:border-accent/60 disabled:hover:border-line"
              } ${!canEdit ? "cursor-default" : ""}`}
            >
              <span className="flex w-full items-center justify-between gap-2">
                <span className="truncate text-sm font-medium text-ink">
                  {choix.label}
                </span>
                <span className="tabular shrink-0 text-xs text-muted">
                  {court(choix.value)}
                </span>
              </span>
              <span className="text-[0.7rem] text-muted">
                {sienne ? "Votre devise" : visee ? "Sélectionnée" : "Basculer"}
              </span>
            </button>
          );
        })}
      </div>

      {occupe && !apercu && (
        <p className="mt-4 text-sm text-muted">Lecture du taux du jour…</p>
      )}

      {apercu && (
        <div className="mt-5 rounded-xl border border-line p-4">
          <p className="text-sm font-medium text-ink">
            Passer de {court(apercu.de)} à {court(apercu.vers)}
          </p>

          {/*
            L'exemple d'abord, le taux ensuite. C'est en lisant « 280 ¥
            devient 23 863 FCFA » qu'on repère une erreur de sens ; le taux,
            lui, ne se vérifie pas de tête.
          */}
          {apercu.exemple && (
            <p className="mt-2 text-sm text-muted">
              <span className="text-ink">{apercu.exemple.nom}</span> :{" "}
              <span className="tabular">{apercu.exemple.avant}</span>{" "}
              {court(apercu.de)} devient{" "}
              <span className="tabular font-semibold text-ink">
                {apercu.exemple.apres}
              </span>{" "}
              {court(apercu.vers)}
            </p>
          )}

          <p className="mt-1 text-xs text-muted">
            Taux du jour : 1 {court(apercu.vers)} ={" "}
            <span className="tabular">{apercu.inverse}</span> {court(apercu.de)}
          </p>

          {/* Deux colonnes sur téléphone : quatre compteurs courts. */}
          <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {Object.entries(apercu.lignes).map(([nom, combien]) => (
              <div key={nom} className="rounded-lg bg-surface-muted px-3 py-2">
                <dt className="text-xs capitalize text-muted">{nom}</dt>
                <dd className="tabular text-lg font-semibold text-ink">
                  {combien}
                </dd>
              </div>
            ))}
          </dl>

          <p className="mt-4 flex items-start gap-2 text-xs text-muted">
            <Icon name="receipt" className="mt-0.5 size-3.5 shrink-0" />
            <span>
              Vos rendez-vous passés et vos écritures comptables gardent leur
              devise d&apos;origine : ce qui a été encaissé en {court(apercu.de)}{" "}
              reste en {court(apercu.de)}.
            </span>
          </p>

          {canEdit && (
            <div className="mt-4 flex flex-wrap gap-2">
              <Button type="button" onClick={basculer} pending={occupe}>
                Convertir en {court(apercu.vers)}
              </Button>
              <GhostButton type="button" onClick={() => setApercu(null)}>
                Annuler
              </GhostButton>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
