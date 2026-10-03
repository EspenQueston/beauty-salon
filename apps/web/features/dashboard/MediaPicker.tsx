"use client";

/**
 * Choix d'une image parmi celles déjà téléversées, ou téléversement direct.
 *
 * Il existe parce que rattacher une photo à une prestation demandait
 * jusqu'ici de passer par l'écran Photos, de retenir laquelle on venait
 * d'ajouter, puis de revenir — un aller-retour que personne ne fait, et
 * c'est pourquoi aucune prestation n'avait d'image.
 *
 * Le téléversement se fait ici même et sélectionne aussitôt le fichier
 * envoyé : le geste courant — « je photographie une réalisation et je
 * l'attache à cette prestation » — tient en une action.
 */

import { useRef, useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import { GhostButton } from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { Icon } from "./icons";

export interface PickableMedia {
  id: string;
  url: string;
  content_type: string;
  alt_text: string;
  kind: string;
  /** « private » : jamais proposé comme illustration. */
  visibility?: string;
}

const IMAGES = "image/jpeg,image/png,image/webp";
const IMAGES_AND_VIDEO = `${IMAGES},video/mp4,video/webm`;
const MAX_BYTES = 15 * 1024 * 1024;

export function MediaPicker({
  tenantId,
  assets,
  value,
  onChange,
  onUploaded,
  label,
  hint,
  kind = "service",
  allowVideo = false,
}: {
  tenantId: string;
  assets: PickableMedia[];
  value: string | null;
  onChange: (id: string | null) => void;
  /** Rappelé après un téléversement, pour rafraîchir la liste. */
  onUploaded: () => void;
  label: string;
  hint?: string;
  kind?: string;
  /**
   * Autorise la vidéo.
   *
   * Faux par défaut : une vignette de prestation ou un portrait n'ont rien à
   * gagner d'une vidéo, et la proposer partout inviterait à téléverser des
   * fichiers lourds là où une photo suffit. La boutique, elle, en tire un
   * vrai bénéfice — une mèche qui bouge se juge mieux qu'une mèche posée.
   */
  allowVideo?: boolean;
}) {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [linking, setLinking] = useState(false);
  const [link, setLink] = useState("");

  /*
    Les preuves de versement ne sont pas des illustrations.

    Le sélecteur reçoit la médiathèque entière. Une capture de paiement —
    le nom d'une cliente, l'heure du virement, parfois son solde — s'y
    affichait donc entre deux photos de coiffure, dans la grille « choisir
    une photo d'article ». Le genre `proof` existe précisément pour la
    distinguer ; il ne servait qu'au mini-site.

    Le filtre porte sur le genre *et* sur la visibilité : un média privé n'a
    rien à faire dans un choix d'illustration, quel que soit son genre.
  */
  const choisissables = assets.filter(
    (asset) => asset.kind !== "proof" && asset.visibility !== "private",
  );

  const images = allowVideo
    ? choisissables
    : choisissables.filter((asset) => !asset.content_type.startsWith("video/"));
  const selected = images.find((asset) => asset.id === value) ?? null;

  async function upload(file: File) {
    if (file.size > MAX_BYTES) {
      toast.error("Fichier trop volumineux : 15 Mo maximum.");
      return;
    }

    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    form.append("alt_text", "");

    try {
      const created = await dashboardFetch<{ id: string }>(
        "/api/v1/media/",
        { method: "POST", body: form },
        tenantId,
      );
      // Sélectionne aussitôt : c'est ce qu'on vient d'envoyer qu'on veut.
      onChange(created.id);
      onUploaded();
      toast.success("Photo ajoutée et rattachée.");
    } catch (caught) {
      toast.error(
        caught instanceof Error ? caught.message : "Envoi impossible.",
      );
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  /**
   * Import depuis une adresse web.
   *
   * Le geste courant quand la photo vient de Pexels ou d'Unsplash : le salon
   * en a l'adresse, pas le fichier. Le media est recopie chez nous plutot que
   * pointe a distance, puis rattache aussitot - comme apres un televersement.
   */
  async function importFromUrl(event: { preventDefault: () => void }) {
    event.preventDefault();
    const trimmed = link.trim();
    if (!trimmed) return;

    setBusy(true);
    try {
      const created = await dashboardFetch<{ id: string }>(
        "/api/v1/media/from-url/",
        { method: "POST", body: JSON.stringify({ url: trimmed, kind }) },
        tenantId,
      );
      onChange(created.id);
      onUploaded();
      setLink("");
      setLinking(false);
      toast.success("Photo importée et rattachée.");
    } catch (caught) {
      toast.error(
        caught instanceof Error ? caught.message : "Import impossible.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>

      <div className="flex flex-wrap items-start gap-3">
        <span className="flex size-20 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-line bg-surface-muted">
          {selected ? (
            selected.content_type.startsWith("video/") ? (
              <video
                src={selected.url}
                muted
                loop
                autoPlay
                playsInline
                preload="metadata"
                aria-label={selected.alt_text || label}
                className="size-full object-cover"
              />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={selected.url}
                alt={selected.alt_text || label}
                className="size-full object-cover"
              />
            )
          ) : (
            <Icon name="image" className="size-6 text-subtle" />
          )}
        </span>

        <div className="min-w-0 flex-1">
          <select
            value={value ?? ""}
            onChange={(event) => onChange(event.target.value || null)}
            aria-label={label}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-sm text-ink"
          >
            <option value="">— Aucune photo —</option>
            {images.map((asset, index) => (
              <option key={asset.id} value={asset.id}>
                {asset.alt_text || `Photo ${index + 1}`}
              </option>
            ))}
          </select>

          <div className="mt-2 flex flex-wrap gap-2">
            <GhostButton
              type="button"
              pending={busy}
              onClick={() => inputRef.current?.click()}
              icon={<Icon name="plus" className="size-4" />}
            >
              Téléverser
            </GhostButton>

            <GhostButton
              type="button"
              onClick={() => setLinking((open) => !open)}
            >
              Coller un lien
            </GhostButton>

            {value && (
              <GhostButton type="button" onClick={() => onChange(null)}>
                Retirer
              </GhostButton>
            )}
          </div>

          {linking && (
            /*
              Un <div>, pas un <form> : ce sélecteur s'affiche à l'intérieur
              du formulaire d'une prestation et de celui du profil. Deux
              <form> imbriqués sont du HTML invalide et font recharger la
              page à la première soumission — en emportant tout ce qui
              n'était pas enregistré.
            */
            <div
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void importFromUrl(event);
                }
              }}
              className="mt-2 flex flex-col gap-2 sm:flex-row"
            >
              <input
                autoFocus
                value={link}
                onChange={(event) => setLink(event.target.value)}
                type="url"
                inputMode="url"
                placeholder="https://images.pexels.com/photos/…"
                aria-label="Adresse de la photo"
                className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
              />
              <GhostButton
                type="button"
                pending={busy}
                disabled={!link.trim()}
                onClick={(event) => void importFromUrl(event)}
              >
                Importer
              </GhostButton>
            </div>
          )}

          {hint && <p className="mt-2 text-xs text-muted">{hint}</p>}
        </div>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={allowVideo ? IMAGES_AND_VIDEO : IMAGES}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) upload(file);
        }}
        className="sr-only"
      />
    </div>
  );
}
