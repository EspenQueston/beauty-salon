"use client";

/**
 * Profil du salon : vitrine, coordonnées, apparence, règles de réservation.
 *
 * Les réglages de réservation sont regroupés à part parce qu'ils ne changent
 * pas l'affichage mais le comportement du moteur de créneaux : les modifier
 * à l'aveugle déplace de vrais rendez-vous. Chaque champ dit donc son effet.
 */

import { useEffect, useMemo, useState } from "react";

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
import { Icon } from "./icons";
import { ContrastMeter } from "./ContrastMeter";
import { MediaPicker, type PickableMedia } from "./MediaPicker";
import { PaymentChannels } from "./PaymentChannels";
import { TravelZones } from "./TravelZones";
import { rows, useResource, type Page } from "./useResource";
import { SectionNav, type NavSection } from "./SectionNav";
import { useDashboard } from "./DashboardShell";

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
  social_links: Record<string, string>;
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
  { key: "wechat", label: "WeChat" },
] as const;

/** Ordre de la barre de sections : celui de la page, pas un autre. */
const PROFILE_SECTIONS: NavSection[] = [
  { id: "vitrine", label: "Vitrine" },
  { id: "reseaux", label: "Réseaux" },
  { id: "couleurs", label: "Couleurs" },
  { id: "apropos", label: "À propos" },
  { id: "regles", label: "Réservation" },
  { id: "deplacement", label: "Déplacement" },
  { id: "acompte", label: "Acompte" },
  { id: "encaissement", label: "Encaissement" },
  { id: "annulation", label: "Annulation" },
  { id: "retard", label: "Retard" },
];

const DEFAULT_PRIMARY = "#B4436C";
const DEFAULT_ACCENT = "#F2C4CE";
const DEFAULT_SURFACE = "#FAF7F8";

/**
 * Palettes prêtes à l'emploi : choisir bat composer, pour la plupart.
 *
 * Chacune porte les trois couleurs, fond de page compris. Sans lui, choisir
 * « Terracotta » laissait le mini-site sur le fond rosé d'origine — deux
 * familles de couleurs sur la même page, ce qui se voit tout de suite.
 */
const PALETTES = [
  { name: "Rose poudré", primary: "#B4436C", accent: "#F7D9E1", surface: "#FCF7F9" },
  { name: "Or et nuit", primary: "#1F2937", accent: "#E9C46A", surface: "#FBF8F1" },
  { name: "Terracotta", primary: "#9C4221", accent: "#F6D5C0", surface: "#FDF7F3" },
  { name: "Émeraude", primary: "#0F766E", accent: "#CDEDE7", surface: "#F4FAF9" },
  { name: "Violet", primary: "#6D28D9", accent: "#E4D8FB", surface: "#F9F7FE" },
  { name: "Bleu nuit", primary: "#1E3A8A", accent: "#D6E0FA", surface: "#F6F8FD" },
  { name: "Cacao", primary: "#5C3A21", accent: "#E8D5C0", surface: "#FBF7F3" },
  { name: "Corail", primary: "#C2410C", accent: "#FDDCC8", surface: "#FFF8F4" },
  { name: "Prune", primary: "#86198F", accent: "#F3D5F5", surface: "#FDF6FE" },
  { name: "Encre et menthe", primary: "#134E4A", accent: "#B9E7DC", surface: "#F2FAF8" },
];

