"use client";

/**
 * Vos QR codes d'encaissement.
 *
 * ---------------------------------------------------------------------------
 * Ce que le salon publie ici
 * ---------------------------------------------------------------------------
 *
 * Le QR code de son propre compte WeChat Pay ou Alipay. L'argent de ses
 * clientes ira directement dessus : la plateforme n'est jamais sur le chemin,
 * ne détient rien, ne prélève rien.
 *
 * C'est aussi ce qui rend cet écran sensible. Un QR code publié ici s'affiche
 * à toute personne qui réserve — c'est le but — mais un code erroné envoie
 * l'argent des clientes sur le compte de quelqu'un d'autre, et personne ne
 * s'en aperçoit avant la première réclamation. D'où l'aperçu à taille réelle
 * et l'avertissement explicite avant publication.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi seulement WeChat et Alipay
 * ---------------------------------------------------------------------------
 *
 * Parce que ce sont les deux moyens utilisés là où sont les premiers salons.
 * Le modèle accepte déjà Mobile Money, Airtel et Orange Money pour
 * Brazzaville et Kinshasa ; ils s'afficheront quand ces salons arriveront.
 */

import { useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import {
  Badge,
  Card,
  GhostButton,
  SectionTitle,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { MediaPicker, type PickableMedia } from "./MediaPicker";
import { rows, useResource, type Page } from "./useResource";

interface Channel {
  id: string;
  kind: string;
  kind_label: string;
  qr_image: string | null;
  qr_url: string;
  account_name: string;
  instructions: string;
  active: boolean;
  usable: boolean;
}

/**
 * Moyens proposés à la création.
 *
 * La liste du serveur en contient davantage — Mobile Money, Airtel, Orange —
 * mais les proposer maintenant à des salons chinois encombrerait le choix
 * pour rien.
 */
const OFFERED = [
  { value: "wechat", label: "WeChat Pay" },
  { value: "alipay", label: "Alipay" },
];

export function PaymentChannels({
  tenantId,
  canEdit,
  media,
  onMediaChanged,
}: {
  tenantId: string;
  canEdit: boolean;
  media: PickableMedia[];
  onMediaChanged: () => void;
}) {
  const toast = useToast();
  const channels = useResource<Page<Channel>>("/api/v1/payment-channels/", tenantId);
  const list = rows(channels.data);

  const missing = OFFERED.filter(
    (option) => !list.some((channel) => channel.kind === option.value),
  );

  async function create(kind: string) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          "/api/v1/payment-channels/",
          { method: "POST", body: JSON.stringify({ kind, position: list.length }) },
          tenantId,
        ),
      { success: "Moyen ajouté. Téléversez votre QR code." },
    );
    if (ok) channels.reload();
  }

  async function patch(channel: Channel, changes: Partial<Channel>) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/payment-channels/${channel.id}/`,
          { method: "PATCH", body: JSON.stringify(changes) },
          tenantId,
        ),
      { success: "Enregistré." },
    );
    if (ok) channels.reload();
  }

  async function remove(channel: Channel) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/payment-channels/${channel.id}/`,
          { method: "DELETE" },
          tenantId,
        ),
      { success: `${channel.kind_label} retiré.` },
    );
    if (ok) channels.reload();
  }

  return (
    <Card id="encaissement">
      <SectionTitle>Encaisser les acomptes</SectionTitle>
      <p className="-mt-2 mb-4 text-sm text-muted">
        Publiez le QR code de votre compte : vos clientes régleront leur
        acompte dessus avant de venir. L&apos;argent arrive directement chez
        vous — nous ne le touchons jamais.
      </p>

      {channels.data === null && !channels.error && <Skeleton rows={1} />}

      {list.length === 0 && channels.data !== null && (
        <p className="mb-3 text-sm text-muted">
          Sans QR code, vos clientes réservent sans rien régler et vous
          encaissez sur place, comme aujourd&apos;hui.
        </p>
      )}

      {list.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2">
          {list.map((channel) => (
            <li key={channel.id}>
              <ChannelCard
                channel={channel}
                tenantId={tenantId}
                canEdit={canEdit}
                media={media}
                onMediaChanged={onMediaChanged}
                onPatch={(changes) => patch(channel, changes)}
                onRemove={() => remove(channel)}
              />
            </li>
          ))}
        </ul>
      )}

      {canEdit && missing.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {missing.map((option) => (
            <GhostButton
              key={option.value}
              type="button"
              onClick={() => create(option.value)}
            >
              Ajouter {option.label}
            </GhostButton>
          ))}
        </div>
      )}
    </Card>
  );
}

