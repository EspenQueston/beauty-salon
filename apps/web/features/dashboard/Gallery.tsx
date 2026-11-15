"use client";

/**
 * Photos du mini-site : galerie, logo, bannière.
 *
 * Le téléversement se fait par lot et affiche l'avancement fichier par
 * fichier : sur un réseau mobile lent, une barre unique qui n'avance pas
 * ressemble à une panne. Chaque échec est nommé — poids, format — plutôt que
 * de faire disparaître silencieusement une photo de la sélection.
 */

import { useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import {
  Badge,
  Button,
  Card,
  DangerButton,
  EmptyState,
  ErrorState,
  GhostButton,
  PageHeader,
  SectionTitle,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { Icon } from "./icons";
import { useDashboard } from "./DashboardShell";
import { rows, useResource, type Page } from "./useResource";

interface Asset {
  id: string;
  url: string;
  content_type: string;
  byte_size: number;
  kind:
    | "gallery"
    | "logo"
    | "banner"
    | "service"
    | "staff"
    | "payment"
    | "about"
    | "product"
    | "proof";
  alt_text: string;
  width: number | null;
  height: number | null;
  position: number;
  featured: boolean;
  /** Ce que montre la photo, et qui l'a faite : de quoi « Réserver ce look ». */
  service: string | null;
  staff_member: string | null;
}

interface Choix {
  id: string;
  name: string;
}

/** Nombre de médias montrés sur l'accueil du mini-site. */
const FEATURED_SLOTS = 6;

interface Profile {
  logo: string | null;
  banner: string | null;
}

const MAX_BYTES = 15 * 1024 * 1024;
const ACCEPT = "image/jpeg,image/png,image/webp,video/mp4,video/webm";

type Traduire = ReturnType<typeof useTranslations>;

/** « 820 Ko », « 2.4 MB » : l'unité suit la langue (`pro.galerie.taille`). */
function humanSize(bytes: number, t: Traduire): string {
  if (bytes < 1024 * 1024) return t("taille.ko", { n: Math.round(bytes / 1024) });
  return t("taille.mo", { n: (bytes / (1024 * 1024)).toFixed(1) });
}

export function Gallery() {
  const t = useTranslations("pro.galerie");
  const { membership } = useDashboard();
  const toast = useToast();
  const tenantId = membership.tenant.id;
  const canEdit = ["owner", "manager"].includes(membership.role);

  const assets = useResource<Page<Asset>>(
    "/api/v1/media/?page_size=100",
    tenantId,
  );
  const profile = useResource<Profile>("/api/v1/salon-profile", tenantId);
  // Pour relier une photo à sa prestation et à qui l'a faite.
  const services = useResource<Page<Choix>>(
    "/api/v1/services/?page_size=200",
    tenantId,
  );
  const equipe = useResource<Page<Choix>>(
    "/api/v1/staff-members/?page_size=100",
    tenantId,
  );
  const prestations = rows(services.data);
  const prestataires = rows(equipe.data);

  const all = rows(assets.data);
  const logoId = profile.data?.logo ?? null;
  const bannerId = profile.data?.banner ?? null;

  /*
   * Le logo et la bannière sortent de la mosaïque.
   *
   * Ils sont téléversés dans la même réserve que les réalisations, donc ils
   * s'y affichaient aussi — un logo de marque au milieu de photos de
   * coiffures, en double avec la section « Identité visuelle » juste
   * au-dessus.
   *
   * Le filtre est appliqué à l'affichage, pas en changeant le type du
   * fichier : retirer le logo le rend à la galerie, sans qu'aucune donnée
   * n'ait été altérée entre-temps.
   */
  const gallery = all.filter(
    (asset) =>
      asset.kind === "gallery" && asset.id !== logoId && asset.id !== bannerId,
  );
  const featuredCount = gallery.filter((asset) => asset.featured).length;
  const identity = all.filter(
    (asset) => asset.id === logoId || asset.id === bannerId,
  );

  async function setIdentity(field: "logo" | "banner", assetId: string | null) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          "/api/v1/salon-profile",
          { method: "PATCH", body: JSON.stringify({ [field]: assetId }) },
          tenantId,
        ),
      {
        success: assetId
          ? t(`identite.${field}.maj`)
          : t(`identite.${field}.retire`),
      },
    );
    if (ok) {
      profile.reload();
      assets.reload();
    }
  }

  async function remove(asset: Asset) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/media/${asset.id}/`,
          { method: "DELETE" },
          tenantId,
        ),
      { success: t("supprimee") },
    );
    if (ok) {
      assets.reload();
      profile.reload();
    }
  }

  /**
   * Met une photo en vitrine, ou l'en retire.
   *
   * La vitrine et l'ordre de la galerie sont deux décisions distinctes :
   * avant, mettre une photo en avant obligeait à la remonter tout en haut
   * de la galerie, donc à renoncer à l'ordre voulu sur la page des
   * réalisations.
   */
  async function toggleFeatured(asset: Asset) {
    const next = !asset.featured;

    if (next && featuredCount >= FEATURED_SLOTS) {
      toast.error(t("vitrinePleine", { n: FEATURED_SLOTS }));
      return;
    }

    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/media/${asset.id}/`,
          { method: "PATCH", body: JSON.stringify({ featured: next }) },
          tenantId,
        ),
      {
        success: next
          ? t("misEnVitrine")
          : t("retireeVitrine"),
      },
    );
    if (ok) assets.reload();
  }

  async function rename(asset: Asset, altText: string) {
    if (altText === asset.alt_text) return;
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/media/${asset.id}/`,
          { method: "PATCH", body: JSON.stringify({ alt_text: altText }) },
          tenantId,
        ),
      { success: t("descriptionOk") },
    );
    if (ok) assets.reload();
  }

  /** Relie la photo à une prestation ou à une prestataire (ou défait le lien). */
  async function relier(
    asset: Asset,
    champ: "service" | "staff_member",
    valeur: string,
  ) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/media/${asset.id}/`,
          {
            method: "PATCH",
            body: JSON.stringify({ [champ]: valeur || null }),
          },
          tenantId,
        ),
      {
        success:
          champ === "service"
            ? valeur
              ? t("prestationReliee")
              : t("prestationRetiree")
            : t("signatureOk"),
      },
    );
    if (ok) assets.reload();
  }

  /** Décale une photo d'un cran : la première est la vitrine. */
  async function move(asset: Asset, direction: -1 | 1) {
    const index = gallery.indexOf(asset);
    const neighbour = gallery[index + direction];
    if (!neighbour) return;

    const ok = await toast.run(
      async () => {
        await dashboardFetch(
          `/api/v1/media/${asset.id}/`,
          {
            method: "PATCH",
            body: JSON.stringify({ position: index + direction }),
          },
          tenantId,
        );
        await dashboardFetch(
          `/api/v1/media/${neighbour.id}/`,
          { method: "PATCH", body: JSON.stringify({ position: index }) },
          tenantId,
        );
      },
      { success: t("ordreOk") },
    );
    if (ok) assets.reload();
  }

  return (
    <section>
      <PageHeader
        title={t("titre")}
        description={t("description")}
      />

      {assets.error && (
        <ErrorState>{t("erreur")}</ErrorState>
      )}

      {canEdit && (
        <Uploader
          tenantId={tenantId}
          onUploaded={() => {
            assets.reload();
            profile.reload();
          }}
        />
      )}

      <div className="mt-8">
        <SectionTitle>{t("identiteVisuelle")}</SectionTitle>
        <div className="grid gap-4 sm:grid-cols-2">
          <IdentitySlot
            field="logo"
            asset={identity.find((a) => a.id === logoId) ?? null}
            hint={t("identite.logo.aide")}
            canEdit={canEdit}
            choices={all}
            onChange={(id) => setIdentity("logo", id)}
          />
          <IdentitySlot
            field="banner"
            asset={identity.find((a) => a.id === bannerId) ?? null}
            hint={t("identite.banner.aide")}
            canEdit={canEdit}
            choices={all}
            onChange={(id) => setIdentity("banner", id)}
          />
        </div>
      </div>

      <div className="mt-8">
        <SectionTitle>
          {t("galerie")}
          {gallery.length > 0 && (
            <span className="ml-2 font-normal normal-case tracking-normal text-subtle">
              {t("compte", { n: gallery.length, vitrine: featuredCount, max: FEATURED_SLOTS })}
            </span>
          )}
        </SectionTitle>

        {gallery.length > 0 && canEdit && (
          <p className="mb-4 flex items-start gap-2 rounded-xl bg-surface-muted p-3 text-sm text-muted">
            <Icon name="star" className="mt-0.5 size-4 shrink-0 text-salon" />
            <span>{t("aideEtoile")}</span>
          </p>
        )}

        {gallery.length > 0 && canEdit && (
          <p className="mb-4 flex items-start gap-2 rounded-xl bg-salon-soft p-3 text-sm text-ink">
            <Icon
              name="sparkles"
              className="mt-0.5 size-4 shrink-0 text-salon"
            />
            <span>
              {t.rich("aideRelier", { gras: (texte) => <strong>{texte}</strong> })}
            </span>
          </p>
        )}

        {assets.data === null && !assets.error && <Skeleton rows={2} />}

        {gallery.length === 0 && assets.data !== null && (
          <EmptyState title={t("vide.titre")}>{t("vide.corps")}</EmptyState>
        )}

        {/*
          Quatre par ligne sur grand écran, deux sur téléphone.

          Une galerie se trie : on cherche une photo pour la mettre en
          vitrine, ou pour la remonter. Trois colonnes obligeaient à faire
          défiler pour comparer deux images qui, à quatre, tiennent côte à
          côte — et laissaient une bande vide à droite sur un écran de
          bureau.
        */}
        <ul className="grid grid-cols-2 gap-2.5 sm:gap-3 md:grid-cols-3 lg:grid-cols-4">
          {gallery.map((asset, index) => (
            <li key={asset.id}>
              <Card padded={false} className="overflow-hidden">
                <div className="relative aspect-[4/3] bg-surface-muted">
                  {asset.content_type.startsWith("video/") ? (
                    <video
                      src={asset.url}
                      controls
                      className="size-full object-cover"
                    />
                  ) : (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={asset.url}
                      alt={asset.alt_text || t("realisation")}
                      className="size-full object-cover"
                    />
                  )}
                  {asset.featured && (
                    <span className="absolute left-2 top-2">
                      <Badge tone="salon">{t("vitrine")}</Badge>
                    </span>
                  )}

                  {canEdit && (
                    <button
                      type="button"
                      onClick={() => toggleFeatured(asset)}
                      aria-pressed={asset.featured}
                      title={
                        asset.featured
                          ? t("retirerVitrine")
                          : t("mettreVitrineAccueil")
                      }
                      className={`absolute right-2 top-2 flex size-9 items-center justify-center rounded-full backdrop-blur transition ${
                        asset.featured
                          ? "bg-salon text-white"
                          : "bg-black/35 text-white/80 hover:bg-black/55 hover:text-white"
                      }`}
                    >
                      <Icon name="star" className="size-4" />
                      <span className="sr-only">
                        {asset.featured ? t("retirerVitrine") : t("mettreVitrine")}
                      </span>
                    </button>
                  )}
                </div>

                <div className="p-4">
                  <input
                    defaultValue={asset.alt_text}
                    onBlur={(event) => rename(asset, event.target.value.trim())}
                    disabled={!canEdit}
                    placeholder={t("decrire")}
                    aria-label={t("description_")}
                    className={inputClass}
                  />
                  <div className="mt-2 grid gap-2">
                    <select
                      value={asset.service ?? ""}
                      onChange={(event) =>
                        relier(asset, "service", event.target.value)
                      }
                      disabled={!canEdit}
                      aria-label={t("prestationMontree")}
                      className={`${inputClass} py-1.5 text-[13px]`}
                    >
                      <option value="">{t("prestationAucune")}</option>
                      {prestations.map((choix) => (
                        <option key={choix.id} value={choix.id}>
                          {choix.name}
                        </option>
                      ))}
                    </select>
                    <select
                      value={asset.staff_member ?? ""}
                      onChange={(event) =>
                        relier(asset, "staff_member", event.target.value)
                      }
                      disabled={!canEdit}
                      aria-label={t("realiseePar")}
                      className={`${inputClass} py-1.5 text-[13px]`}
                    >
                      <option value="">{t("realiseeParAucun")}</option>
                      {prestataires.map((choix) => (
                        <option key={choix.id} value={choix.id}>
                          {choix.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <p className="mt-2 text-xs text-subtle">
                    {asset.width && asset.height
                      ? `${asset.width} × ${asset.height} · `
                      : ""}
                    {humanSize(asset.byte_size, t)}
                  </p>

                  {canEdit && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      <GhostButton
                        type="button"
                        onClick={() => move(asset, -1)}
                        disabled={index === 0}
                        aria-label={t("reculer")}
                      >
                        ←
                      </GhostButton>
                      <GhostButton
                        type="button"
                        onClick={() => move(asset, 1)}
                        disabled={index === gallery.length - 1}
                        aria-label={t("avancer")}
                      >
                        →
                      </GhostButton>
                      <DangerButton
                        type="button"
                        onClick={() => remove(asset)}
                        className="ml-auto"
                      >
                        {t("supprimer")}
                      </DangerButton>
                    </div>
                  )}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      </div>

      {!canEdit && (
        <p className="mt-6 text-sm text-muted">
          {t("lectureSeule")}
        </p>
      )}
    </section>
  );
}

function IdentitySlot({
  field,
  asset,
  hint,
  canEdit,
  choices,
  onChange,
}: {
  field: "logo" | "banner";
  asset: Asset | null;
  hint: string;
  canEdit: boolean;
  choices: Asset[];
  onChange: (assetId: string | null) => void;
}) {
  const t = useTranslations("pro.galerie");
  const libelle = t(`identite.${field}.titre`);
  const images = choices.filter(
    (item) => !item.content_type.startsWith("video/"),
  );

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-ink">{libelle}</p>
          <p className="mt-0.5 text-xs text-muted">{hint}</p>
        </div>
        {asset && canEdit && (
          <GhostButton type="button" onClick={() => onChange(null)}>
            {t("retirer")}
          </GhostButton>
        )}
      </div>

      <div
        className={`mt-3 overflow-hidden rounded-xl border border-line bg-surface-muted ${
          field === "logo" ? "aspect-square max-w-[9rem]" : "aspect-[3/1]"
        }`}
      >
        {asset ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={asset.url}
            alt={asset.alt_text || libelle}
            className="size-full object-cover"
          />
        ) : (
          <div className="flex size-full items-center justify-center text-subtle">
            <Icon name="image" className="size-7" />
          </div>
        )}
      </div>

      {canEdit && images.length > 0 && (
        <select
          value={asset?.id ?? ""}
          onChange={(event) => onChange(event.target.value || null)}
          aria-label={t(`identite.${field}.choisir`)}
          className={`${inputClass} mt-3`}
        >
          <option value="">{t("aucune")}</option>
          {images.map((item, index) => (
            <option key={item.id} value={item.id}>
              {item.alt_text || t("numero", { n: index + 1 })}
            </option>
          ))}
        </select>
      )}
    </Card>
  );
}

interface UploadItem {
  name: string;
  state: "pending" | "done" | "failed";
  message?: string;
}

function Uploader({
  tenantId,
  onUploaded,
}: {
  tenantId: string;
  onUploaded: () => void;
}) {
  const t = useTranslations("pro.galerie.envoi");
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [queue, setQueue] = useState<UploadItem[]>([]);
  const [busy, setBusy] = useState(false);

  async function upload(files: FileList | File[]) {
    const list = Array.from(files);
    if (list.length === 0) return;

    setBusy(true);
    setQueue(list.map((file) => ({ name: file.name, state: "pending" })));

    let succeeded = 0;
    const failures: string[] = [];

    for (const [index, file] of list.entries()) {
      // Contrôle côté navigateur avant d'envoyer 15 Mo pour rien : le
      // serveur refuserait de toute façon, mais après le transfert.
      if (file.size > MAX_BYTES) {
        failures.push(file.name);
        setQueue((current) =>
          current.map((item, position) =>
            position === index
              ? { ...item, state: "failed", message: t("tropLourd") }
              : item,
          ),
        );
        continue;
      }

      const form = new FormData();
      form.append("file", file);
      form.append("kind", "gallery");
      form.append("alt_text", "");

      try {
        await dashboardFetch(
          "/api/v1/media/",
          { method: "POST", body: form },
          tenantId,
        );
        succeeded += 1;
        setQueue((current) =>
          current.map((item, position) =>
            position === index ? { ...item, state: "done" } : item,
          ),
        );
      } catch (caught) {
        failures.push(file.name);
        setQueue((current) =>
          current.map((item, position) =>
            position === index
              ? {
                  ...item,
                  state: "failed",
                  message:
                    caught instanceof Error
                      ? caught.message
                      : t("impossible"),
                }
              : item,
          ),
        );
      }
    }

    setBusy(false);
    if (inputRef.current) inputRef.current.value = "";

    if (succeeded > 0) {
      toast.success(
        succeeded === 1 ? t("uneAjoutee") : t("ajoutees", { n: succeeded }),
      );
      onUploaded();
    }
    if (failures.length > 0) {
      toast.error(
        failures.length === 1
          ? t("unEchec", { nom: failures[0] })
          : t("echecs", { n: failures.length }),
      );
    }
    // Laisse la liste visible un instant : elle dit quel fichier a échoué.
    setTimeout(() => setQueue([]), 6000);
  }

  return (
    <div>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          upload(event.dataTransfer.files);
        }}
        className={`rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${
          dragging
            ? "border-salon bg-salon-soft"
            : "border-line-strong bg-surface/60"
        }`}
      >
        <Icon name="image" className="mx-auto size-8 text-subtle" />
        <p className="mt-3 font-medium text-ink">{t("deposer")}</p>
        <p className="mx-auto mt-1.5 max-w-sm text-sm text-muted">
          {t("formats")}
        </p>

        <div className="mt-5">
          <Button
            type="button"
            pending={busy}
            onClick={() => inputRef.current?.click()}
            icon={<Icon name="plus" className="size-4" />}
          >
            {t("choisir")}
          </Button>
        </div>

        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          onChange={(event) => event.target.files && upload(event.target.files)}
          className="sr-only"
        />

        {/*
          Le second chemin : coller une adresse.

          C'est le geste naturel quand la photo vient de Pexels ou d'Unsplash
          — le salon en a l'adresse, pas le fichier. Sans cette entrée, il
          fallait télécharger puis retéléverser : deux étapes de plus sur un
          téléphone, là où tout se joue.
        */}
        <FromUrl tenantId={tenantId} onImported={onUploaded} />
      </div>

      {queue.length > 0 && (
        <ul className="mt-4 space-y-1.5">
          {queue.map((item, index) => (
            <li
              key={`${item.name}-${index}`}
              className="flex items-center gap-2 text-sm"
            >
              <span
                className={
                  item.state === "done"
                    ? "text-success"
                    : item.state === "failed"
                      ? "text-danger"
                      : "text-subtle"
                }
              >
                {item.state === "done"
                  ? "✓"
                  : item.state === "failed"
                    ? "✕"
                    : "…"}
              </span>
              <span className="truncate text-ink">{item.name}</span>
              {item.message && (
                <span className="text-xs text-danger">{item.message}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Import d'un média par son adresse web.
 *
 * Replié par défaut : la majorité des salons téléverse depuis son téléphone,
 * et un champ d'URL toujours ouvert ferait hésiter entre deux chemins pour
 * un geste qui n'en demande qu'un.
 *
 * Le fichier est recopié sur nos serveurs, pas pointé à distance : un
 * mini-site ne doit pas dépendre d'un hébergeur tiers pour s'afficher, et
 * beaucoup refusent d'être affichés depuis un autre domaine.
 */
function FromUrl({
  tenantId,
  onImported,
}: {
  tenantId: string;
  onImported: () => void;
}) {
  const t = useTranslations("pro.galerie.lien");
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;

    setBusy(true);
    const ok = await toast.run(
      () =>
        dashboardFetch(
          "/api/v1/media/from-url/",
          {
            method: "POST",
            body: JSON.stringify({ url: trimmed, kind: "gallery" }),
          },
          tenantId,
        ),
      { success: t("importe") },
    );
    setBusy(false);

    if (ok) {
      setUrl("");
      setOpen(false);
      onImported();
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-3 text-sm text-muted underline-offset-2 hover:text-ink hover:underline"
      >
        {t("ouvrir")}
      </button>
    );
  }

  return (
    <form
      onSubmit={(event) => void submit(event)}
      className="mx-auto mt-4 flex max-w-md flex-col gap-2 sm:flex-row"
    >
      <input
        autoFocus
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        type="url"
        inputMode="url"
        placeholder="https://images.pexels.com/photos/…"
        aria-label={t("adresse")}
        className={inputClass}
      />
      <div className="flex items-center justify-center gap-2">
        <Button type="submit" pending={busy} disabled={!url.trim()}>
          {t("importer")}
        </Button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setUrl("");
          }}
          className="rounded-lg px-2 py-2 text-sm text-muted transition hover:text-ink"
        >
          {t("annuler")}
        </button>
      </div>
    </form>
  );
}
