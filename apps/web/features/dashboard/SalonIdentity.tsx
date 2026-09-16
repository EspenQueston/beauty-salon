"use client";

/**
 * Le nom du salon, et les coordonnées de qui le tient.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi cet écran existe
 * ---------------------------------------------------------------------------
 *
 * Ces cinq champs vivent dans trois tables différentes, et ça ne regarde
 * personne d'autre que le serveur : on vient les changer au même moment —
 * quand on corrige une faute dans le nom du salon, quand on change de numéro.
 * Les éparpiller sur trois écrans obligeait à savoir dans lequel chercher.
 *
 * C'est aussi là que mène le bloc du salon, en bas de la colonne de gauche.
 * Cliquer sur son propre nom et tomber sur la présentation publique du salon
 * était la mauvaise réponse à la bonne question.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'on ne change pas ici
 * ---------------------------------------------------------------------------
 *
 * Le sous-domaine. Il est imprimé sur des flyers, collé en QR code au mur,
 * partagé en story : le changer casserait tous ces liens sans que personne
 * ne s'en aperçoive avant la première cliente perdue. Il s'affiche, avec de
 * quoi le copier, et c'est tout.
 *
 * Le mot de passe non plus : il a son propre écran, avec la vérification de
 * l'ancien. Le glisser ici en ferait une case parmi d'autres.
 */

import { useEffect, useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import {
  Button,
  Card,
  ErrorState,
  Field,
  PageHeader,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";

import { useDashboard } from "./DashboardShell";
import { Icon } from "./icons";
import { useResource } from "./useResource";

interface Identity {
  salon_name: string;
  owner_name: string;
  owner_email: string;
  owner_phone: string;
  slug: string;
  site_url: string;
  role: string;
}

export function SalonIdentityScreen() {
  const { membership, reload: reloadSession } = useDashboard();
  const toast = useToast();
  const tenantId = membership.tenant.id;
  const canEdit = membership.role === "owner";

  const { data, error, reload } = useResource<Identity>(
    "/api/v1/salon-identity",
    tenantId,
  );

  const [form, setForm] = useState<Identity | null>(null);
  const [saving, setSaving] = useState(false);

  // Le formulaire se remplit quand la lecture arrive, et seulement alors :
  // le réinitialiser à chaque rendu effacerait ce qu'on est en train de taper.
  const [seen, setSeen] = useState<Identity | null>(null);
  if (data && data !== seen) {
    setSeen(data);
    setForm(data);
  }

  // Le titre de l'onglet suit le nom du salon : après un renommage, laisser
  // l'ancien dans la barre d'onglets donne l'impression que rien n'a pris.
  useEffect(() => {
    if (data?.salon_name) document.title = `Identité · ${data.salon_name}`;
  }, [data?.salon_name]);

  if (error) return <ErrorState>{error}</ErrorState>;
  if (!form) return <Skeleton rows={5} />;

  function set<K extends keyof Identity>(key: K, value: Identity[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!form) return;

    setSaving(true);
    const ok = await toast.run(
      () =>
        dashboardFetch<Identity>(
          "/api/v1/salon-identity",
          {
            method: "PATCH",
            body: JSON.stringify({
              salon_name: form.salon_name,
              owner_name: form.owner_name,
              owner_email: form.owner_email,
              owner_phone: form.owner_phone,
            }),
          },
          tenantId,
        ),
      { success: "Vos informations sont à jour." },
    );
    setSaving(false);

    if (ok) {
      reload();
      // La session porte le nom du salon : sans rechargement, la colonne de
      // gauche continuerait d'afficher l'ancien jusqu'à la prochaine visite.
      reloadSession();
    }
  }

  return (
    <>
      <PageHeader
        title="Identité"
        description="Le nom de votre salon, et comment vous joindre."
      />

      <form onSubmit={save} className="space-y-5">
        {/* ----- Le salon ------------------------------------------------ */}
        <Card>
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-ink">
            <Icon name="store" className="size-4 text-salon" />
            Votre salon
          </h2>

          <Field
            label="Nom du salon"
            hint="Il apparaît en haut de votre mini-site, dans vos e-mails et sur vos factures."
          >
            <input
              value={form.salon_name}
              onChange={(event) => set("salon_name", event.target.value)}
              disabled={!canEdit}
              required
              maxLength={120}
              className={inputClass}
            />
          </Field>

          {/*
            L'adresse du mini-site, en lecture seule et copiable.

            C'est l'information qu'on vient chercher le plus souvent sur cet
            écran — pour la coller dans une story ou l'envoyer par WhatsApp —
            et c'est la seule qu'on ne doit surtout pas pouvoir modifier.
          */}
          <div className="mt-4">
            <p className="mb-1.5 text-sm font-medium text-ink">
              Adresse de votre mini-site
            </p>
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-surface-muted px-3 py-2.5">
              <code className="min-w-0 flex-1 truncate text-sm text-muted">
                {form.site_url}
              </code>
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard
                    ?.writeText(form.site_url)
                    .then(() => toast.info("Adresse copiée."))
                    .catch(() => toast.info("Copie impossible sur ce navigateur."));
                }}
                className="shrink-0 rounded-lg border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink transition hover:bg-surface-hover"
              >
                Copier
              </button>
              <a
                href={form.site_url}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 rounded-lg border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink transition hover:bg-surface-hover"
              >
                Ouvrir
              </a>
            </div>
            <p className="mt-1.5 text-xs text-subtle">
              Cette adresse ne change pas : elle est peut-être déjà imprimée
              ou partagée. Écrivez-nous si vous devez vraiment en changer.
            </p>
          </div>
        </Card>

        {/* ----- La personne --------------------------------------------- */}
        <Card>
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-ink">
            <Icon name="users" className="size-4 text-salon" />
            Vous
          </h2>

          {/* Deux colonnes dès le téléphone : ce sont des champs courts, et
              une colonne unique ferait défiler quatre fois pour quatre
              lignes. Le téléphone garde toute la largeur — un numéro
              international y tient mal sur 160 px. */}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Votre nom"
              hint="Il apparaît sur votre fiche de prestataire."
            >
              <input
                value={form.owner_name}
                onChange={(event) => set("owner_name", event.target.value)}
                disabled={!canEdit}
                maxLength={120}
                className={inputClass}
              />
            </Field>

            <Field
              label="Téléphone"
              hint="Pour que l'équipe Beauty Salon vous joigne."
            >
              <input
                type="tel"
                inputMode="tel"
                value={form.owner_phone}
                onChange={(event) => set("owner_phone", event.target.value)}
                disabled={!canEdit}
                maxLength={32}
                className={inputClass}
              />
            </Field>

            <Field
              label="Adresse e-mail"
              hint="C'est aussi votre identifiant de connexion."
              className="sm:col-span-2"
            >
              <input
                type="email"
                value={form.owner_email}
                onChange={(event) => set("owner_email", event.target.value)}
                disabled={!canEdit}
                required
                className={inputClass}
              />
            </Field>
          </div>
        </Card>

        {canEdit ? (
          <div className="flex justify-end">
            <Button type="submit" pending={saving}>
              Enregistrer
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted">
            Seule la propriétaire du salon peut modifier ces informations.
          </p>
        )}
      </form>
    </>
  );
}