function ChannelCard({
  channel,
  tenantId,
  canEdit,
  media,
  onMediaChanged,
  onPatch,
  onRemove,
}: {
  channel: Channel;
  tenantId: string;
  canEdit: boolean;
  media: PickableMedia[];
  onMediaChanged: () => void;
  onPatch: (changes: Partial<Channel>) => void;
  onRemove: () => void;
}) {
  const [name, setName] = useState(channel.account_name);
  const [instructions, setInstructions] = useState(channel.instructions);

  return (
    <div
      className={`rounded-xl border p-3 transition ${
        channel.active && channel.usable
          ? "border-line bg-surface"
          : "border-dashed border-line bg-surface-muted"
      }`}
    >
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium text-ink">{channel.kind_label}</p>
        {channel.usable ? (
          <Badge tone="success">Proposé</Badge>
        ) : (
          <Badge tone="warning">QR manquant</Badge>
        )}
      </div>

      {/* L'aperçu est à taille réelle, pas en vignette : un QR code trop
          petit pour être scanné ne permet pas de vérifier qu'il est le bon,
          et c'est exactement l'erreur qui envoie l'argent ailleurs. */}
      {channel.qr_url && (
        <span className="mb-2.5 block w-fit rounded-xl bg-white p-2 ring-1 ring-line">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={channel.qr_url}
            alt={`QR code ${channel.kind_label}`}
            className="size-32 object-contain"
          />
        </span>
      )}

      <MediaPicker
        tenantId={tenantId}
        assets={media}
        value={channel.qr_image}
        onChange={(id) => onPatch({ qr_image: id })}
        onUploaded={onMediaChanged}
        label="QR code"
        hint="La capture de votre code depuis l'application."
        // Surtout pas « gallery » : le genre décide de ce qui apparaît sur la
        // page Réalisations du mini-site. Un QR téléversé puis jamais
        // rattaché y restait pour toujours, entre deux coiffures.
        kind="payment"
      />

      <label className="mt-3 block">
        <span className="mb-1 block text-xs text-muted">Nom du compte</span>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          onBlur={() => {
            if (name !== channel.account_name) onPatch({ account_name: name });
          }}
          disabled={!canEdit}
          placeholder="Ce que la cliente verra en scannant"
          className={inputClass}
        />
      </label>

      <label className="mt-2 block">
        <span className="mb-1 block text-xs text-muted">Précision</span>
        <input
          value={instructions}
          onChange={(event) => setInstructions(event.target.value)}
          onBlur={() => {
            if (instructions !== channel.instructions)
              onPatch({ instructions });
          }}
          disabled={!canEdit}
          placeholder="« Mettez votre nom en commentaire »"
          className={inputClass}
        />
      </label>

      {canEdit && (
        <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-line pt-2.5">
          <button
            type="button"
            onClick={() => onPatch({ active: !channel.active })}
            className="text-xs text-muted underline-offset-2 hover:text-ink hover:underline"
          >
            {channel.active ? "Suspendre" : "Réactiver"}
          </button>
          <span aria-hidden className="text-subtle">
            ·
          </span>
          <button
            type="button"
            onClick={onRemove}
            className="text-xs text-danger underline-offset-2 hover:underline"
          >
            Supprimer
          </button>
        </div>
      )}
    </div>
  );
}
