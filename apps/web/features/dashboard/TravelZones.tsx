"use client";

/**
 * Grille des frais de déplacement.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi un forfait par quartier, et pas un tarif au kilomètre
 * ---------------------------------------------------------------------------
 *
 * Facturer la distance suppose deux adresses géocodables. Sur les marchés
 * visés, l'adresse de la cliente n'en est pas une : on se repère au quartier
 * et au point de référence, pas au numéro de rue. Un calcul au kilomètre
 * produirait des montants faux avec l'apparence de la précision.
 *
 * Le forfait par quartier, lui, est la grille que le salon utilise déjà au
 * téléphone.
 *
 * ---------------------------------------------------------------------------
 * Enregistrement au fil de la saisie
 * ---------------------------------------------------------------------------
 *
 * Chaque champ part dès qu'on le quitte, et seulement s'il a changé. Le reste
 * de la page a un bouton « Enregistrer » ; ici, une grille de dix quartiers
 * derrière un bouton unique, c'est dix modifications perdues au premier
 * rafraîchissement mal placé.
 */

import { useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import { formatPrice } from "@/lib/format";
import {
  Badge,
  Button,
  Card,
  DangerButton,
  EmptyState,
  ErrorState,
  GhostButton,
  SectionTitle,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { rows, useResource, type Page } from "./useResource";

export interface Zone {
  id: string;
  name: string;
  fee_amount: string;
  position: number;
  active: boolean;
}

export function TravelZones({
  tenantId,
  currency,
  canEdit,
}: {
  tenantId: string;
  currency: string;
  canEdit: boolean;
}) {
  const toast = useToast();
  const zones = useResource<Page<Zone>>("/api/v1/travel-zones/", tenantId);
  const [creating, setCreating] = useState(false);

  const list = rows(zones.data);

  async function patch(zone: Zone, changes: Partial<Zone>) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/travel-zones/${zone.id}/`,
          { method: "PATCH", body: JSON.stringify(changes) },
          tenantId,
        ),
      { success: "Zone mise à jour." },
    );
    if (ok) zones.reload();
  }

  async function remove(zone: Zone) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/travel-zones/${zone.id}/`,
          { method: "DELETE" },
          tenantId,
        ),
      { success: `« ${zone.name} » retirée de votre grille.` },
    );
    if (ok) zones.reload();
  }

  async function create(name: string, fee: string) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          "/api/v1/travel-zones/",
          {
            method: "POST",
            body: JSON.stringify({
              name,
              fee_amount: fee || "0",
              position: list.length,
            }),
          },
          tenantId,
        ),
      { success: `« ${name} » ajoutée à votre grille.` },
    );
    if (ok) {
      zones.reload();
      setCreating(false);
    }
    return ok;
  }

  const served = list.filter((zone) => zone.active);
  const free = served.filter((zone) => Number(zone.fee_amount) === 0).length;

  return (
    <Card>
      <SectionTitle>
        Zones de déplacement
        {served.length > 0 && (
          <span className="ml-2 font-normal normal-case tracking-normal text-subtle">
            {served.length} desservie{served.length > 1 ? "s" : ""}
            {free > 0 && ` · ${free} sans frais`}
          </span>
        )}
      </SectionTitle>

      <p className="-mt-2 mb-5 text-sm text-muted">
        Le forfait s&apos;ajoute au prix de la prestation et s&apos;affiche à la
        cliente <span className="text-ink">avant</span> qu&apos;elle confirme.
        Une zone à 0 est desservie gratuitement.
      </p>

      {zones.error && <ErrorState>Impossible de charger vos zones.</ErrorState>}
      {zones.data === null && !zones.error && <Skeleton rows={2} />}

      {zones.data !== null && list.length === 0 && !creating && (
        <EmptyState title="Aucune zone pour l'instant">
          Tant que cette grille est vide, la réservation à domicile n&apos;est
          pas proposée sur votre mini-site.
        </EmptyState>
      )}

      {list.length > 0 && (
        <ul className="space-y-2">
          {list.map((zone) => (
            <ZoneRow
              key={zone.id}
              zone={zone}
              currency={currency}
              canEdit={canEdit}
              onPatch={(changes) => patch(zone, changes)}
              onRemove={() => remove(zone)}
            />
          ))}
        </ul>
      )}

      {canEdit && (
        <div className="mt-4">
          {creating ? (
            <NewZone
              currency={currency}
              onCancel={() => setCreating(false)}
              onCreate={create}
            />
          ) : (
            <Button type="button" onClick={() => setCreating(true)}>
              Ajouter une zone
            </Button>
          )}
        </div>
      )}
    </Card>
  );
}

