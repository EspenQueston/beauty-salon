"use client";

/**
 * Options d'une prestation, éditées depuis sa fiche.
 *
 * ---------------------------------------------------------------------------
 * Les deux colonnes ne sont pas décoratives
 * ---------------------------------------------------------------------------
 *
 * Le supplément se comprend tout seul. Le **temps**, lui, est ce que la
 * plupart des salons oublient de renseigner — et c'est celui qui compte le
 * plus : il entre dans la recherche de créneau. Une pose « longueur XL » à 0
 * minute se verra proposer un créneau de la durée de base, et la cliente
 * suivante attendra sur le trottoir.
 *
 * Le champ est donc à côté du prix, pas caché derrière un dépliant, et le
 * récapitulatif du bas rappelle ce que la prestation dure une fois toutes
 * les options cochées.
 *
 * Comme pour les zones de déplacement, chaque champ part dès qu'on le
 * quitte : une grille derrière un bouton unique, c'est des modifications
 * perdues au premier rafraîchissement mal placé.
 */

import { useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import { formatDuration, formatPrice } from "@/lib/format";
import {
  Badge,
  Button,
  DangerButton,
  ErrorState,
  GhostButton,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { rows, useResource, type Page } from "./useResource";

export interface Option {
  id: string;
  service: string;
  name: string;
  description: string;
  price_delta: string;
  duration_delta_minutes: number;
  position: number;
  active: boolean;
}

export function ServiceOptions({
  tenantId,
  serviceId,
  serviceName,
  baseMinutes,
  currency,
  canEdit,
}: {
  tenantId: string;
  serviceId: string;
  serviceName: string;
  baseMinutes: number;
  currency: string;
  canEdit: boolean;
}) {
  const toast = useToast();
  const options = useResource<Page<Option>>(
    `/api/v1/service-options/?service=${serviceId}`,
    tenantId,
  );
  const [creating, setCreating] = useState(false);

  const list = rows(options.data);
  const active = list.filter((option) => option.active);

  // Ce que dure la prestation si tout est coché : le pire cas, celui qui
  // décide de la plus longue réservation possible.
  const longest =
    baseMinutes +
    active.reduce((total, option) => total + option.duration_delta_minutes, 0);

  async function patch(option: Option, changes: Partial<Option>) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/service-options/${option.id}/`,
          { method: "PATCH", body: JSON.stringify(changes) },
          tenantId,
        ),
      { success: "Option mise à jour." },
    );
    if (ok) options.reload();
  }

  async function remove(option: Option) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/service-options/${option.id}/`,
          { method: "DELETE" },
          tenantId,
        ),
      { success: `« ${option.name} » retirée.` },
    );
    if (ok) options.reload();
  }

  async function create(name: string, price: string, minutes: string) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          "/api/v1/service-options/",
          {
            method: "POST",
            body: JSON.stringify({
              service: serviceId,
              name,
              price_delta: price || "0",
              duration_delta_minutes: Number(minutes) || 0,
              position: list.length,
            }),
          },
          tenantId,
        ),
      { success: `« ${name} » ajoutée à ${serviceName}.` },
    );
    if (ok) {
      options.reload();
      setCreating(false);
    }
    return ok;
  }

  return (
    <div className="rounded-xl border border-line bg-surface-muted/40 p-3 sm:p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-medium text-ink">Options</p>
        {active.length > 0 && (
          <p className="tabular text-xs text-subtle">
            Jusqu&apos;à {formatDuration(longest)} si tout est choisi
          </p>
        )}
      </div>

      {options.error && (
        <ErrorState>Impossible de charger les options.</ErrorState>
      )}
      {options.data === null && !options.error && <Skeleton rows={1} />}

      {options.data !== null && list.length === 0 && !creating && (
        <p className="text-sm text-muted">
          Aucune option. Ajoutez « longueur XL », « mèches fournies », « retrait
          de l&apos;ancienne coiffure »…
        </p>
      )}

      {list.length > 0 && (
        <ul className="space-y-2">
          {list.map((option) => (
            <OptionRow
              key={option.id}
              option={option}
              currency={currency}
              canEdit={canEdit}
              onPatch={(changes) => patch(option, changes)}
              onRemove={() => remove(option)}
            />
          ))}
        </ul>
      )}

      {canEdit && (
        <div className="mt-3">
          {creating ? (
            <NewOption
              currency={currency}
              onCancel={() => setCreating(false)}
              onCreate={create}
            />
          ) : (
            <GhostButton type="button" onClick={() => setCreating(true)}>
              Ajouter une option
            </GhostButton>
          )}
        </div>
      )}
    </div>
  );
}

