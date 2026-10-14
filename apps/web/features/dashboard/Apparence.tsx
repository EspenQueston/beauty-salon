"use client";

/**
 * Apparence avancée du mini-site (offre Pro).
 *
 * Des choix, pas du code : deux polices dans une liste fermée, l'ordre et la
 * visibilité des rubriques du menu et des sections de l'accueil, jusqu'à
 * trois pages écrites par le salon, une accroche et le libellé du bouton de
 * réservation. Le serveur refuse tout ce qui sort de ces listes — aucun
 * champ n'accepte de HTML, de CSS ni de script.
 *
 * L'aperçu suit chaque geste, avant l'enregistrement : on voit ce que verront
 * les clientes, pas un formulaire à imaginer. Tant que rien n'est enregistré,
 * une barre le rappelle, et quitter la page demande confirmation.
 */

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { DashboardError, dashboardFetch } from "@/lib/dashboard";
import { TOUTES_LES_POLICES, familleDe } from "@/lib/polices";
import {
  Badge,
  Button,
  Card,
  DangerButton,
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
import { MediaPicker, type PickableMedia } from "./MediaPicker";
import { EnteteCarte, VerrouPro } from "./Pro";
import { rows, useResource, type Page } from "./useResource";

// ---------------------------------------------------------------------------
// Formes de l'API
// ---------------------------------------------------------------------------

interface Rubrique {
  cle: string;
  visible: boolean;
}

interface PageSalon {
  id: string;
  titre: string;
  slug?: string;
  accroche: string;
  contenu: string;
  image: string | null;
}

interface Config {
  police_titres: string;
  police_texte: string;
  menu: Rubrique[];
  sections: Rubrique[];
  accroche: string;
  bouton_reserver: string;
  pages: PageSalon[];
}

type Famille = "moderne" | "elegante" | "affiche" | "manuscrite";

interface Police {
  cle: string;
  nom: string;
  famille: Famille;
  texte: boolean;
}

interface Reponse {
  config: Config;
  options: {
    polices: Police[];
    menu: string[];
    sections: string[];
    pages_max: number;
    longueurs: {
      accroche: number;
      bouton_reserver: number;
      titre_page: number;
      contenu_page: number;
    };
  };
  active: boolean;
}

/** Les rubriques connues ; libellés sous `pro.apparence.menu` et `.sections`. */
const MENU_CONNU = ["prestations", "realisations", "equipe", "a-propos", "infos"];
const SECTIONS_CONNUES = ["prestations", "etapes", "realisations", "equipe", "avis", "infos"];

const FAMILLES: (Famille | "toutes")[] = ["toutes", "moderne", "elegante", "affiche", "manuscrite"];

/** Des accords éprouvés : un titre qui a du caractère, un texte qui se lit. */
const ACCORDS: { titres: string; texte: string; cle: string }[] = [
  { titres: "playfair", texte: "nunito", cle: "classique" },
  { titres: "great-vibes", texte: "raleway", cle: "romantique" },
  { titres: "cinzel", texte: "manrope", cle: "luxe" },
  { titres: "fraunces", texte: "outfit", cle: "contemporain" },
  { titres: "dm-serif", texte: "poppins", cle: "editorial" },
  { titres: "montserrat", texte: "montserrat", cle: "epure" },
];

const PREFIXE_PAGE = "page:";

// ---------------------------------------------------------------------------
// Outils
// ---------------------------------------------------------------------------

/** Le même calcul que le serveur : « Tarifs & Forfaits » -> « tarifs-forfaits ». */
function slugDe(titre: string): string {
  const slug = titre
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32)
    .replace(/-+$/g, "");
  return slug || "page";
}

function nouvelIdentifiant(): string {
  const octets = new Uint8Array(4);
  crypto.getRandomValues(octets);
  return Array.from(octets, (o) => o.toString(16).padStart(2, "0")).join("");
}

/** Un texte brut : les chevrons sont refusés par le serveur, on les retire à la saisie. */
const brut = (valeur: string) => valeur.replace(/[<>]/g, "");

// ---------------------------------------------------------------------------
// La page
// ---------------------------------------------------------------------------

