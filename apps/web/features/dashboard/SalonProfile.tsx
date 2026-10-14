"use client";

/**
 * Profil du salon : vitrine, coordonnées, apparence, règles de réservation.
 *
 * Les réglages de réservation sont regroupés à part parce qu'ils ne changent
 * pas l'affichage mais le comportement du moteur de créneaux : les modifier
 * à l'aveugle déplace de vrais rendez-vous. Chaque champ dit donc son effet.
 */

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { adjustForContrast } from "@/lib/contrast";
import { dashboardFetch } from "@/lib/dashboard";
import { formatPrice } from "@/lib/format";
import { formatDuration } from "@/lib/format";
import {
  Button,
  Card,
  ErrorState,
  Field,
  PageHeader,
  SectionTitle,
  Skeleton,
  Toggle,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { PALETTES } from "@/features/site/palettes";
import { Icon } from "./icons";
import { ContrastMeter } from "./ContrastMeter";
import { MediaPicker, type PickableMedia } from "./MediaPicker";
import { CurrencySwitch } from "./CurrencySwitch";
import { PaymentChannels } from "./PaymentChannels";
import { TravelZones } from "./TravelZones";
import { rows, useResource, type Page } from "./useResource";
import { SectionNav, type NavSection } from "./SectionNav";
import { useDashboard } from "./DashboardShell";
import { useFormats } from "./formats";

interface Profile {
  description: string;
  address: string;
  city: string;
  service_mode: "salon" | "home" | "hybrid";
  service_area: string;
  latitude: string | null;
  longitude: string | null;
  phone: string;
  whatsapp_number: string;
  contact_email: string;
  social_links: Record<string, string>;
  wechat_id: string;
  wechat_qr: string | null;
  theme_config: { primary?: string; accent?: string; surface?: string };
  about_title: string;
  about_content: string;
  about_image: string | null;
  deposit_rate: number;
  deposit_minimum: string;
  deposit_covers_items: boolean;
  cancellation_policy: string;
  cancellation_deadline_hours: number;
  late_policy: string;
  late_tolerance_minutes: number;
  slot_granularity_minutes: number;
  buffer_minutes: number;
  min_lead_time_minutes: number;
  max_advance_days: number;
}

const NETWORKS = [
  { key: "instagram", label: "Instagram" },
  { key: "tiktok", label: "TikTok" },
  { key: "facebook", label: "Facebook" },
] as const;

/** Ordre de la barre de sections : celui de la page, pas un autre. */
const PROFILE_SECTIONS = [
  "vitrine",
  "reseaux",
  "couleurs",
  "apropos",
  "regles",
  "deplacement",
  "acompte",
  "devise",
  "encaissement",
  "annulation",
  "retard",
];

const DEFAULT_PRIMARY = "#B4436C";
const DEFAULT_ACCENT = "#F2C4CE";
const DEFAULT_SURFACE = "#FAF7F8";

export function SalonProfileScreen() {
  const t = useTranslations("pro.profil");
  const site = useTranslations("site");
  const { region } = useFormats();
  const sections: NavSection[] = PROFILE_SECTIONS.map((id) => ({
    id,
    label: t(`sections.${id}`),
  }));
  const { membership, user } = useDashboard();
  const toast = useToast();
  const tenantId = membership.tenant.id;
  const canEdit = ["owner", "manager"].includes(membership.role);

  // La reserve de medias sert au choix de la photo « A propos ». Elle est
  // chargee ici plutot que dans le selecteur : un rechargement apres
  // televersement doit rafraichir la liste, pas remonter le composant.
  const media = useResource<Page<PickableMedia>>(
    "/api/v1/media/?page_size=100",
    tenantId,
  );

  const [profile, setProfile] = useState<Profile | null>(null);
  const [saved, setSaved] = useState<Profile | null>(null);
  const [error, setError] = useState(false);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    dashboardFetch<Profile>("/api/v1/salon-profile", {}, tenantId)
      .then((data) => {
        if (cancelled) return;
        setProfile(data);
        setSaved(data);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [tenantId]);

  const dirty = useMemo(
    () => JSON.stringify(profile) !== JSON.stringify(saved),
    [profile, saved],
  );

  function set<K extends keyof Profile>(key: K, value: Profile[K]) {
    setProfile((current) => (current ? { ...current, [key]: value } : current));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!profile) return;
    setPending(true);

    // Le serveur dit combien de prestations il a ouvertes au domicile quand
    // le mode du salon vient de changer. Un effet de bord se raconte : sans
    // cette phrase, la gérante découvrirait plus tard que son catalogue a
    // changé de lieu sans qu'elle l'ait touché.
    let alignees = 0;

    const ok = await toast.run(
      async () => {
        const reponse = await dashboardFetch<
          Profile & { prestations_alignees?: number }
        >(
          "/api/v1/salon-profile",
          { method: "PATCH", body: JSON.stringify(profile) },
          tenantId,
        );
        alignees = reponse.prestations_alignees ?? 0;
      },
      { success: t("ok") },
    );

    setPending(false);
    if (ok) {
      setSaved(profile);
      if (alignees > 0) {
        toast.info(t("alignees", { n: alignees }));
      }
    }
  }

  if (error) {
    return (
      <section>
        <PageHeader title={t("titre")} />
        <ErrorState>{t("erreur")}</ErrorState>
      </section>
    );
  }

  if (!profile) {
    return (
      <section>
        <PageHeader title={t("titre")} />
        <Skeleton rows={5} />
      </section>
    );
  }

  const theme = profile.theme_config ?? {};
  const primary = theme.primary ?? DEFAULT_PRIMARY;
  const accent = theme.accent ?? DEFAULT_ACCENT;
  const surface = theme.surface ?? DEFAULT_SURFACE;

  /*
    L'aperçu doit montrer ce que verra la cliente.

    Sur une pastille, le mini-site ne pose pas la couleur de marque brute :
    il la fonce juste assez pour rester lisible sur la couleur secondaire
    (`themeToCssVars`, lib/format.ts). Peindre ici la couleur brute donnait
    un aperçu plus pâle que le site réel — c'est-à-dire un aperçu qui ment.
  */
  const encrePastille = adjustForContrast(primary, accent, 4.5) ?? primary;

  return (
    <section>
      <PageHeader
        title={t("titre")}
        description={t("description")}
      />

      {/* Six blocs sur trois écrans : la barre évite de les parcourir à
          l'aveugle, et dit laquelle on est en train de remplir. */}
      <SectionNav sections={sections} />

      <form onSubmit={submit} className="space-y-6 pb-24">
        {/* ---------------------------------------------------------- vitrine */}
        <Card id="vitrine">
          <SectionTitle>{t("vitrine.titre")}</SectionTitle>

          <Field
            label={t("vitrine.presentation")}
            hint={t("vitrine.presentationAide")}
          >
            <textarea
              value={profile.description}
              onChange={(event) => set("description", event.target.value)}
              disabled={!canEdit}
              rows={4}
              className={inputClass}
            />
          </Field>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label={t("vitrine.adresse")}>
              <input
                value={profile.address}
                onChange={(event) => set("address", event.target.value)}
                disabled={!canEdit}
                className={inputClass}
              />
            </Field>
            <Field label={t("vitrine.ville")}>
              <input
                value={profile.city}
                onChange={(event) => set("city", event.target.value)}
                disabled={!canEdit}
                className={inputClass}
              />
            </Field>
            <Field label={t("vitrine.telephone")}>
              <input
                value={profile.phone}
                onChange={(event) => set("phone", event.target.value)}
                disabled={!canEdit}
                className={inputClass}
              />
            </Field>
            <Field
              label="WhatsApp"
              hint={t("vitrine.whatsappAide")}
            >
              <input
                value={profile.whatsapp_number}
                onChange={(event) => set("whatsapp_number", event.target.value)}
                disabled={!canEdit}
                placeholder="+242…"
                className={inputClass}
              />
            </Field>
            <Field
              label={t("vitrine.email")}
              hint={t("vitrine.emailAide")}
            >
              <div className="flex gap-2">
                <input
                  type="email"
                  value={profile.contact_email ?? ""}
                  onChange={(event) => set("contact_email", event.target.value)}
                  disabled={!canEdit}
                  placeholder={t("vitrine.emailExemple")}
                  autoComplete="email"
                  className={inputClass}
                />
                {canEdit && !profile.contact_email && user.email && (
                  <button
                    type="button"
                    onClick={() => set("contact_email", user.email)}
                    className="shrink-0 rounded-lg border border-line px-3 text-xs font-medium text-ink transition hover:bg-surface-hover"
                    title={t("vitrine.utiliser", { email: user.email })}
                  >
                    {t("vitrine.monEmail")}
                  </button>
                )}
              </div>
            </Field>
            {/*
              Ce réglage en commande un autre, et il faut le dire.

              Chaque prestation porte son propre lieu. Passer ici à « à
              domicile » sans que le catalogue suive donnait un parcours de
              réservation qui n'offrait jamais le déplacement : les zones
              déclarées plus bas ne servaient à rien, et le symptôme ne
              désignait pas sa cause. Le serveur aligne donc les prestations
              qui n'avaient pas été réglées à part — autant l'annoncer avant
              plutôt que de le faire découvrir.
            */}
            <Field
              label={t("vitrine.lieu")}
              className="sm:col-span-2"
              hint={
                profile.service_mode === "salon"
                  ? t("vitrine.lieuSalon")
                  : t("vitrine.lieuDomicile")
              }
            >
              <select
                value={profile.service_mode}
                onChange={(event) =>
                  set(
                    "service_mode",
                    event.target.value as Profile["service_mode"],
                  )
                }
                disabled={!canEdit}
                className={inputClass}
              >
                <option value="salon">{t("vitrine.lieux.salon")}</option>
                <option value="home">{t("vitrine.lieux.home")}</option>
                <option value="hybrid">{t("vitrine.lieux.hybrid")}</option>
              </select>
            </Field>
          </div>
        </Card>

        {/* --------------------------------------------------------- réseaux */}
        <Card id="reseaux">
          <SectionTitle>{t("reseaux.titre")}</SectionTitle>
          <div className="grid gap-4 sm:grid-cols-2">
            {NETWORKS.map((network) => (
              <Field key={network.key} label={network.label}>
                <input
                  value={profile.social_links?.[network.key] ?? ""}
                  onChange={(event) =>
                    set("social_links", {
                      ...profile.social_links,
                      [network.key]: event.target.value,
                    })
                  }
                  disabled={!canEdit}
                  placeholder="https://…"
                  className={inputClass}
                />
              </Field>
            ))}
          </div>

          {/*
            WeChat ne s'ajoute pas par une adresse.

            Les autres réseaux se partagent par un lien qu'on ouvre. WeChat se
            rejoint en scannant un QR, ou en tapant un identifiant dans la
            barre de recherche — d'où deux champs à part, sous les liens.

            Les deux, et pas l'un au choix : le QR sert quand la cliente lit
            la page sur un écran qu'elle peut scanner, l'identifiant quand
            elle la lit *dans* WeChat, où l'on ne peut pas scanner son propre
            téléphone. Le mini-site affiche ce que vous remplissez ici.
          */}
          <div className="mt-6 border-t border-line pt-5">
            <h3 className="text-sm font-semibold text-ink">
              {t("reseaux.wechat")}
            </h3>
            <p className="mt-1 text-sm text-muted">{t("reseaux.wechatAide")}</p>

            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <Field
                label={t("reseaux.wechatId")}
                hint={t("reseaux.wechatIdAide")}
              >
                <input
                  value={profile.wechat_id ?? ""}
                  onChange={(event) => set("wechat_id", event.target.value)}
                  disabled={!canEdit}
                  placeholder="salon-beaute-gz"
                  maxLength={64}
                  className={inputClass}
                />
              </Field>
            </div>

            <div className="mt-4">
              <MediaPicker
                tenantId={tenantId}
                assets={rows(media.data)}
                value={profile.wechat_qr}
                onChange={(id) => set("wechat_qr", id)}
                onUploaded={media.reload}
                label={t("reseaux.wechatQr")}
                hint={t("reseaux.wechatQrAide")}
                // Un genre à lui : ce code n.est ni une réalisation, ni le QR
                // de paiement. Les confondre ferait payer une cliente qui
                // voulait poser une question.
                kind="wechat"
              />
            </div>
          </div>
        </Card>

        {/* --------------------------------------------------------- couleurs */}
        <Card id="couleurs">
          <SectionTitle>{t("couleurs.titre")}</SectionTitle>
          <p className="mb-4 text-sm text-muted">{t("couleurs.intro")}</p>

          {canEdit && (
            <div className="mb-5 flex flex-wrap gap-2">
              {PALETTES.map((palette) => {
                const active =
                  palette.primary.toLowerCase() === primary.toLowerCase() &&
                  palette.accent.toLowerCase() === accent.toLowerCase();
                return (
                  <button
                    key={palette.name}
                    type="button"
                    onClick={() =>
                      set("theme_config", {
                        ...theme,
                        primary: palette.primary,
                        accent: palette.accent,
                        surface: palette.surface,
                      })
                    }
                    aria-pressed={active}
                    className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition ${
                      active
                        ? "border-salon bg-salon-soft text-ink"
                        : "border-line bg-surface text-muted hover:bg-surface-hover"
                    }`}
                  >
                    <span className="flex">
                      <span
                        className="size-4 rounded-full ring-1 ring-black/10"
                        style={{ background: palette.primary }}
                      />
                      <span
                        className="-ml-1.5 size-4 rounded-full ring-1 ring-black/10"
                        style={{ background: palette.accent }}
                      />
                      <span
                        className="-ml-1.5 size-4 rounded-full ring-1 ring-black/10"
                        style={{ background: palette.surface }}
                      />
                    </span>
                    {site(`palettes.${palette.cle}`)}
                  </button>
                );
              })}
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-[auto_1fr]">
            <div className="flex flex-wrap gap-5">
              <ColorField
                label={t("couleurs.principale")}
                hint={t("couleurs.principaleAide")}
                value={primary}
                disabled={!canEdit}
                onChange={(value) =>
                  set("theme_config", { ...theme, primary: value })
                }
              />
              <ColorField
                label={t("couleurs.secondaire")}
                hint={t("couleurs.secondaireAide")}
                value={accent}
                disabled={!canEdit}
                onChange={(value) =>
                  set("theme_config", { ...theme, accent: value })
                }
              />
              <ColorField
                label={t("couleurs.fond")}
                hint={t("couleurs.fondAide")}
                value={surface}
                disabled={!canEdit}
                onChange={(value) =>
                  set("theme_config", { ...theme, surface: value })
                }
              />
            </div>

            {/* L'aperçu reprend la structure du mini-site — fond de page,
                carte blanche, bouton — pour qu'on juge l'accord réel des
                trois couleurs et pas un échantillon isolé. */}
            <div className="min-w-0">
              <span className="mb-1.5 block text-sm font-medium text-ink">
                {t("couleurs.apercu")}
              </span>
              <div
                className="rounded-xl border border-line p-4"
                style={{ background: surface }}
              >
                <div className="rounded-lg bg-white p-4 shadow-sm">
                  <p
                    className="text-lg font-semibold"
                    style={{ color: primary }}
                  >
                    {membership.tenant.name}
                  </p>
                  <p className="mt-0.5 text-sm text-black/55">
                    {profile.city || t("couleurs.ville")}
                  </p>

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span
                      className="rounded-full px-2.5 py-1 text-xs font-medium"
                      style={{ background: accent, color: encrePastille }}
                    >
                      {t("couleurs.pastille")}
                    </span>
                    <span
                      className="tabular text-sm font-semibold"
                      style={{ color: primary }}
                    >
                      250 ¥
                    </span>
                  </div>

                  <span
                    className="mt-3 inline-block rounded-lg px-4 py-2 text-sm font-semibold text-white"
                    style={{ background: primary }}
                  >
                    {t("couleurs.reserver")}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Une palette peut être jolie et illisible. La mesure tranche, et
              propose la correction plutôt que de seulement constater. */}
          {canEdit && (
            <div className="mt-6">
              <ContrastMeter
                primary={primary}
                accent={accent}
                surface={surface}
                onFix={(field, value) =>
                  set("theme_config", { ...theme, [field]: value })
                }
              />
            </div>
          )}
        </Card>

        {/* ------------------------------------------- règles de réservation */}
        <Card id="regles">
          <SectionTitle>{t("regles.titre")}</SectionTitle>
          <p className="mb-4 text-sm text-muted">{t("regles.intro")}</p>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label={t("regles.pas")}
              hint={t("regles.pasAide", {
                n: profile.slot_granularity_minutes,
                exemple: describeStep(profile.slot_granularity_minutes, region),
              })}
            >
              <input
                type="number"
                min={5}
                max={120}
                step={5}
                value={profile.slot_granularity_minutes}
                onChange={(event) =>
                  set("slot_granularity_minutes", Number(event.target.value))
                }
                disabled={!canEdit}
                className={`${inputClass} tabular`}
              />
            </Field>

            <Field
              label={t("regles.battement")}
              hint={
                profile.buffer_minutes > 0
                  ? t("regles.battementAide", { duree: formatDuration(profile.buffer_minutes) })
                  : t("regles.battementAucun")
              }
            >
              <input
                type="number"
                min={0}
                max={240}
                step={5}
                value={profile.buffer_minutes}
                onChange={(event) =>
                  set("buffer_minutes", Number(event.target.value))
                }
                disabled={!canEdit}
                className={`${inputClass} tabular`}
              />
            </Field>

            <Field
              label={t("regles.delai")}
              hint={
                profile.min_lead_time_minutes > 0
                  ? t("regles.delaiAide", { duree: formatDuration(profile.min_lead_time_minutes) })
                  : t("regles.delaiAucun")
              }
            >
              <input
                type="number"
                min={0}
                step={15}
                value={profile.min_lead_time_minutes}
                onChange={(event) =>
                  set("min_lead_time_minutes", Number(event.target.value))
                }
                disabled={!canEdit}
                className={`${inputClass} tabular`}
              />
            </Field>

            <Field
              label={t("regles.horizon")}
              hint={t("regles.horizonAide", { n: profile.max_advance_days })}
            >
              <input
                type="number"
                min={1}
                max={365}
                value={profile.max_advance_days}
                onChange={(event) =>
                  set("max_advance_days", Number(event.target.value))
                }
                disabled={!canEdit}
                className={`${inputClass} tabular`}
              />
            </Field>
          </div>
        </Card>

        {/* -------------------------------------------------------- à propos */}
        <Card id="apropos">
          <SectionTitle>{t("apropos.titre")}</SectionTitle>
          <p className="mb-4 text-sm text-muted">{t("apropos.intro")}</p>

          <Field
            label={t("apropos.titrePage")}
            hint={t("apropos.titrePageAide", { salon: membership.tenant.name })}
          >
            <input
              value={profile.about_title}
              onChange={(event) => set("about_title", event.target.value)}
              disabled={!canEdit}
              placeholder={t("apropos.titrePageExemple", { salon: membership.tenant.name })}
              className={inputClass}
            />
          </Field>

          <Field
            label={t("apropos.presentation")}
            hint={t("apropos.presentationAide")}
            className="mt-4"
          >
            <textarea
              value={profile.about_content}
              onChange={(event) => set("about_content", event.target.value)}
              disabled={!canEdit}
              rows={9}
              placeholder={t("apropos.presentationExemple")}
              className={inputClass}
            />
          </Field>

          <p className="mt-3 text-xs text-subtle">
            {t("apropos.mots", { n: aboutWordCount(profile.about_content) })} ·{" "}
            {profile.about_content.trim() ? t("apropos.enLigne") : t("apropos.masquee")}
          </p>

          {/*
            La photo de la page « A propos ».
            
            Elle existait cote serveur et s'affichait sur le mini-site, mais
            aucun ecran ne permettait de la choisir : le salon voyait donc une
            image d'ambiance sur sa propre page sans aucun moyen de la
            remplacer par la sienne.
          */}
          <div className="mt-5 border-t border-line pt-5">
            <MediaPicker
              tenantId={tenantId}
              assets={rows(media.data)}
              value={profile.about_image}
              onChange={(id) => set("about_image", id)}
              onUploaded={media.reload}
              label={t("apropos.photo")}
              hint={t("apropos.photoAide")}
              // « about » et non « gallery » : cette photo a son emploi, elle
              // n.a rien à faire dans les réalisations du salon.
              kind="about"
            />
          </div>
        </Card>

        {/* ------------------------------------------------------ déplacement */}
        {profile.service_mode !== "salon" && (
          <>
            <Card id="deplacement">
              <SectionTitle>{t("deplacement.titre")}</SectionTitle>

              <Field
                label={t("deplacement.quartiers")}
                hint={t("deplacement.quartiersAide")}
              >
                <input
                  value={profile.service_area}
                  onChange={(event) => set("service_area", event.target.value)}
                  disabled={!canEdit}
                  placeholder="Bacongo, Makélékélé, Moungali"
                  className={inputClass}
                />
              </Field>

              <PinField
                latitude={profile.latitude}
                longitude={profile.longitude}
                city={profile.city}
                address={profile.address}
                disabled={!canEdit}
                onChange={(latitude, longitude) => {
                  set("latitude", latitude);
                  set("longitude", longitude);
                }}
              />
            </Card>

            <TravelZones
              tenantId={tenantId}
              currency={membership.tenant.currency}
              canEdit={canEdit}
            />
          </>
        )}

        {/* Comment l'acompte se calcule.

            Avant, c'était un montant fixe par prestation : 150 sur 450 font
            33 %, les mêmes 150 sur 690 n'en font plus que 22 — alors qu'un
            rendez-vous plus cher qui ne vient pas coûte davantage. */}
        <Card id="acompte">
          <SectionTitle>{t("acompte.titre")}</SectionTitle>
          <p className="-mt-2 mb-4 text-sm text-muted">{t("acompte.intro")}</p>

          {/*
            Les deux chiffres ensemble, et nulle part ailleurs.

            Chaque prestation portait autrefois son propre montant. Deux
            réglages pour une même notion, à deux endroits — et une
            contradiction que les clientes voyaient : la fiche annonçait
            « acompte de 5 000 » pendant que la réservation en réclamait
            7 500, parce que le pourcentage l'emportait. La fiche ne dit plus
            que oui ou non ; le combien est ici.
          */}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label={t("acompte.part")}
              hint={t("acompte.partAide")}
            >
              <input
                type="number"
                min={0}
                max={100}
                value={profile.deposit_rate}
                onChange={(event) =>
                  set("deposit_rate", Number(event.target.value))
                }
                disabled={!canEdit}
                className={`${inputClass} tabular`}
              />
            </Field>

            <Field
              label={t("acompte.minimum", { devise: membership.tenant.currency })}
              hint={t("acompte.minimumAide")}
            >
              <input
                type="number"
                min={0}
                inputMode="decimal"
                value={profile.deposit_minimum}
                onChange={(event) => set("deposit_minimum", event.target.value)}
                disabled={!canEdit}
                className={`${inputClass} tabular`}
              />
            </Field>

            <div className="sm:col-span-2">
              <Toggle
                checked={profile.deposit_covers_items}
                onChange={(value) => set("deposit_covers_items", value)}
                label={t("acompte.fournitures")}
                hint={t("acompte.fournituresAide")}
              />
            </div>
          </div>

          {/* Un réglage qui ne demande rien se signale : sans ce mot, le
              salon croit avoir activé les acomptes et découvre des mois plus
              tard qu'aucun n'a jamais été réclamé. */}
          {profile.deposit_rate === 0 &&
            Number(profile.deposit_minimum) === 0 && (
              <p className="mt-3 flex items-start gap-2 rounded-xl bg-warning-bg px-3 py-2.5 text-sm text-warning">
                <Icon name="clock" className="mt-0.5 size-4 shrink-0" />
                <span>{t("acompte.aucun")}</span>
              </p>
            )}

          <DepositPreview
            rate={profile.deposit_rate}
            minimum={Number(profile.deposit_minimum) || 0}
            coversItems={profile.deposit_covers_items}
            currency={membership.tenant.currency}
          />
        </Card>

        {/* Les acomptes se règlent avant la venue : l'écran vit à côté de
            la politique d'annulation, qui répond à la même question — que
            se passe-t-il si la cliente ne vient pas. */}
        {/* ------------------------------------------------------------ devise */}
        <CurrencySwitch
          tenantId={tenantId}
          canEdit={canEdit}
          onChanged={media.reload}
        />

        <PaymentChannels
          tenantId={tenantId}
          canEdit={canEdit}
          media={rows(media.data)}
          onMediaChanged={media.reload}
        />

        {/* ------------------------------------------------------- annulation */}
        <Card id="annulation">
          <SectionTitle>{t("annulation.titre")}</SectionTitle>

          <Field
            label={t("annulation.politique")}
            hint={t("annulation.politiqueAide")}
          >
            <textarea
              value={profile.cancellation_policy}
              onChange={(event) =>
                set("cancellation_policy", event.target.value)
              }
              disabled={!canEdit}
              rows={3}
              className={inputClass}
            />
          </Field>

          <Field
            label={t("annulation.delai")}
            className="mt-4 max-w-xs"
          >
            <input
              type="number"
              min={0}
              max={168}
              value={profile.cancellation_deadline_hours}
              onChange={(event) =>
                set("cancellation_deadline_hours", Number(event.target.value))
              }
              disabled={!canEdit}
              className={`${inputClass} tabular`}
            />
          </Field>
        </Card>

        {/* ------------------------------------------------------------ retard */}
        <Card id="retard">
          <SectionTitle>{t("retard.titre")}</SectionTitle>

          <p className="-mt-2 mb-5 text-sm text-muted">{t("retard.intro")}</p>

          <div className="grid gap-5 sm:grid-cols-[minmax(0,13rem)_1fr]">
            <ToleranceInput
              value={profile.late_tolerance_minutes}
              disabled={!canEdit}
              onChange={(minutes) => set("late_tolerance_minutes", minutes)}
            />

            <Field
              label={t("retard.audela")}
              hint={t("retard.audelaAide")}
            >
              <textarea
                value={profile.late_policy}
                onChange={(event) => set("late_policy", event.target.value)}
                disabled={!canEdit}
                rows={3}
                placeholder={t("retard.audelaExemple")}
                className={inputClass}
              />
            </Field>
          </div>

          <LatePreview
            minutes={profile.late_tolerance_minutes}
            policy={profile.late_policy}
          />
        </Card>

        {canEdit ? (
          /* Barre collante : sur une page longue, le bouton d'enregistrement
             ne doit jamais être hors de portée. */
          <div className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-surface/95 px-4 py-3 backdrop-blur lg:left-[17rem]">
            <div className="mx-auto flex max-w-4xl items-center justify-between gap-4">
              <p className="text-sm text-muted">
                {dirty ? t("nonEnregistre") : t("toutEnregistre")}
              </p>
              <Button type="submit" pending={pending} disabled={!dirty}>
                {t("enregistrer")}
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted">
            {t("lectureSeule")}
          </p>
        )}
      </form>
    </section>
  );
}

/** Compteur de mots : il dit d'un coup d'œil si le texte est assez nourri. */
function aboutWordCount(text: string): number {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

/**
 * « 9 h 15, 9 h 30 » pour un pas de 15 min — plus parlant qu'un nombre.
 *
 * Même notation que le résumé des heures d'ouverture, trois lignes plus
 * haut : les deux se lisaient côte à côte avec deux conventions
 * différentes, « 9 h 30 » d'un côté et « 9:30 » de l'autre.
 */
function describeStep(minutes: number, region: string): string {
  const step = Math.max(5, minutes);
  return [0, step, step * 2]
    .map((offset) => frenchClock(9 * 60 + offset, region))
    .join(", ");
}

/**
 * Minutes depuis minuit → « 9 h » ou « 9 h 30 », espaces insécables ; en
 * anglais, « 9:00 » et « 9:30 ».
 */
function frenchClock(total: number, region: string): string {
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  if (!region.startsWith("fr")) return `${hours}:${String(minutes).padStart(2, "0")}`;
  const hour = `${hours} h`;
  return minutes === 0 ? hour : `${hour} ${String(minutes).padStart(2, "0")}`;
}

function ColorField({
  label,
  hint,
  value,
  disabled,
  onChange,
}: {
  label: string;
  hint?: string;
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const t = useTranslations("pro.profil.couleurs");
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">
        {label}
        {hint && <span className="ml-1.5 font-normal text-subtle">{hint}</span>}
      </span>
      <span className="flex items-center gap-2">
        <input
          type="color"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          className="h-10 w-12 cursor-pointer rounded-lg border border-line bg-surface p-1"
        />
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          spellCheck={false}
          aria-label={t("hexa", { couleur: label })}
          className="tabular w-28 rounded-lg border border-line bg-surface px-2.5 py-2 text-sm text-ink"
        />
      </span>
    </label>
  );
}

/** Paliers de tolérance courants. Composer un nombre est presque toujours inutile. */
const TOLERANCES = [0, 10, 15, 30] as const;

/**
 * Tolérance de retard : des paliers, plus un champ libre.
 *
 * Quatre valeurs couvrent la quasi-totalité des salons, et « 0 » est un vrai
 * choix — pas une case vide — pour celui qui ne tolère aucun retard. Le champ
 * libre reste là pour les autres, sans imposer sa saisie à tout le monde.
 */
function ToleranceInput({
  value,
  disabled,
  onChange,
}: {
  value: number;
  disabled?: boolean;
  onChange: (minutes: number) => void;
}) {
  const t = useTranslations("pro.profil.retard");
  const isPreset = (TOLERANCES as readonly number[]).includes(value);

  return (
    <fieldset className="min-w-0">
      <legend className="mb-1.5 text-sm font-medium text-ink">{t("tolerance")}</legend>

      <div className="flex flex-wrap gap-1.5">
        {TOLERANCES.map((minutes) => (
          <button
            key={minutes}
            type="button"
            disabled={disabled}
            onClick={() => onChange(minutes)}
            aria-pressed={value === minutes}
            className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
              value === minutes
                ? "bg-ink text-surface"
                : "border border-line text-muted hover:border-ink/40 hover:text-ink"
            } disabled:opacity-50`}
          >
            {minutes === 0 ? t("aucune") : `${minutes} min`}
          </button>
        ))}
      </div>

      <label className="mt-2.5 flex items-center gap-2">
        <span className="text-xs text-subtle">{t("autre")}</span>
        <input
          type="number"
          min={0}
          max={120}
          value={value}
          onChange={(event) => {
            const next = Number(event.target.value);
            onChange(
              Number.isFinite(next) ? Math.min(120, Math.max(0, next)) : 0,
            );
          }}
          disabled={disabled}
          aria-label={t("toleranceAria")}
          className={`tabular w-20 rounded-lg border bg-surface px-2.5 py-1.5 text-sm text-ink ${
            isPreset ? "border-line" : "border-ink/40"
          }`}
        />
        <span className="text-xs text-subtle">min</span>
      </label>
    </fieldset>
  );
}

/**
 * Ce que la cliente lira, écrit à la personne du salon.
 *
 * Une politique de retard est un texte qu'on rédige une fois et que d'autres
 * lisent cent fois : la voir prendre sa forme finale pendant qu'on l'écrit
 * évite de découvrir le ton employé dans un e-mail déjà parti.
 */
function LatePreview({ minutes, policy }: { minutes: number; policy: string }) {
  const t = useTranslations("pro.profil.retard");
  const written = policy.trim();

  return (
    <div className="mt-5 rounded-xl border border-dashed border-line bg-surface-muted px-4 py-3.5">
      <p className="mb-2 text-[0.7rem] font-semibold uppercase tracking-wide text-subtle">
        {t("vuParCliente")}
      </p>

      {written ? (
        <p className="text-sm leading-relaxed text-ink">
          {minutes === 0 ? t("apercuSansTolerance") : t("apercuTolerance", { n: minutes })}{" "}
          <span className="text-muted">{written}</span>
        </p>
      ) : (
        <p className="text-sm leading-relaxed text-muted">
          {t("vide")}{" "}
          <span className="text-ink">{t("agendaSignale", { n: minutes })}</span>
        </p>
      )}
    </div>
  );
}

/**
 * Point exact du salon, posé à la main.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi la saisie manuelle plutôt qu'un géocodage automatique
 * ---------------------------------------------------------------------------
 *
 * Dans une bonne partie de Brazzaville ou de Kinshasa, aucune adresse postale
 * n'est indexée : un géocodeur y renvoie le centre-ville avec un aplomb
 * parfait. Une cliente se perd alors en suivant un lien qui avait l'air juste
 * — c'est pire que pas de lien du tout.
 *
 * Le salon colle donc lui-même le point depuis Google Maps, où il se voit sur
 * une photo satellite et reconnaît son propre toit. Le champ accepte le
 * format que Maps met dans le presse-papiers, parce que c'est celui que les
 * gens ont sous la main.
 */
function PinField({
  latitude,
  longitude,
  city,
  address,
  disabled,
  onChange,
}: {
  latitude: string | null;
  longitude: string | null;
  city: string;
  address: string;
  disabled?: boolean;
  onChange: (latitude: string | null, longitude: string | null) => void;
}) {
  const [raw, setRaw] = useState(
    latitude && longitude ? `${latitude}, ${longitude}` : "",
  );
  const t = useTranslations("pro.profil.point");
  const [error, setError] = useState<string | null>(null);

  const posed = Boolean(latitude && longitude);

  // Lien de repérage : le point posé s'il existe, sinon l'adresse écrite.
  const lookup = posed
    ? `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`
    : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
        [address, city].filter(Boolean).join(" ") || t("recherche"),
      )}`;

  function commit(value: string) {
    const trimmed = value.trim();

    if (!trimmed) {
      setError(null);
      onChange(null, null);
      return;
    }

    const parsed = parseCoordinates(trimmed);
    if (!parsed) {
      setError(t("format"));
      return;
    }
    setError(null);
    setRaw(`${parsed.latitude}, ${parsed.longitude}`);
    onChange(parsed.latitude, parsed.longitude);
  }

  return (
    <div className="mt-4">
      <Field
        label={t("libelle")}
        hint={t("aide")}
        error={error ?? undefined}
      >
        <input
          value={raw}
          onChange={(event) => setRaw(event.target.value)}
          onBlur={(event) => commit(event.target.value)}
          disabled={disabled}
          spellCheck={false}
          placeholder="-4.2634, 15.2429"
          aria-label={t("aria")}
          className={`${inputClass} tabular`}
        />
      </Field>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
        <a
          href={lookup}
          target="_blank"
          rel="noreferrer noopener"
          className="font-medium text-salon underline-offset-2 hover:underline"
        >
          {posed ? t("verifier") : t("trouver")}
        </a>
        <span className={posed ? "text-success" : "text-subtle"}>
          {posed ? t("itineraireExact") : t("itineraireAdresse")}
        </span>
      </div>
    </div>
  );
}

/**
 * Lit un couple de coordonnées.
 *
 * Deux écritures circulent, et la virgule veut dire l'inverse dans chacune :
 *
 *     -4.2634, 15.2429     ce que Google Maps met dans le presse-papiers
 *     -4,2634 15,2429      la frappe naturelle d'un clavier francophone
 *
 * On essaie donc la première lecture, et on ne bascule sur la seconde que si
 * elle ne donne pas deux nombres. Une règle unique se trompait forcément sur
 * l'une des deux — et « -4.2634,15.2429 », sans espace, tombait justement
 * dans l'angle mort.
 */
function parseCoordinates(
  value: string,
): { latitude: string; longitude: string } | null {
  const cleaned = value.replace(/[()]/g, "").trim();

  return (
    toCoordinates(cleaned.split(/[,\s]+/)) ??
    toCoordinates(cleaned.replace(/,/g, ".").split(/\s+/))
  );
}

function toCoordinates(
  parts: string[],
): { latitude: string; longitude: string } | null {
  const clean = parts.filter(Boolean);
  if (clean.length !== 2) return null;

  const [latitude, longitude] = clean.map(Number);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
  if (Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return null;

  // Six décimales : environ onze centimètres, largement au-delà de ce qu'une
  // carte grand public sait montrer. Au-delà, ce sont des chiffres inventés.
  return {
    latitude: latitude.toFixed(6),
    longitude: longitude.toFixed(6),
  };
}

/**
 * Ce que le réglage donne sur un cas concret.
 *
 * Un pourcentage seul ne dit rien : « 30 % » ne permet pas de savoir si on
 * demande trop ou pas assez. Trois lignes chiffrées le disent, et c'est en
 * les lisant qu'on ajuste — pas en relisant le libellé du champ.
 *
 * L'exemple est volontairement celui qui a motivé la règle : une prestation,
 * des options, des fournitures. C'est le panier où l'ancien montant fixe
 * protégeait le moins.
 */
function DepositPreview({
  rate,
  minimum,
  coversItems,
  currency,
}: {
  rate: number;
  /** Le plancher du salon. Il vient du réglage voisin, plus d'une valeur
   *  inventée pour l'exemple : l'aperçu doit bouger quand on le change. */
  minimum: number;
  coversItems: boolean;
  currency: string;
}) {
  const t = useTranslations("pro.profil.exemple");
  const { region } = useFormats();
  const prix = (valeur: number) => formatPrice(String(valeur), currency, region);
  const service = 450;
  const options = 80;
  const items = 240;

  const fromRate = rate > 0 ? ((service + options) * rate) / 100 : 0;
  const time = Math.max(minimum, fromRate);
  const due = Math.floor(time + (coversItems ? items : 0));
  const total = service + options + items;

  return (
    <div className="mt-5 rounded-xl border border-dashed border-line bg-surface-muted/40 p-3.5">
      <p className="mb-2 text-[0.7rem] font-semibold uppercase tracking-wide text-subtle">
        {t("titre")}
      </p>

      {/* Deux colonnes dès le téléphone : ces lignes sont courtes, et
          empilées elles éloigneraient le total du réglage qu'on ajuste. */}
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
        <Row label={t("prestation")} value={prix(service)} />
        <Row label={t("options")} value={prix(options)} />
        <Row label={t("fournitures")} value={prix(items)} />
        <Row label={t("total")} value={prix(total)} strong />
      </dl>

      <p className="mt-2.5 flex flex-wrap items-baseline justify-between gap-x-2 border-t border-line pt-2.5">
        <span className="text-sm font-medium text-ink">{t("acompte")}</span>
        <span className="tabular text-base font-semibold text-salon">
          {prix(due)}
          <span className="ml-1.5 text-xs font-normal text-subtle">
            {t("partTotal", { pct: Math.round((due / total) * 100) })}
          </span>
        </span>
      </p>

      {rate === 0 && minimum > 0 && (
        <p className="mt-1.5 text-xs text-muted">
          {t("sansPourcentage", { minimum: prix(minimum) })}
        </p>
      )}
      {rate > 0 && minimum > fromRate && (
        <p className="mt-1.5 text-xs text-muted">
          {t("minimumApplique", { taux: rate, montant: prix(Math.floor(fromRate)) })}
        </p>
      )}
    </div>
  );
}

function Row({
  label,
  value,
  strong = false,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-xs text-muted">{label}</dt>
      <dd
        className={`tabular text-xs ${strong ? "font-medium text-ink" : "text-ink"}`}
      >
        {value}
      </dd>
    </div>
  );
}