function OptionRow({
  option,
  currency,
  canEdit,
  onPatch,
  onRemove,
}: {
  option: Option;
  currency: string;
  canEdit: boolean;
  onPatch: (changes: Partial<Option>) => void;
  onRemove: () => void;
}) {
  const [name, setName] = useState(option.name);
  const [price, setPrice] = useState(option.price_delta);
  const [minutes, setMinutes] = useState(String(option.duration_delta_minutes));

  const free = Number(price) === 0;
  const instant = Number(minutes) === 0;

  return (
    <li
      className={`rounded-lg border border-line p-2.5 transition ${
        option.active ? "bg-surface" : "bg-surface-muted opacity-70"
      }`}
    >
      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_7rem_7rem_auto] sm:items-center">
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          onBlur={() => {
            const trimmed = name.trim();
            if (!trimmed) {
              setName(option.name);
              return;
            }
            if (trimmed !== option.name) onPatch({ name: trimmed });
          }}
          disabled={!canEdit}
          aria-label="Nom de l'option"
          className={inputClass}
        />

        <label className="flex items-center gap-1.5">
          <span className="sr-only">Supplément en {currency}</span>
          <input
            value={price}
            onChange={(event) => setPrice(event.target.value)}
            onBlur={() => {
              if (price !== option.price_delta)
                onPatch({ price_delta: price || "0" });
            }}
            disabled={!canEdit}
            inputMode="decimal"
            className={`${inputClass} tabular`}
          />
          <span className="shrink-0 text-xs text-subtle">{currency}</span>
        </label>

        {/* Le temps, à côté du prix et pas ailleurs : c'est lui qui décide
            du créneau, et c'est celui qu'on oublie de remplir. */}
        <label className="flex items-center gap-1.5">
          <span className="sr-only">Temps supplémentaire en minutes</span>
          <input
            value={minutes}
            onChange={(event) => setMinutes(event.target.value)}
            onBlur={() => {
              const next = Math.max(0, Number(minutes) || 0);
              if (next !== option.duration_delta_minutes)
                onPatch({ duration_delta_minutes: next });
            }}
            disabled={!canEdit}
            inputMode="numeric"
            className={`${inputClass} tabular`}
          />
          <span className="shrink-0 text-xs text-subtle">min</span>
        </label>

        <div className="flex flex-wrap items-center justify-between gap-2 sm:justify-end">
          <span className="flex items-center gap-1.5 text-xs">
            {free ? (
              <Badge tone="success">Inclus</Badge>
            ) : (
              <span className="tabular text-muted">
                {formatPrice(price, currency)}
              </span>
            )}
            {!instant && (
              <span className="tabular text-subtle">
                +{formatDuration(Number(minutes))}
              </span>
            )}
          </span>

          {canEdit && (
            <span className="flex items-center gap-1.5">
              <GhostButton
                type="button"
                onClick={() => onPatch({ active: !option.active })}
              >
                {option.active ? "Suspendre" : "Réactiver"}
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

function NewOption({
  currency,
  onCancel,
  onCreate,
}: {
  currency: string;
  onCancel: () => void;
  onCreate: (name: string, price: string, minutes: string) => Promise<boolean>;
}) {
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [minutes, setMinutes] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: { preventDefault: () => void }) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;

    setPending(true);
    await onCreate(trimmed, price, minutes);
    setPending(false);
    setName("");
    setPrice("");
    setMinutes("");
  }

  return (
    /*
      Un <div>, pas un <form> : ce bloc peut se retrouver à l'intérieur d'un
      autre formulaire, et deux <form> imbriqués font recharger la page à la
      première soumission. La touche Entrée est gérée à la main.
    */
    <div
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          void submit(event);
        }
      }}
      className="grid gap-2 rounded-lg border border-dashed border-line p-2.5 sm:grid-cols-[minmax(0,1fr)_7rem_7rem_auto] sm:items-center"
    >
      <input
        autoFocus
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="Longueur XL"
        aria-label="Nom de l'option"
        className={inputClass}
      />
      <label className="flex items-center gap-1.5">
        <span className="sr-only">Supplément en {currency}</span>
        <input
          value={price}
          onChange={(event) => setPrice(event.target.value)}
          placeholder="0"
          inputMode="decimal"
          className={`${inputClass} tabular`}
        />
        <span className="shrink-0 text-xs text-subtle">{currency}</span>
      </label>
      <label className="flex items-center gap-1.5">
        <span className="sr-only">Temps supplémentaire en minutes</span>
        <input
          value={minutes}
          onChange={(event) => setMinutes(event.target.value)}
          placeholder="0"
          inputMode="numeric"
          className={`${inputClass} tabular`}
        />
        <span className="shrink-0 text-xs text-subtle">min</span>
      </label>
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