/**
 * Une ligne de la grille.
 *
 * Sur téléphone, le nom prend toute la largeur et le tarif passe dessous avec
 * ses commandes : à 375 px, trois champs sur une même ligne donnent trois
 * champs illisibles.
 */
function ZoneRow({
  zone,
  currency,
  canEdit,
  onPatch,
  onRemove,
}: {
  zone: Zone;
  currency: string;
  canEdit: boolean;
  onPatch: (changes: Partial<Zone>) => void;
  onRemove: () => void;
}) {
  const [name, setName] = useState(zone.name);
  const [fee, setFee] = useState(zone.fee_amount);

  const free = Number(fee) === 0;

  return (
    <li
      className={`rounded-xl border border-line p-3 transition ${
        zone.active ? "bg-surface" : "bg-surface-muted opacity-70"
      }`}
    >
      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_9rem_auto] sm:items-center">
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          onBlur={() => {
            const trimmed = name.trim();
            // Un nom vide rendrait la zone inchoisissable côté cliente.
            if (!trimmed) {
              setName(zone.name);
              return;
            }
            if (trimmed !== zone.name) onPatch({ name: trimmed });
          }}
          disabled={!canEdit}
          aria-label="Nom du quartier"
          className={inputClass}
        />

        <div className="flex items-center gap-2">
          <input
            value={fee}
            onChange={(event) => setFee(event.target.value)}
            onBlur={() => {
              if (fee !== zone.fee_amount) onPatch({ fee_amount: fee || "0" });
            }}
            disabled={!canEdit}
            inputMode="decimal"
            aria-label={`Frais de déplacement en ${currency}`}
            className={`${inputClass} tabular`}
          />
          <span className="shrink-0 text-xs text-subtle">{currency}</span>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 sm:justify-end">
          {/* Le montant relu en toutes lettres : un champ de saisie brut ne
              dit pas si « 3000 » vaut trois mille ou trente. */}
          <span className="text-xs">
            {free ? (
              <Badge tone="success">Offert</Badge>
            ) : (
              <span className="tabular text-muted">
                {formatPrice(fee, currency)}
              </span>
            )}
          </span>

          {canEdit && (
            <span className="flex items-center gap-1.5">
              <GhostButton
                type="button"
                onClick={() => onPatch({ active: !zone.active })}
              >
                {zone.active ? "Suspendre" : "Réactiver"}
              </GhostButton>
              <DangerButton type="button" onClick={onRemove}>
                Supprimer
              </DangerButton>
            </span>
          )}
        </div>
      </div>
    </li>
  );
}

function NewZone({
  currency,
  onCancel,
  onCreate,
}: {
  currency: string;
  onCancel: () => void;
  onCreate: (name: string, fee: string) => Promise<boolean>;
}) {
  const [name, setName] = useState("");
  const [fee, setFee] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: { preventDefault: () => void }) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;

    setPending(true);
    await onCreate(trimmed, fee);
    setPending(false);
    setName("");
    setFee("");
  }

  return (
    /*
      Un <div>, pas un <form>.

      Ce bloc s'affiche à l'intérieur du grand formulaire de la page Profil.
      Deux <form> imbriqués sont du HTML invalide, et le navigateur s'y
      comporte de façon imprévisible : ici, cliquer « Ajouter » déclenchait
      une vraie soumission — donc un rechargement de page — et tout ce qui
      n'était pas encore enregistré partait avec.

      La touche Entrée reste gérée à la main : c'est la seule chose que le
      <form> apportait réellement.
    */
    <div
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          void submit(event);
        }
      }}
      className="grid gap-2 rounded-xl border border-dashed border-line p-3 sm:grid-cols-[minmax(0,1fr)_9rem_auto] sm:items-center"
    >
      <input
        autoFocus
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="Bacongo"
        aria-label="Nom du quartier"
        className={inputClass}
      />
      <div className="flex items-center gap-2">
        <input
          value={fee}
          onChange={(event) => setFee(event.target.value)}
          placeholder="0"
          inputMode="decimal"
          aria-label={`Frais de déplacement en ${currency}`}
          className={`${inputClass} tabular`}
        />
        <span className="shrink-0 text-xs text-subtle">{currency}</span>
      </div>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          pending={pending}
          disabled={!name.trim()}
          onClick={(event) => void submit(event)}
        >
          Ajouter
        </Button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg px-2 py-2 text-sm text-muted transition hover:text-ink"
        >
          Annuler
        </button>
      </div>
    </div>
  );
}