export function SalonProfileScreen() {
  const { membership } = useDashboard();
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
  const [error, setError] = useState<string | null>(null);
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
        if (!cancelled) setError("Chargement impossible.");
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

    const ok = await toast.run(
      () =>
        dashboardFetch(
          "/api/v1/salon-profile",
          { method: "PATCH", body: JSON.stringify(profile) },
          tenantId,
        ),
      { success: "Profil enregistré. Votre mini-site est à jour." },
    );

    setPending(false);
    if (ok) setSaved(profile);
  }

  if (error) {
    return (
      <section>
        <PageHeader title="Profil du salon" />
        <ErrorState>{error}</ErrorState>
      </section>
    );
  }

  if (!profile) {
    return (
      <section>
        <PageHeader title="Profil du salon" />
        <Skeleton rows={5} />
      </section>
    );
  }

  const theme = profile.theme_config ?? {};
  const primary = theme.primary ?? DEFAULT_PRIMARY;
  const accent = theme.accent ?? DEFAULT_ACCENT;
  const surface = theme.surface ?? DEFAULT_SURFACE;

  return (
    <section>
      <PageHeader
        title="Profil du salon"
        description="Ce que voient vos clientes avant de réserver, et les règles que suit votre agenda."
      />

      {/* Six blocs sur trois écrans : la barre évite de les parcourir à
          l'aveugle, et dit laquelle on est en train de remplir. */}
      <SectionNav sections={PROFILE_SECTIONS} />

      <form onSubmit={submit} className="space-y-6 pb-24">
        {/* ---------------------------------------------------------- vitrine */}
        <Card id="vitrine">
          <SectionTitle>Vitrine</SectionTitle>

          <Field
            label="Présentation"
            hint="Deux ou trois phrases : votre spécialité, ce qui vous distingue."
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
            <Field label="Adresse">
              <input
                value={profile.address}
                onChange={(event) => set("address", event.target.value)}
                disabled={!canEdit}
                className={inputClass}
              />
            </Field>
            <Field label="Ville">
              <input
                value={profile.city}
                onChange={(event) => set("city", event.target.value)}
                disabled={!canEdit}
                className={inputClass}
              />
            </Field>
            <Field label="Téléphone">
              <input
                value={profile.phone}
                onChange={(event) => set("phone", event.target.value)}
                disabled={!canEdit}
                className={inputClass}
              />
            </Field>
            <Field
              label="WhatsApp"
              hint="Format international, ex. +242060000000."
            >
              <input
                value={profile.whatsapp_number}
                onChange={(event) => set("whatsapp_number", event.target.value)}
                disabled={!canEdit}
                placeholder="+242…"
                className={inputClass}
              />
            </Field>
            <Field label="Prestations réalisées" className="sm:col-span-2">
              <select
                value={profile.service_mode}
                onChange={(event) =>
                  set("service_mode", event.target.value as Profile["service_mode"])
                }
                disabled={!canEdit}
                className={inputClass}
              >
                <option value="salon">Au salon</option>
                <option value="home">À domicile</option>
                <option value="hybrid">Les deux</option>
              </select>
            </Field>
          </div>
        </Card>

        {/* --------------------------------------------------------- réseaux */}
        <Card id="reseaux">
          <SectionTitle>Réseaux sociaux</SectionTitle>
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
        </Card>

        {/* --------------------------------------------------------- couleurs */}
        <Card id="couleurs">
          <SectionTitle>Couleurs</SectionTitle>
          <p className="mb-4 text-sm text-muted">
            Elles habillent votre mini-site. La mise en page, elle, reste la
            même pour tous — c&apos;est ce qui garantit qu&apos;il reste lisible
            sur un petit écran.
          </p>

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
                    {palette.name}
                  </button>
                );
              })}
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-[auto_1fr]">
            <div className="flex flex-wrap gap-5">
              <ColorField
                label="Principale"
                hint="Boutons et prix"
                value={primary}
                disabled={!canEdit}
                onChange={(value) => set("theme_config", { ...theme, primary: value })}
              />
              <ColorField
                label="Secondaire"
                hint="Pastilles, médaillons"
                value={accent}
                disabled={!canEdit}
                onChange={(value) => set("theme_config", { ...theme, accent: value })}
              />
              <ColorField
                label="Fond de page"
                hint="Derrière les cartes"
                value={surface}
                disabled={!canEdit}
                onChange={(value) => set("theme_config", { ...theme, surface: value })}
              />
            </div>

            {/* L'aperçu reprend la structure du mini-site — fond de page,
                carte blanche, bouton — pour qu'on juge l'accord réel des
                trois couleurs et pas un échantillon isolé. */}
            <div className="min-w-0">
              <span className="mb-1.5 block text-sm font-medium text-ink">
                Aperçu du mini-site
              </span>
              <div
                className="rounded-xl border border-line p-4"
                style={{ background: surface }}
              >
                <div className="rounded-lg bg-white p-4 shadow-sm">
                  <p className="text-lg font-semibold" style={{ color: primary }}>
                    {membership.tenant.name}
                  </p>
                  <p className="mt-0.5 text-sm text-black/55">
                    {profile.city || "Votre ville"}
                  </p>

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span
                      className="rounded-full px-2.5 py-1 text-xs font-medium"
                      style={{ background: accent, color: primary }}
                    >
                      Tresses
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
                    Réserver
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
          <SectionTitle>Règles de réservation</SectionTitle>
          <p className="mb-4 text-sm text-muted">
            Ces réglages changent les créneaux proposés à vos clientes. Une
            modification s&apos;applique aux réservations à venir, pas à celles
            déjà prises.
          </p>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Pas des créneaux"
              hint={`${profile.slot_granularity_minutes} min propose ${describeStep(profile.slot_granularity_minutes)}…`}
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
              label="Battement entre rendez-vous"
              hint={
                profile.buffer_minutes > 0
                  ? `${formatDuration(profile.buffer_minutes)} réservées après chaque prestation.`
                  : "Aucun temps de remise en état réservé."
              }
            >
              <input
                type="number"
                min={0}
                max={240}
                step={5}
                value={profile.buffer_minutes}
                onChange={(event) => set("buffer_minutes", Number(event.target.value))}
                disabled={!canEdit}
                className={`${inputClass} tabular`}
              />
            </Field>

            <Field
              label="Délai minimal avant un rendez-vous"
              hint={
                profile.min_lead_time_minutes > 0
                  ? `Une cliente ne peut pas réserver dans les ${formatDuration(profile.min_lead_time_minutes)}.`
                  : "Réservation possible jusqu'à la dernière minute."
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
              label="Réservable jusqu'à (jours à l'avance)"
              hint={`Agenda ouvert sur ${profile.max_advance_days} jours.`}
            >
              <input
                type="number"
                min={1}
                max={365}
                value={profile.max_advance_days}
                onChange={(event) => set("max_advance_days", Number(event.target.value))}
                disabled={!canEdit}
                className={`${inputClass} tabular`}
              />
            </Field>
          </div>
        </Card>

        {/* -------------------------------------------------------- à propos */}
        <Card id="apropos">
          <SectionTitle>Page « À propos »</SectionTitle>
          <p className="mb-4 text-sm text-muted">
            Votre histoire, en quelques paragraphes. Elle devient une page à
            part sur votre mini-site, et le lien n&apos;apparaît dans le menu
            qu&apos;une fois le texte écrit.
          </p>

          <Field
            label="Titre de la page"
            hint={`Laissé vide, votre mini-site affiche « À propos de ${membership.tenant.name} ».`}
          >
            <input
              value={profile.about_title}
              onChange={(event) => set("about_title", event.target.value)}
              disabled={!canEdit}
              placeholder={`À propos de ${membership.tenant.name}`}
              className={inputClass}
            />
          </Field>

          <Field
            label="Votre présentation"
            hint="Séparez vos paragraphes par une ligne vide. Depuis quand vous exercez, ce que vous faites le mieux, ce qui vous distingue."
            className="mt-4"
          >
            <textarea
              value={profile.about_content}
              onChange={(event) => set("about_content", event.target.value)}
              disabled={!canEdit}
              rows={9}
              placeholder={
                "Nous avons ouvert en 2015, dans un quartier où personne ne " +
                "coiffait le cheveu afro.\n\nAujourd'hui, trois prestataires " +
                "vous reçoivent sur rendez-vous…"
              }
              className={inputClass}
            />
          </Field>

          <p className="mt-3 text-xs text-subtle">
            {aboutWordCount(profile.about_content)} mot
            {aboutWordCount(profile.about_content) > 1 ? "s" : ""} ·{" "}
            {profile.about_content.trim()
              ? "la page est en ligne"
              : "la page reste masquée tant que ce champ est vide"}
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
              label="Photo de la page"
              hint="Portrait ou vue du salon. Sans photo, une image d.ambiance est affichée à la place."
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
              <SectionTitle>Où vous vous déplacez</SectionTitle>

              <Field
                label="Quartiers desservis"
                hint="Séparés par des virgules. Affichés tels quels sur votre mini-site."
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
          <SectionTitle>Montant de l&apos;acompte</SectionTitle>
          <p className="-mt-2 mb-4 text-sm text-muted">
            Le temps se réserve à un pourcentage : un créneau libéré assez tôt
            peut être repris. Les fournitures, elles, se règlent en entier —
            vous les avez déjà achetées.
          </p>

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
              label="Part de la prestation demandée (%)"
              hint="S'applique aux prestations que vous avez marquées « demande un acompte »."
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
              label={`Acompte minimum (${membership.tenant.currency})`}
              hint="Plancher, quel que soit le pourcentage. Utile sur les petites prestations."
            >
              <input
                type="number"
                min={0}
                inputMode="decimal"
                value={profile.deposit_minimum}
                onChange={(event) =>
                  set("deposit_minimum", event.target.value)
                }
                disabled={!canEdit}
                className={`${inputClass} tabular`}
              />
            </Field>

            <div className="sm:col-span-2">
              <Toggle
                checked={profile.deposit_covers_items}
                onChange={(value) => set("deposit_covers_items", value)}
                label="Fournitures payées d'avance"
                hint="Des mèches achetées pour une cliente précise ne se revendent pas toujours."
              />
            </div>
          </div>

          {/* Un réglage qui ne demande rien se signale : sans ce mot, le
              salon croit avoir activé les acomptes et découvre des mois plus
              tard qu'aucun n'a jamais été réclamé. */}
          {profile.deposit_rate === 0 && Number(profile.deposit_minimum) === 0 && (
            <p className="mt-3 flex items-start gap-2 rounded-xl bg-warning-bg px-3 py-2.5 text-sm text-warning">
              <Icon name="clock" className="mt-0.5 size-4 shrink-0" />
              <span>
                Avec 0 % et aucun minimum, aucun acompte ne sera demandé — même
                sur les prestations qui en réclament un.
              </span>
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
        <PaymentChannels
          tenantId={tenantId}
          canEdit={canEdit}
          media={rows(media.data)}
          onMediaChanged={media.reload}
        />

        {/* ------------------------------------------------------- annulation */}
        <Card id="annulation">
          <SectionTitle>Annulation</SectionTitle>

          <Field
            label="Politique affichée à la cliente"
            hint="Elle doit être acceptée avant toute réservation : c'est ce texte que vous pourrez opposer en cas de litige."
          >
            <textarea
              value={profile.cancellation_policy}
              onChange={(event) => set("cancellation_policy", event.target.value)}
              disabled={!canEdit}
              rows={3}
              className={inputClass}
            />
          </Field>

          <Field
            label="Annulation gratuite jusqu'à (heures avant)"
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
          <SectionTitle>Retard</SectionTitle>

          <p className="-mt-2 mb-5 text-sm text-muted">
            Le retard se règle en le disant à l&apos;avance. Une cliente
            prévenue arrive à l&apos;heure ; une cliente qui l&apos;apprend sur
            place se sent lésée — et vous perdez les deux.
          </p>

          <div className="grid gap-5 sm:grid-cols-[minmax(0,13rem)_1fr]">
            <ToleranceInput
              value={profile.late_tolerance_minutes}
              disabled={!canEdit}
              onChange={(minutes) => set("late_tolerance_minutes", minutes)}
            />

            <Field
              label="Ce qu'il se passe au-delà"
              hint="Affiché sur votre mini-site et rappelé dans l'e-mail de confirmation."
            >
              <textarea
                value={profile.late_policy}
                onChange={(event) => set("late_policy", event.target.value)}
                disabled={!canEdit}
                rows={3}
                placeholder={
                  "Nous faisons notre possible pour vous prendre quand même, " +
                  "mais la prestation peut être raccourcie ou reportée selon " +
                  "les rendez-vous suivants."
                }
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
                {dirty ? "Modifications non enregistrées." : "Tout est enregistré."}
              </p>
              <Button type="submit" pending={pending} disabled={!dirty}>
                Enregistrer
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted">
            Seuls le propriétaire et le gérant peuvent modifier le profil.
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
function describeStep(minutes: number): string {
  const step = Math.max(5, minutes);
  return [0, step, step * 2].map((offset) => frenchClock(9 * 60 + offset)).join(", ");
}

/** Minutes depuis minuit → « 9 h » ou « 9 h 30 », espaces insécables. */
function frenchClock(total: number): string {
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  const hour = `${hours} h`;
  return minutes === 0
    ? hour
    : `${hour} ${String(minutes).padStart(2, "0")}`;
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
          aria-label={`${label} en hexadécimal`}
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
  const isPreset = (TOLERANCES as readonly number[]).includes(value);

  return (
    <fieldset className="min-w-0">
      <legend className="mb-1.5 text-sm font-medium text-ink">Tolérance</legend>

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
            {minutes === 0 ? "Aucune" : `${minutes} min`}
          </button>
        ))}
      </div>

      <label className="mt-2.5 flex items-center gap-2">
        <span className="text-xs text-subtle">Autre</span>
        <input
          type="number"
          min={0}
          max={120}
          value={value}
          onChange={(event) => {
            const next = Number(event.target.value);
            onChange(Number.isFinite(next) ? Math.min(120, Math.max(0, next)) : 0);
          }}
          disabled={disabled}
          aria-label="Tolérance de retard en minutes"
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
  const written = policy.trim();

  return (
    <div className="mt-5 rounded-xl border border-dashed border-line bg-surface-muted px-4 py-3.5">
      <p className="mb-2 text-[0.7rem] font-semibold uppercase tracking-wide text-subtle">
        Vu par la cliente
      </p>

      {written ? (
        <p className="text-sm leading-relaxed text-ink">
          {minutes === 0
            ? "Merci d'arriver à l'heure. En cas de retard : "
            : `Merci d'arriver à l'heure. Au-delà de ${minutes} minutes de retard : `}
          <span className="text-muted">{written}</span>
        </p>
      ) : (
        <p className="text-sm leading-relaxed text-muted">
          Tant que ce champ est vide, rien n&apos;est affiché à la cliente et
          l&apos;e-mail ne mentionne pas le retard.{" "}
          <span className="text-ink">
            L&apos;agenda, lui, signale déjà les rendez-vous en retard de plus
            de {minutes} min.
          </span>
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
  const [error, setError] = useState<string | null>(null);

  const posed = Boolean(latitude && longitude);

  // Lien de repérage : le point posé s'il existe, sinon l'adresse écrite.
  const lookup = posed
    ? `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`
    : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
        [address, city].filter(Boolean).join(" ") || "salon de beauté",
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
      setError("Format attendu : 4.2634, 15.2429");
      return;
    }
    setError(null);
    setRaw(`${parsed.latitude}, ${parsed.longitude}`);
    onChange(parsed.latitude, parsed.longitude);
  }

  return (
    <div className="mt-4">
      <Field
        label="Point exact (facultatif)"
        hint="Collez les coordonnées depuis Google Maps : clic droit sur votre salon, puis clic sur les chiffres pour les copier."
        error={error ?? undefined}
      >
        <input
          value={raw}
          onChange={(event) => setRaw(event.target.value)}
          onBlur={(event) => commit(event.target.value)}
          disabled={disabled}
          spellCheck={false}
          placeholder="-4.2634, 15.2429"
          aria-label="Latitude et longitude"
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
          {posed ? "Vérifier le point sur la carte" : "Trouver mon salon sur la carte"}
        </a>
        <span className={posed ? "text-success" : "text-subtle"}>
          {posed
            ? "L'itinéraire mène au point exact."
            : "Sans point, l'itinéraire cherche l'adresse écrite."}
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
        Sur un exemple
      </p>

      {/* Deux colonnes dès le téléphone : ces lignes sont courtes, et
          empilées elles éloigneraient le total du réglage qu'on ajuste. */}
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
        <Row label="Prestation" value={formatPrice(String(service), currency)} />
        <Row label="Options" value={formatPrice(String(options), currency)} />
        <Row label="Fournitures" value={formatPrice(String(items), currency)} />
        <Row
          label="Total"
          value={formatPrice(String(total), currency)}
          strong
        />
      </dl>

      <p className="mt-2.5 flex flex-wrap items-baseline justify-between gap-x-2 border-t border-line pt-2.5">
        <span className="text-sm font-medium text-ink">Acompte demandé</span>
        <span className="tabular text-base font-semibold text-salon">
          {formatPrice(String(due), currency)}
          <span className="ml-1.5 text-xs font-normal text-subtle">
            {Math.round((due / total) * 100)} % du total
          </span>
        </span>
      </p>

      {rate === 0 && minimum > 0 && (
        <p className="mt-1.5 text-xs text-muted">
          Sans pourcentage, l&apos;acompte reste au minimum quel que soit le
          panier — {formatPrice(String(minimum), currency)}, plus les
          fournitures.
        </p>
      )}
      {rate > 0 && minimum > fromRate && (
        <p className="mt-1.5 text-xs text-muted">
          Ici c&apos;est le minimum qui s&apos;applique : {rate} % ne feraient
          que {formatPrice(String(Math.floor(fromRate)), currency)}.
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
      <dd className={`tabular text-xs ${strong ? "font-medium text-ink" : "text-ink"}`}>
        {value}
      </dd>
    </div>
  );
}
