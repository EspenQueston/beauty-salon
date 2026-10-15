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
 * Quels moyens
 * ---------------------------------------------------------------------------
 *
 * Ceux qui existent dans le pays du salon, tels que le serveur les donne
 * (`/payment-channels/disponibles/`) : WeChat Pay et Alipay en Chine ; Mobile
 * Money, Orange ou Airtel Money là où l'opérateur est présent, et virement,
 * en Afrique. Ceux-là se règlent avec un numéro que la cliente compose : le
 * QR code y devient facultatif, et c'est le numéro qu'on demande.
 */

import { useTranslations } from "next-intl";
import { useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import { nomDuMoyen, parNumero } from "./moyens";
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
  /** Faux si le moyen n'existe pas dans le pays du salon : plus proposé. */
  propose: boolean;
}

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
  const t = useTranslations("pro.encaissement");
  const toast = useToast();
  const libelle = (kind: string) => nomDuMoyen(kind, t("virement"));
  const channels = useResource<Page<Channel>>(
    "/api/v1/payment-channels/",
    tenantId,
  );
  const list = rows(channels.data);
  // Les moyens du pays du salon, décidés par le serveur (qui refuse les autres).
  const disponibles = useResource<{ kind: string }[]>(
    "/api/v1/payment-channels/disponibles/",
    tenantId,
  );
  const missing = (disponibles.data ?? [])
    .map((item) => item.kind)
    .filter((kind) => !list.some((channel) => channel.kind === kind));

  async function create(kind: string) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          "/api/v1/payment-channels/",
          {
            method: "POST",
            body: JSON.stringify({ kind, position: list.length }),
          },
          tenantId,
        ),
      { success: t(parNumero(kind) ? "ajouteNumero" : "ajoute") },
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
      { success: t("enregistre") },
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
      { success: t("retire", { moyen: libelle(channel.kind) }) },
    );
    if (ok) channels.reload();
  }

  return (
    <Card id="encaissement">
      <SectionTitle>{t("titre")}</SectionTitle>
      <p className="-mt-2 mb-4 text-sm text-muted">{t("intro")}</p>

      {channels.data === null && !channels.error && <Skeleton rows={1} />}

      {list.length === 0 && channels.data !== null && (
        <p className="mb-3 text-sm text-muted">
          {t("sansQr")}
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
        <div className="mt-3 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
          {missing.map((kind) => (
            <GhostButton key={kind} type="button" onClick={() => create(kind)}>
              {t("ajouter", { moyen: libelle(kind) })}
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
  const t = useTranslations("pro.encaissement");
  const [name, setName] = useState(channel.account_name);
  const [instructions, setInstructions] = useState(channel.instructions);
  const nom = nomDuMoyen(channel.kind, t("virement"));
  // Mobile Money, virement : un numéro ou des coordonnées, pas d'abord un QR.
  const numero = parNumero(channel.kind);
  const banque = channel.kind === "bank";

  return (
    <div
      className={`rounded-xl border p-3 transition ${
        channel.active && channel.usable && channel.propose
          ? "border-line bg-surface"
          : "border-dashed border-line bg-surface-muted"
      }`}
    >
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium text-ink">{nom}</p>
        {!channel.propose ? (
          <Badge tone="warning">{t("horsPays")}</Badge>
        ) : channel.usable ? (
          <Badge tone="success">{t("propose")}</Badge>
        ) : (
          <Badge tone="warning">{t(numero ? "numeroManquant" : "qrManquant")}</Badge>
        )}
      </div>

      {numero ? (
        // Mobile Money, virement : le numéro d'abord — c'est lui que la
        // cliente compose. Le QR code reste possible, replié.
        <>
          <label className="block">
            <span className="mb-1 block text-xs text-muted">
              {t(banque ? "coordonnees" : numero ? "numero" : "precision")}
            </span>
            <input
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              onBlur={() => {
                if (instructions !== channel.instructions)
                  onPatch({ instructions });
              }}
              disabled={!canEdit}
              placeholder={t(banque ? "coordonneesExemple" : numero ? "numeroExemple" : "precisionExemple")}
              className={inputClass}
            />
          </label>
          <label className="mt-2 block">
            <span className="mb-1 block text-xs text-muted">{t(numero ? "titulaire" : "compte")}</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              onBlur={() => {
                if (name !== channel.account_name) onPatch({ account_name: name });
              }}
              disabled={!canEdit}
              placeholder={t(numero ? "titulaireExemple" : "compteExemple")}
              className={inputClass}
            />
          </label>
          <details className="mt-3" open={!!channel.qr_url}>
            <summary className="min-h-9 cursor-pointer py-1 text-xs font-medium text-muted hover:text-ink">
              {t("qrFacultatif")}
            </summary>
            <div className="mt-2">
              {/* L'aperçu est à taille réelle, pas en vignette : un QR code trop
                  petit pour être scanné ne permet pas de vérifier qu'il est le bon,
                  et c'est exactement l'erreur qui envoie l'argent ailleurs. */}
              {channel.qr_url && (
                <span className="mb-2.5 block w-fit rounded-xl bg-white p-2 ring-1 ring-line">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={channel.qr_url}
                    alt={t("qrDe", { moyen: nom })}
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
                label={numero ? t("qrFacultatif") : t("qr")}
                hint={t("qrAide")}
                // Surtout pas « gallery » : le genre décide de ce qui apparaît sur la
                // page Réalisations du mini-site. Un QR téléversé puis jamais
                // rattaché y restait pour toujours, entre deux coiffures.
                kind="payment"
              />
            </div>
          </details>
        </>
      ) : (
        <>
          {/* L'aperçu est à taille réelle, pas en vignette : un QR code trop
              petit pour être scanné ne permet pas de vérifier qu'il est le bon,
              et c'est exactement l'erreur qui envoie l'argent ailleurs. */}
          {channel.qr_url && (
            <span className="mb-2.5 block w-fit rounded-xl bg-white p-2 ring-1 ring-line">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={channel.qr_url}
                alt={t("qrDe", { moyen: nom })}
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
            label={numero ? t("qrFacultatif") : t("qr")}
            hint={t("qrAide")}
            // Surtout pas « gallery » : le genre décide de ce qui apparaît sur la
            // page Réalisations du mini-site. Un QR téléversé puis jamais
            // rattaché y restait pour toujours, entre deux coiffures.
            kind="payment"
          />

          <label className="mt-3 block">
            <span className="mb-1 block text-xs text-muted">{t(numero ? "titulaire" : "compte")}</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              onBlur={() => {
                if (name !== channel.account_name) onPatch({ account_name: name });
              }}
              disabled={!canEdit}
              placeholder={t(numero ? "titulaireExemple" : "compteExemple")}
              className={inputClass}
            />
          </label>

          <label className="mt-2 block">
            <span className="mb-1 block text-xs text-muted">
              {t(banque ? "coordonnees" : numero ? "numero" : "precision")}
            </span>
            <input
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              onBlur={() => {
                if (instructions !== channel.instructions)
                  onPatch({ instructions });
              }}
              disabled={!canEdit}
              placeholder={t(banque ? "coordonneesExemple" : numero ? "numeroExemple" : "precisionExemple")}
              className={inputClass}
            />
          </label>
        </>
      )}

      {canEdit && (
        <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-line pt-2.5">
          <button
            type="button"
            onClick={() => onPatch({ active: !channel.active })}
            className="text-xs text-muted underline-offset-2 hover:text-ink hover:underline"
          >
            {channel.active ? t("suspendre") : t("reactiver")}
          </button>
          <span aria-hidden className="text-subtle">
            ·
          </span>
          <button
            type="button"
            onClick={onRemove}
            className="text-xs text-danger underline-offset-2 hover:underline"
          >
            {t("supprimer")}
          </button>
        </div>
      )}
    </div>
  );
}