export function Apparence() {
  const t = useTranslations("pro.apparence");
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const direction = membership.role === "owner" || membership.role === "manager";
  const toast = useToast();

  const donnees = useResource<Reponse>("/api/v1/site-pro", tenantId, { enabled: direction });
  const medias = useResource<Page<PickableMedia>>("/api/v1/media/?page_size=100", tenantId, {
    enabled: direction,
  });
  // Le brouillon n'existe qu'une fois qu'on a touché à quelque chose ;
  // avant, c'est la configuration du serveur qu'on montre.
  const [brouillon, setBrouillon] = useState<Config | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [ouverte, setOuverte] = useState<string | null>(null);
  const reference = donnees.data?.config ?? null;
  const config = brouillon ?? reference;
  const modifie = Boolean(brouillon) && JSON.stringify(brouillon) !== JSON.stringify(reference);

  // Quitter avec des changements non enregistrés demande confirmation.
  useEffect(() => {
    if (!modifie) return;
    const retenir = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", retenir);
    return () => window.removeEventListener("beforeunload", retenir);
  }, [modifie]);

  if (!direction) {
    return (
      <section>
        <PageHeader title={t("titre")} />
        <ErrorState>{t("reserve")}</ErrorState>
      </section>
    );
  }

  if (donnees.error) return <ErrorState>{donnees.error}</ErrorState>;
  if (!donnees.data || !config) {
    return (
      <section>
        <PageHeader title={t("titre")} />
        <Skeleton rows={4} />
      </section>
    );
  }

  const { options, active } = donnees.data;
  const changer = (partiel: Partial<Config>) =>
    setBrouillon((avant) => ({ ...(avant ?? config), ...partiel }));

  // Une page et son entrée de menu vivent ensemble : ajoutée, elle rejoint
  // le menu à la fin, visible ; retirée, elle en sort.
  function ajouterPage() {
    if (!config || config.pages.length >= options.pages_max) return;
    const page: PageSalon = {
      id: nouvelIdentifiant(),
      titre: "",
      accroche: "",
      contenu: "",
      image: null,
    };
    changer({
      pages: [...config.pages, page],
      menu: [...config.menu, { cle: PREFIXE_PAGE + page.id, visible: true }],
    });
    setOuverte(page.id);
  }

  function modifierPage(id: string, partiel: Partial<PageSalon>) {
    if (!config) return;
    changer({ pages: config.pages.map((p) => (p.id === id ? { ...p, ...partiel } : p)) });
  }

  function retirerPage(id: string) {
    if (!config) return;
    changer({
      pages: config.pages.filter((p) => p.id !== id),
      menu: config.menu.filter((entree) => entree.cle !== PREFIXE_PAGE + id),
    });
  }

  const pageIncomplete = config.pages.find((p) => p.titre.trim().length < 2);

  async function enregistrer() {
    if (!config) return;
    if (pageIncomplete) {
      setOuverte(pageIncomplete.id);
      setErreur(t("titreRequis"));
      return;
    }
    setEnvoi(true);
    setErreur(null);
    try {
      await dashboardFetch(
        "/api/v1/site-pro",
        { method: "PUT", body: JSON.stringify(config) },
        tenantId,
      );
      toast.success(t("ok"));
      setBrouillon(null);
      donnees.reload();
    } catch (caught) {
      setErreur(caught instanceof DashboardError ? caught.message : t("echec"));
    } finally {
      setEnvoi(false);
    }
  }

  const nomRubrique = (cle: string) => {
    if (cle.startsWith(PREFIXE_PAGE)) {
      const page = config.pages.find((p) => PREFIXE_PAGE + p.id === cle);
      return page?.titre.trim() || t("nouvellePage");
    }
    return MENU_CONNU.includes(cle) ? t(`menu.${cle}`) : cle;
  };

  return (
    <section className={TOUTES_LES_POLICES}>
      <PageHeader
        title={t("titre")}
        description={t("description")}
      />

      {!active && <VerrouPro fonction="customization" />}

      {/* minmax(0, 1fr) des le telephone : sans lui, la piste prend la largeur
          minimale de son contenu (la ligne de menu de l'apercu) et la page
          deborde de 13 pixels. */}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_21rem] lg:items-start">
        <fieldset disabled={!active} className="min-w-0 space-y-4 disabled:opacity-60">
          <Polices
            polices={options.polices}
            titres={config.police_titres}
            texte={config.police_texte}
            onChange={changer}
          />

          <Card padded={false} className="p-4 sm:p-5">
            <EnteteCarte
              icone="edit"
              titre={t("pages.titre")}
              detail={t("pages.detail")}
              statut={
                <Badge tone={config.pages.length >= options.pages_max ? "warning" : "neutral"}>
                  {config.pages.length}/{options.pages_max}
                </Badge>
              }
            />
            <div className="mt-4 space-y-2.5">
              {config.pages.map((page, index) => (
                <EditeurPage
                  key={page.id}
                  page={page}
                  numero={index + 1}
                  ouverte={ouverte === page.id}
                  onBasculer={() => setOuverte(ouverte === page.id ? null : page.id)}
                  onChange={(partiel) => modifierPage(page.id, partiel)}
                  onRetirer={() => retirerPage(page.id)}
                  longueurs={options.longueurs}
                  medias={rows(medias.data)}
                  onTeleverse={medias.reload}
                  tenantId={tenantId}
                />
              ))}
              {config.pages.length < options.pages_max ? (
                <button
                  type="button"
                  onClick={ajouterPage}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-line-strong px-4 py-3 text-sm font-medium text-muted transition hover:border-salon hover:bg-salon-soft/40 hover:text-salon"
                >
                  <Icon name="plus" className="size-4" />
                  {t("pages.ajouter")}
                </button>
              ) : (
                <p className="rounded-xl bg-surface-muted px-3 py-2 text-center text-[12px] text-muted sm:text-xs">
                  {t("pages.max")}
                </p>
              )}
            </div>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card padded={false} className="p-4 sm:p-5">
              <EnteteCarte icone="menu" titre={t("menuTitre")} detail={t("menuDetail")} />
              <Liste
                elements={config.menu}
                nom={nomRubrique}
                estPage={(cle) => cle.startsWith(PREFIXE_PAGE)}
                onChange={(menu) => changer({ menu })}
              />
              <p className="mt-2 text-[11px] leading-snug text-muted sm:text-xs">
                {t("menuVide")}
              </p>
            </Card>

            <Card padded={false} className="p-4 sm:p-5">
              <EnteteCarte
                icone="grid"
                titre={t("accueilTitre")}
                detail={t("accueilDetail")}
              />
              <Liste
                elements={config.sections}
                nom={(cle) => (SECTIONS_CONNUES.includes(cle) ? t(`sections.${cle}`) : cle)}
                onChange={(sections) => changer({ sections })}
              />
            </Card>
          </div>

          <Card padded={false} className="p-4 sm:p-5">
            <EnteteCarte
              icone="sparkles"
              titre={t("textes.titre")}
              detail={t("textes.detail")}
            />
            <div className="mt-4 grid gap-4 sm:grid-cols-[1fr_14rem]">
              <Field
                label={t("textes.accroche")}
                hint={t("textes.accrocheAide", {
                  n: config.accroche.length,
                  max: options.longueurs.accroche,
                })}
              >
                <textarea
                  className={`${inputClass} min-h-20 resize-y`}
                  value={config.accroche}
                  maxLength={options.longueurs.accroche}
                  onChange={(event) => changer({ accroche: brut(event.target.value) })}
                  placeholder={t("textes.accrocheExemple")}
                />
              </Field>
              <Field
                label={t("textes.bouton")}
                hint={t("textes.boutonAide", {
                  n: config.bouton_reserver.length,
                  max: options.longueurs.bouton_reserver,
                })}
              >
                <input
                  className={inputClass}
                  value={config.bouton_reserver}
                  maxLength={options.longueurs.bouton_reserver}
                  onChange={(event) => changer({ bouton_reserver: brut(event.target.value) })}
                  placeholder={t("textes.boutonExemple")}
                />
              </Field>
            </div>
          </Card>
        </fieldset>

        <div className="min-w-0 space-y-3 lg:sticky lg:top-6">
          <Apercu config={config} nom={membership.tenant.name} nomRubrique={nomRubrique} />

          {erreur && <ErrorState>{erreur}</ErrorState>}

          {/* Sur grand écran, sous l'aperçu qui reste en vue. */}
          <div className="hidden sm:block">
            <Actions
              modifie={modifie}
              actif={active}
              envoi={envoi}
              onEnregistrer={enregistrer}
              onAnnuler={() => {
                setBrouillon(null);
                setErreur(null);
              }}
            />
          </div>
        </div>
      </div>

      {/*
        Sur téléphone, collée au bas de l'écran dès qu'il y a quelque chose
        à enregistrer : l'écran est long, et choisir une police tout en haut
        ne doit pas obliger à descendre jusqu'en bas pour la garder. La marge
        droite laisse la place au bouton flottant des réglages.
      */}
      {modifie && (
        <>
          <div aria-hidden className="h-28 sm:hidden" />
          <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pr-20 pt-3 shadow-[0_-8px_24px_rgb(0_0_0/0.12)] backdrop-blur sm:hidden">
            {erreur && <p className="mb-2 text-[12px] font-medium text-danger">{erreur}</p>}
            <Actions
              modifie={modifie}
              actif={active}
              envoi={envoi}
              onEnregistrer={enregistrer}
              onAnnuler={() => {
                setBrouillon(null);
                setErreur(null);
              }}
            />
          </div>
        </>
      )}
    </section>
  );
}

