"use client";

/**
 * Apparence avancée du mini-site (offre Pro).
 *
 * Des choix, pas du code : deux polices dans une liste, l'ordre et la
 * visibilité des rubriques du menu et des sections de l'accueil, une
 * accroche et le libellé du bouton de réservation. Le serveur refuse tout ce
 * qui sort de ces listes — aucun champ n'accepte de HTML, de CSS ni de script.
 *
 * L'aperçu suit chaque geste, avant l'enregistrement : on voit ce que verront
 * les clientes, pas un formulaire à imaginer.
 */

import { useState } from "react";

import { DashboardError, dashboardFetch } from "@/lib/dashboard";
import { TOUTES_LES_POLICES, familleDe } from "@/lib/polices";
import {
  Button,
  Card,
  ErrorState,
  Field,
  GhostButton,
  PageHeader,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { useDashboard } from "./DashboardShell";
import { Icon } from "./icons";
import { EnteteCarte, VerrouPro } from "./Pro";
import { useResource } from "./useResource";

interface Rubrique {
  cle: string;
  visible: boolean;
}

interface Config {
  police_titres: string;
  police_texte: string;
  menu: Rubrique[];
  sections: Rubrique[];
  accroche: string;
  bouton_reserver: string;
}

interface Reponse {
  config: Config;
  options: {
    polices: { cle: string; nom: string }[];
    menu: string[];
    sections: string[];
    longueurs: { accroche: number; bouton_reserver: number };
  };
  active: boolean;
}

const NOMS_MENU: Record<string, string> = {
  prestations: "Prestations",
  realisations: "Réalisations",
  equipe: "Équipe",
  "a-propos": "À propos",
  infos: "Infos pratiques",
};

const NOMS_SECTIONS: Record<string, string> = {
  prestations: "Prestations en vedette",
  etapes: "Comment ça se passe",
  realisations: "Réalisations",
  equipe: "L'équipe",
  avis: "Avis des clientes",
  infos: "Infos pratiques",
};

export function Apparence() {
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const direction = membership.role === "owner" || membership.role === "manager";
  const toast = useToast();

  const donnees = useResource<Reponse>("/api/v1/site-pro", tenantId, { enabled: direction });
  // Le brouillon n'existe qu'une fois qu'on a touché à quelque chose ;
  // avant, c'est la configuration du serveur qu'on montre.
  const [brouillon, setBrouillon] = useState<Config | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const reference = donnees.data?.config ?? null;
  const config = brouillon ?? reference;

  if (!direction) {
    return (
      <section>
        <PageHeader title="Apparence avancée" />
        <ErrorState>Réservé au propriétaire et à la gérante du salon.</ErrorState>
      </section>
    );
  }

  if (donnees.error) return <ErrorState>{donnees.error}</ErrorState>;
  if (!donnees.data || !config) {
    return (
      <section>
        <PageHeader title="Apparence avancée" />
        <Skeleton rows={4} />
      </section>
    );
  }

  const { options, active } = donnees.data;
  const modifie = JSON.stringify(config) !== JSON.stringify(reference);

  async function enregistrer() {
    if (!config) return;
    setEnvoi(true);
    setErreur(null);
    try {
      await dashboardFetch("/api/v1/site-pro", { method: "PUT", body: JSON.stringify(config) }, tenantId);
      toast.success("Apparence enregistrée : votre mini-site est à jour.");
      setBrouillon(null);
      donnees.reload();
    } catch (caught) {
      setErreur(caught instanceof DashboardError ? caught.message : "Enregistrement impossible.");
    } finally {
      setEnvoi(false);
    }
  }

  const changer = (partiel: Partial<Config>) =>
    setBrouillon((avant) => ({ ...(avant ?? config), ...partiel }));

  return (
    <section className={TOUTES_LES_POLICES}>
      <PageHeader
        title="Apparence avancée"
        description="Polices, menu, ordre des sections et textes clés de votre mini-site. Les couleurs et le logo restent dans « Identité »."
      />

      {!active && <VerrouPro fonction="customization" />}

      <div className="grid gap-4 lg:grid-cols-[1fr_22rem] lg:items-start">
        <fieldset disabled={!active} className="min-w-0 space-y-4 disabled:opacity-60">
          <Card padded={false} className="p-4 sm:p-5">
            <EnteteCarte icone="edit" titre="Polices" detail="Une pour les titres, une pour le texte." />
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <ChoixPolice
                libelle="Titres"
                polices={options.polices}
                valeur={config.police_titres}
                onChange={(cle) => changer({ police_titres: cle })}
              />
              <ChoixPolice
                libelle="Texte"
                polices={options.polices}
                valeur={config.police_texte}
                onChange={(cle) => changer({ police_texte: cle })}
              />
            </div>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card padded={false} className="p-4 sm:p-5">
              <EnteteCarte icone="menu" titre="Menu" detail="L'ordre des rubriques, et celles qu'on voit." />
              <Liste
                elements={config.menu}
                noms={NOMS_MENU}
                onChange={(menu) => changer({ menu })}
              />
              <p className="mt-2 text-[11px] leading-snug text-muted sm:text-xs">
                Une rubrique sans contenu (aucune réalisation, par exemple) reste cachée.
              </p>
            </Card>

            <Card padded={false} className="p-4 sm:p-5">
              <EnteteCarte icone="grid" titre="Accueil" detail="L'ordre des sections, entre l'en-tête et l'appel final." />
              <Liste
                elements={config.sections}
                noms={NOMS_SECTIONS}
                onChange={(sections) => changer({ sections })}
              />
            </Card>
          </div>

          <Card padded={false} className="p-4 sm:p-5">
            <EnteteCarte
              icone="sparkles"
              titre="Textes clés"
              detail="Du texte simple, affiché tel quel dans les deux langues du site."
            />
            <div className="mt-4 grid gap-4 sm:grid-cols-[1fr_14rem]">
              <Field
                label="Accroche de l'en-tête"
                hint={`${config.accroche.length}/${options.longueurs.accroche} — vide : la description du salon.`}
              >
                <textarea
                  className={`${inputClass} min-h-20 resize-y`}
                  value={config.accroche}
                  maxLength={options.longueurs.accroche}
                  onChange={(event) => changer({ accroche: event.target.value.replace(/[<>]/g, "") })}
                  placeholder="Tresses, soins et coiffures, sur rendez-vous à Brazzaville."
                />
              </Field>
              <Field
                label="Bouton de réservation"
                hint={`${config.bouton_reserver.length}/${options.longueurs.bouton_reserver} — vide : « Réserver ».`}
              >
                <input
                  className={inputClass}
                  value={config.bouton_reserver}
                  maxLength={options.longueurs.bouton_reserver}
                  onChange={(event) =>
                    changer({ bouton_reserver: event.target.value.replace(/[<>]/g, "") })
                  }
                  placeholder="Prendre rendez-vous"
                />
              </Field>
            </div>
          </Card>
        </fieldset>

        <div className="space-y-3 lg:sticky lg:top-6">
          <Apercu config={config} nom={membership.tenant.name} />

          {erreur && <ErrorState>{erreur}</ErrorState>}

          <div className="sticky bottom-0 z-10 -mx-4 flex gap-2 border-t border-line bg-surface/95 px-4 py-3 pr-20 backdrop-blur sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0 sm:pr-0 lg:flex-col">
            <Button
              type="button"
              onClick={enregistrer}
              pending={envoi}
              disabled={!active || !modifie}
              className="flex-1"
            >
              Enregistrer
            </Button>
            <GhostButton
              type="button"
              disabled={!active || !modifie}
              onClick={() => setBrouillon(null)}
              className="flex-1"
            >
              Annuler les changements
            </GhostButton>
          </div>
        </div>
      </div>
    </section>
  );
}

function ChoixPolice({
  libelle,
  polices,
  valeur,
  onChange,
}: {
  libelle: string;
  polices: { cle: string; nom: string }[];
  valeur: string;
  onChange: (cle: string) => void;
}) {
  return (
    <div>
      <p className="mb-2 text-sm font-medium text-ink">{libelle}</p>
      <div role="radiogroup" aria-label={libelle} className="grid grid-cols-3 gap-1.5">
        {polices.map((police) => (
          <button
            key={police.cle}
            type="button"
            role="radio"
            aria-checked={valeur === police.cle}
            title={police.nom}
            onClick={() => onChange(police.cle)}
            className={`flex min-w-0 flex-col items-center rounded-xl border px-1 py-2 transition ${
              valeur === police.cle
                ? "border-salon bg-salon-soft ring-1 ring-salon"
                : "border-line hover:border-line-strong"
            }`}
          >
            <span className="text-xl leading-none text-ink" style={{ fontFamily: familleDe(police.cle) }}>
              Aa
            </span>
            <span className="mt-1 w-full truncate text-center text-[10px] text-muted sm:text-[11px]">
              {police.nom.replace(" (par défaut)", "")}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

/** Une liste ordonnable : flèches pour déplacer (fiables au pouce), œil pour montrer. */
function Liste({
  elements,
  noms,
  onChange,
}: {
  elements: Rubrique[];
  noms: Record<string, string>;
  onChange: (elements: Rubrique[]) => void;
}) {
  function deplacer(index: number, sens: -1 | 1) {
    const cible = index + sens;
    if (cible < 0 || cible >= elements.length) return;
    const copie = [...elements];
    [copie[index], copie[cible]] = [copie[cible], copie[index]];
    onChange(copie);
  }

  return (
    <ol className="mt-3 space-y-1.5">
      {elements.map((element, index) => (
        <li
          key={element.cle}
          className={`flex items-center gap-2 rounded-xl border border-line px-2.5 py-1.5 transition ${
            element.visible ? "bg-surface" : "bg-surface-muted"
          }`}
        >
          <span className="tabular w-4 text-center text-[11px] text-subtle">{index + 1}</span>
          <span
            className={`min-w-0 flex-1 truncate text-[13px] sm:text-sm ${
              element.visible ? "font-medium text-ink" : "text-subtle line-through"
            }`}
          >
            {noms[element.cle] ?? element.cle}
          </span>
          <button
            type="button"
            onClick={() =>
              onChange(
                elements.map((item) =>
                  item.cle === element.cle ? { ...item, visible: !item.visible } : item,
                ),
              )
            }
            aria-label={element.visible ? `Masquer ${noms[element.cle]}` : `Montrer ${noms[element.cle]}`}
            aria-pressed={!element.visible}
            className={`flex size-8 items-center justify-center rounded-lg transition hover:bg-surface-hover ${
              element.visible ? "text-salon" : "text-subtle"
            }`}
          >
            <Icon name={element.visible ? "eye" : "close"} className="size-4" />
          </button>
          <button
            type="button"
            onClick={() => deplacer(index, -1)}
            disabled={index === 0}
            aria-label={`Monter ${noms[element.cle]}`}
            className="flex size-8 items-center justify-center rounded-lg text-muted transition hover:bg-surface-hover disabled:opacity-30"
          >
            <Icon name="chevron-left" className="size-4 rotate-90" />
          </button>
          <button
            type="button"
            onClick={() => deplacer(index, 1)}
            disabled={index === elements.length - 1}
            aria-label={`Descendre ${noms[element.cle]}`}
            className="flex size-8 items-center justify-center rounded-lg text-muted transition hover:bg-surface-hover disabled:opacity-30"
          >
            <Icon name="chevron-right" className="size-4 rotate-90" />
          </button>
        </li>
      ))}
    </ol>
  );
}

/** Le haut du mini-site, en miniature, avec les réglages en cours. */
function Apercu({ config, nom }: { config: Config; nom: string }) {
  const menu = config.menu.filter((item) => item.visible).map((item) => NOMS_MENU[item.cle] ?? item.cle);
  const sections = config.sections.filter((item) => item.visible);
  return (
    <Card padded={false} className="overflow-hidden">
      <p className="flex items-center gap-1.5 border-b border-line px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-subtle">
        <Icon name="eye" className="size-3.5" /> Aperçu
      </p>
      <div style={{ fontFamily: familleDe(config.police_texte) }}>
        <div className="flex items-center gap-2 overflow-hidden border-b border-line px-3 py-2">
          <span className="shrink-0 text-[12px] font-semibold text-ink">{nom}</span>
          <span className="ml-auto flex min-w-0 gap-2 overflow-hidden text-[10.5px] text-muted">
            {menu.map((item) => (
              <span key={item} className="shrink-0">
                {item}
              </span>
            ))}
          </span>
        </div>
        <div className="salon-gradient px-4 py-6 text-white">
          <p className="text-2xl font-semibold leading-tight" style={{ fontFamily: familleDe(config.police_titres) }}>
            {nom}
          </p>
          <p className="mt-2 line-clamp-3 text-[12.5px] leading-relaxed opacity-90">
            {config.accroche || "La description de votre salon s'affiche ici."}
          </p>
          {/* Encre fixe : le bouton reste blanc dans les deux thèmes du produit. */}
          <span className="mt-3 inline-flex rounded-lg bg-white px-3 py-1.5 text-[12px] font-semibold text-[#17171c]">
            {config.bouton_reserver || "Réserver"}
          </span>
        </div>
        <ol className="space-y-1 px-4 py-3">
          {sections.map((section, index) => (
            <li key={section.cle} className="flex items-center gap-2 text-[12px] text-muted">
              <span className="tabular flex size-4.5 items-center justify-center rounded-full bg-surface-muted text-[10px]">
                {index + 1}
              </span>
              <span style={{ fontFamily: familleDe(config.police_titres) }} className="text-ink">
                {NOMS_SECTIONS[section.cle] ?? section.cle}
              </span>
            </li>
          ))}
        </ol>
      </div>
    </Card>
  );
}