function Actions({
  modifie,
  actif,
  envoi,
  onEnregistrer,
  onAnnuler,
}: {
  modifie: boolean;
  actif: boolean;
  envoi: boolean;
  onEnregistrer: () => void;
  onAnnuler: () => void;
}) {
  const t = useTranslations("pro.apparence");
  return (
    <div>
      {modifie && (
        <p className="mb-2 flex items-center gap-1.5 text-[12px] font-medium text-warning sm:text-xs">
          <span className="size-1.5 animate-pulse rounded-full bg-warning" aria-hidden />
          {t("nonEnregistre")}
        </p>
      )}
      <div className="flex gap-2 lg:flex-col">
        <Button
          type="button"
          onClick={onEnregistrer}
          pending={envoi}
          disabled={!actif || !modifie}
          className="flex-1"
        >
          {t("enregistrer")}
        </Button>
        <GhostButton type="button" disabled={!actif || !modifie} onClick={onAnnuler} className="flex-1">
          {t("annuler")}
        </GhostButton>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Les polices
// ---------------------------------------------------------------------------

function Polices({
  polices,
  titres,
  texte,
  onChange,
}: {
  polices: Police[];
  titres: string;
  texte: string;
  onChange: (partiel: Partial<Config>) => void;
}) {
  const t = useTranslations("pro.apparence.polices");
  const [cible, setCible] = useState<"titres" | "texte">("titres");
  const [famille, setFamille] = useState<Famille | "toutes">("toutes");

  // Pour le texte courant, seules les polices lisibles en paragraphe.
  const proposees = useMemo(
    () =>
      polices.filter(
        (police) =>
          (cible === "titres" || police.texte) && (famille === "toutes" || police.famille === famille),
      ),
    [polices, cible, famille],
  );
  const familles = FAMILLES.filter(
    (f) =>
      f === "toutes" ||
      polices.some((p) => p.famille === f && (cible === "titres" || p.texte)),
  );
  const valeur = cible === "titres" ? titres : texte;
  const nomDe = (cle: string) => polices.find((p) => p.cle === cle)?.nom ?? cle;

  return (
    <Card padded={false} className="p-4 sm:p-5">
      <EnteteCarte
        icone="edit"
        titre={t("titre")}
        detail={t("resume", { titres: nomDe(titres), texte: nomDe(texte) })}
      />

      {/* Les accords, d'un geste : titre et texte ensemble. */}
      <div className="mt-4">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-subtle">
          {t("accords")}
        </p>
        <div className="barre-discrete -mx-1 flex snap-x gap-2 overflow-x-auto px-1 pb-1.5">
          {ACCORDS.map((accord) => {
            const choisi = titres === accord.titres && texte === accord.texte;
            return (
              <button
                key={accord.cle}
                type="button"
                onClick={() => onChange({ police_titres: accord.titres, police_texte: accord.texte })}
                aria-pressed={choisi}
                className={`min-w-[8.5rem] shrink-0 snap-start rounded-xl border px-3 py-2 text-left transition ${
                  choisi
                    ? "border-salon bg-salon-soft ring-1 ring-salon"
                    : "border-line hover:border-line-strong hover:bg-surface-hover"
                }`}
              >
                <span
                  className="block truncate text-base leading-tight text-ink"
                  style={{ fontFamily: familleDe(accord.titres) }}
                >
                  {t("exempleAccord")}
                </span>
                <span
                  className="mt-0.5 block truncate text-[11px] text-muted"
                  style={{ fontFamily: familleDe(accord.texte) }}
                >
                  {t(`accordsNoms.${accord.cle}`)}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div role="tablist" aria-label={t("aChoisir")} className="inline-grid grid-cols-2 rounded-xl border border-line bg-surface-muted p-1">
          {(["titres", "texte"] as const).map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={cible === item}
              onClick={() => {
                setCible(item);
                if (item === "texte" && (famille === "affiche" || famille === "manuscrite")) {
                  setFamille("toutes");
                }
              }}
              className={`rounded-lg px-4 py-1.5 text-[13px] font-semibold transition sm:px-5 sm:text-sm ${
                cible === item ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink"
              }`}
            >
              {item === "titres" ? t("titres") : t("texte")}
            </button>
          ))}
        </div>
        <div className="barre-discrete -mx-1 flex max-w-full gap-1.5 overflow-x-auto px-1 pb-1">
          {familles.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFamille(f)}
              aria-pressed={famille === f}
              className={`shrink-0 rounded-full border px-3 py-1 text-xs font-medium transition ${
                famille === f
                  ? "border-salon bg-salon text-white"
                  : "border-line text-muted hover:text-ink"
              }`}
            >
              {t(`familles.${f}`)}
            </button>
          ))}
        </div>
      </div>

      <div
        role="radiogroup"
        aria-label={cible === "titres" ? t("policeTitres") : t("policeTexte")}
        className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4"
      >
        {proposees.map((police) => {
          const choisie = valeur === police.cle;
          return (
            <button
              key={police.cle}
              type="button"
              role="radio"
              aria-checked={choisie}
              onClick={() =>
                onChange(cible === "titres" ? { police_titres: police.cle } : { police_texte: police.cle })
              }
              className={`group relative flex min-w-0 flex-col rounded-xl border p-3 text-left transition active:scale-[0.98] ${
                choisie
                  ? "border-salon bg-salon-soft/60 ring-1 ring-salon"
                  : "border-line hover:-translate-y-0.5 hover:border-line-strong hover:shadow-sm"
              }`}
            >
              {choisie && (
                <span className="absolute right-2 top-2 flex size-4 items-center justify-center rounded-full bg-salon text-white">
                  <Icon name="check" className="size-3" />
                </span>
              )}
              <span
                className="text-2xl leading-none text-ink sm:text-[1.7rem]"
                style={{ fontFamily: familleDe(police.cle) }}
              >
                Aa
              </span>
              <span
                className="mt-1.5 truncate text-[12px] text-ink/80 sm:text-[13px]"
                style={{ fontFamily: familleDe(police.cle) }}
              >
                {cible === "titres" ? t("exempleTitre") : t("exempleTexte")}
              </span>
              <span className="mt-1 truncate text-[10.5px] text-subtle sm:text-[11px]">{police.nom}</span>
            </button>
          );
        })}
      </div>
      {cible === "texte" && (
        <p className="mt-2 text-[11px] text-muted sm:text-xs">
          {t("reserveesTitres")}
        </p>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Une page du salon
// ---------------------------------------------------------------------------

function EditeurPage({
  page,
  numero,
  ouverte,
  onBasculer,
  onChange,
  onRetirer,
  longueurs,
  medias,
  onTeleverse,
  tenantId,
}: {
  page: PageSalon;
  numero: number;
  ouverte: boolean;
  onBasculer: () => void;
  onChange: (partiel: Partial<PageSalon>) => void;
  onRetirer: () => void;
  longueurs: Reponse["options"]["longueurs"];
  medias: PickableMedia[];
  onTeleverse: () => void;
  tenantId: string;
}) {
  const t = useTranslations("pro.apparence.page");
  const [confirmer, setConfirmer] = useState(false);
  const titre = page.titre.trim();

  return (
    <div
      className={`overflow-hidden rounded-xl border transition ${
        ouverte ? "border-salon/60 shadow-sm" : "border-line"
      }`}
    >
      <button
        type="button"
        onClick={onBasculer}
        aria-expanded={ouverte}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition hover:bg-surface-hover"
      >
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-salon-soft text-[12px] font-semibold text-salon">
          {numero}
        </span>
        <span className="min-w-0 flex-1">
          <span className={`block truncate text-sm font-medium ${titre ? "text-ink" : "text-subtle"}`}>
            {titre || t("sansTitre")}
          </span>
          <span className="block truncate font-mono text-[11px] text-subtle">/p/{slugDe(titre)}</span>
        </span>
        <Icon
          name="chevron-right"
          className={`size-4 shrink-0 text-muted transition-transform ${ouverte ? "rotate-90" : ""}`}
        />
      </button>

      {ouverte && (
        <div className="space-y-3 border-t border-line p-3 sm:p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field
              label={t("titre")}
              hint={`${page.titre.length}/${longueurs.titre_page}`}
            >
              <input
                className={inputClass}
                value={page.titre}
                maxLength={longueurs.titre_page}
                onChange={(event) => onChange({ titre: brut(event.target.value) })}
                placeholder={t("titreExemple")}
                autoFocus={!page.titre}
              />
            </Field>
            <Field label={t("accroche")} hint={t("accrocheAide")}>
              <input
                className={inputClass}
                value={page.accroche}
                maxLength={160}
                onChange={(event) => onChange({ accroche: brut(event.target.value) })}
                placeholder={t("accrocheExemple")}
              />
            </Field>
          </div>
          <Field
            label={t("contenu")}
            hint={t("contenuAide", { n: page.contenu.length, max: longueurs.contenu_page })}
          >
            <textarea
              className={`${inputClass} min-h-36 resize-y leading-relaxed`}
              value={page.contenu}
              maxLength={longueurs.contenu_page}
              onChange={(event) => onChange({ contenu: brut(event.target.value) })}
              placeholder={t("contenuExemple")}
            />
          </Field>
          <MediaPicker
            tenantId={tenantId}
            assets={medias}
            value={page.image}
            onChange={(id) => onChange({ image: id })}
            onUploaded={onTeleverse}
            label={t("image")}
            hint={t("imageAide")}
            kind="about"
          />
          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line pt-3">
            {confirmer ? (
              <>
                <span className="mr-auto text-[12px] text-muted sm:text-sm">
                  {t("confirmer")}
                </span>
                <GhostButton type="button" onClick={() => setConfirmer(false)}>
                  {t("garder")}
                </GhostButton>
                <DangerButton type="button" onClick={onRetirer}>
                  {t("retirer")}
                </DangerButton>
              </>
            ) : (
              <GhostButton
                type="button"
                onClick={() => setConfirmer(true)}
                icon={<Icon name="close" className="size-4" />}
              >
                {t("retirerPage")}
              </GhostButton>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Une liste ordonnable
// ---------------------------------------------------------------------------

/** Flèches pour déplacer (fiables au pouce), œil pour montrer ou cacher. */
function Liste({
  elements,
  nom,
  estPage,
  onChange,
}: {
  elements: Rubrique[];
  nom: (cle: string) => string;
  estPage?: (cle: string) => boolean;
  onChange: (elements: Rubrique[]) => void;
}) {
  const t = useTranslations("pro.apparence.liste");
  function deplacer(index: number, sens: -1 | 1) {
    const cible = index + sens;
    if (cible < 0 || cible >= elements.length) return;
    const copie = [...elements];
    [copie[index], copie[cible]] = [copie[cible], copie[index]];
    onChange(copie);
  }

  return (
    <ol className="mt-3 space-y-1.5">
      {elements.map((element, index) => {
        const libelle = nom(element.cle);
        return (
          <li
            key={element.cle}
            className={`flex items-center gap-1.5 rounded-xl border border-line px-2 py-1.5 transition sm:gap-2 sm:px-2.5 ${
              element.visible ? "bg-surface" : "bg-surface-muted"
            }`}
          >
            <span className="tabular w-4 text-center text-[11px] text-subtle">{index + 1}</span>
            <span
              className={`min-w-0 flex-1 truncate text-[13px] sm:text-sm ${
                element.visible ? "font-medium text-ink" : "text-subtle line-through"
              }`}
            >
              {libelle}
            </span>
            {estPage?.(element.cle) && (
              <span className="shrink-0 rounded-full bg-salon-soft px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-salon">
                {t("page")}
              </span>
            )}
            <button
              type="button"
              onClick={() =>
                onChange(
                  elements.map((item) =>
                    item.cle === element.cle ? { ...item, visible: !item.visible } : item,
                  ),
                )
              }
              aria-label={element.visible ? t("masquer", { nom: libelle }) : t("montrer", { nom: libelle })}
              aria-pressed={!element.visible}
              className={`flex size-8 shrink-0 items-center justify-center rounded-lg transition hover:bg-surface-hover ${
                element.visible ? "text-salon" : "text-subtle"
              }`}
            >
              <Icon name={element.visible ? "eye" : "close"} className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => deplacer(index, -1)}
              disabled={index === 0}
              aria-label={t("monter", { nom: libelle })}
              className="flex size-8 shrink-0 items-center justify-center rounded-lg text-muted transition hover:bg-surface-hover disabled:opacity-30"
            >
              <Icon name="chevron-left" className="size-4 rotate-90" />
            </button>
            <button
              type="button"
              onClick={() => deplacer(index, 1)}
              disabled={index === elements.length - 1}
              aria-label={t("descendre", { nom: libelle })}
              className="flex size-8 shrink-0 items-center justify-center rounded-lg text-muted transition hover:bg-surface-hover disabled:opacity-30"
            >
              <Icon name="chevron-right" className="size-4 rotate-90" />
            </button>
          </li>
        );
      })}
    </ol>
  );
}

// ---------------------------------------------------------------------------
// L'aperçu
// ---------------------------------------------------------------------------

/** Le haut du mini-site, en miniature, avec les réglages en cours. */
function Apercu({
  config,
  nom,
  nomRubrique,
}: {
  config: Config;
  nom: string;
  nomRubrique: (cle: string) => string;
}) {
  const t = useTranslations("pro.apparence");
  const menu = config.menu.filter((item) => item.visible);
  const sections = config.sections.filter((item) => item.visible);
  return (
    <Card padded={false} className="overflow-hidden">
      <p className="flex items-center gap-1.5 border-b border-line px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-subtle">
        <Icon name="eye" className="size-3.5" /> {t("apercu.titre")}
      </p>
      <div style={{ fontFamily: familleDe(config.police_texte) }}>
        <div className="flex items-center gap-2 border-b border-line px-3 py-2">
          <span className="shrink-0 text-[12px] font-semibold text-ink">{nom}</span>
          <span className="ml-auto flex min-w-0 gap-2 overflow-hidden text-[10.5px] text-muted [mask-image:linear-gradient(to_right,black_85%,transparent)]">
            {menu.map((item) => (
              <span
                key={item.cle}
                className={`shrink-0 ${item.cle.startsWith(PREFIXE_PAGE) ? "font-semibold text-salon" : ""}`}
              >
                {nomRubrique(item.cle)}
              </span>
            ))}
          </span>
        </div>
        <div className="salon-gradient px-4 py-6 text-white">
          <p
            className="text-2xl font-semibold leading-tight"
            style={{ fontFamily: familleDe(config.police_titres) }}
          >
            {nom}
          </p>
          <p className="mt-2 line-clamp-3 text-[12.5px] leading-relaxed opacity-90">
            {config.accroche || t("apercu.description")}
          </p>
          {/* Encre fixe : le bouton reste blanc dans les deux thèmes du produit. */}
          <span className="mt-3 inline-flex rounded-lg bg-white px-3 py-1.5 text-[12px] font-semibold text-[#17171c]">
            {config.bouton_reserver || t("apercu.reserver")}
          </span>
        </div>
        <ol className="space-y-1 px-4 py-3">
          {sections.map((section, index) => (
            <li key={section.cle} className="flex items-center gap-2 text-[12px] text-muted">
              <span className="tabular flex size-4.5 items-center justify-center rounded-full bg-surface-muted text-[10px]">
                {index + 1}
              </span>
              <span style={{ fontFamily: familleDe(config.police_titres) }} className="text-ink">
                {SECTIONS_CONNUES.includes(section.cle) ? t(`sections.${section.cle}`) : section.cle}
              </span>
            </li>
          ))}
        </ol>
      </div>
    </Card>
  );
}
