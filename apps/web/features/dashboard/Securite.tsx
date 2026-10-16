"use client";

/**
 * Sécurité du compte : double authentification, mot de passe, sessions.
 *
 * La double authentification se règle ici, en trois temps : scanner le QR
 * code, confirmer avec un premier code et le mot de passe, ranger les codes
 * de secours (montrés une seule fois). Le serveur exige le mot de passe pour
 * l'activer comme pour la retirer : une session volée ne suffit pas à
 * verrouiller la propriétaire dehors.
 */

import { useTranslations } from "next-intl";
import { useState, type FormEvent, type ReactNode } from "react";

import { DashboardError, dashboardFetch, mfa, type EtatMfa } from "@/lib/dashboard";
import { Badge, Button, Card, ErrorState, Field, GhostButton, PageHeader, Skeleton, inputClass } from "@/features/ui";
import { PasswordField } from "@/features/ui/PasswordField";
import { useToast } from "@/features/ui/Toast";
import { useDashboard } from "./DashboardShell";
import { Icon } from "./icons";
import { useResource } from "./useResource";

const codeClass = `${inputClass} text-center font-mono text-lg tracking-[0.3em]`;

function message(caught: unknown, repli: string): string {
  return caught instanceof DashboardError ? caught.message : repli;
}

export function Securite() {
  const t = useTranslations("pro.securite");
  const { membership, reload: rechargerSession } = useDashboard();
  const { data, error, reload } = useResource<EtatMfa>("/api/v1/auth/mfa", membership.tenant.id);

  return (
    <>
      <PageHeader
        title={t("titre")}
        description={t("description")}
      />
      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] lg:gap-6">
        <div className="min-w-0">
          {error ? (
            <ErrorState>{t("erreur")}</ErrorState>
          ) : data === null ? (
            <Skeleton rows={2} />
          ) : (
            <DoubleAuthentification
              etat={data}
              onChange={() => {
                reload();
                rechargerSession();
              }}
            />
          )}
        </div>
        <div className="grid min-w-0 content-start gap-5">
          <MotDePasse />
          <Sessions />
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Double authentification
// ---------------------------------------------------------------------------

function Titre({ icone, children, badge }: { icone: "lock" | "edit" | "clock"; children: ReactNode; badge?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-ink sm:text-base">
        <Icon name={icone} className="size-4 text-salon" />
        {children}
      </h2>
      {badge}
    </div>
  );
}

function DoubleAuthentification({ etat, onChange }: { etat: EtatMfa; onChange: () => void }) {
  const t = useTranslations("pro.securite");
  const [codes, setCodes] = useState<string[] | null>(null);

  if (codes) {
    return (
      <CodesDeSecours
        codes={codes}
        onFini={() => {
          setCodes(null);
          onChange();
        }}
      />
    );
  }

  return (
    <Card>
      <Titre
        icone="lock"
        badge={
          etat.enabled ? (
            <Badge tone="success">{t("activee")}</Badge>
          ) : (
            <Badge tone="warning">{t("desactivee")}</Badge>
          )
        }
      >
        {t("deuxFacteurs")}
      </Titre>
      {etat.enabled ? (
        <Active etat={etat} onCodes={setCodes} onChange={onChange} />
      ) : (
        <Activation onCodes={setCodes} />
      )}
    </Card>
  );
}

function Activation({ onCodes }: { onCodes: (codes: string[]) => void }) {
  const t = useTranslations("pro.securite.activation");
  const toast = useToast();
  const [cle, setCle] = useState<{ qr_svg: string; secret: string } | null>(null);
  const [code, setCode] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [occupe, setOccupe] = useState(false);
  const [erreur, setErreur] = useState("");

  async function commencer() {
    setOccupe(true);
    setErreur("");
    try {
      setCle(await mfa.preparer());
    } catch (caught) {
      setErreur(message(caught, t("preparationEchec")));
    } finally {
      setOccupe(false);
    }
  }

  async function confirmer(event: FormEvent) {
    event.preventDefault();
    setOccupe(true);
    setErreur("");
    try {
      const resultat = await mfa.confirmer(code, motDePasse);
      toast.success(t("ok"));
      onCodes(resultat.codes);
    } catch (caught) {
      setErreur(message(caught, t("echec")));
    } finally {
      setOccupe(false);
    }
  }

  if (!cle) {
    return (
      <>
        <p className="text-[13px] leading-relaxed text-muted sm:text-sm">{t("intro")}</p>
        <ul className="mt-3 grid gap-1.5 text-[13px] text-muted sm:grid-cols-2 sm:text-sm">
          {["Google Authenticator", "Microsoft Authenticator", "1Password, Bitwarden…", t("gratuit")].map(
            (ligne) => (
              <li key={ligne} className="flex items-center gap-1.5">
                <Icon name="check" className="size-3.5 shrink-0 text-success" />
                {ligne}
              </li>
            ),
          )}
        </ul>
        {erreur && <p className="mt-3 text-sm font-medium text-danger">{erreur}</p>}
        <Button type="button" pending={occupe} onClick={() => void commencer()} className="mt-4 w-full sm:w-auto">
          {t("activer")}
        </Button>
      </>
    );
  }

  return (
    <form onSubmit={confirmer} className="grid gap-4">
      <div className="grid gap-4 sm:grid-cols-[auto_minmax(0,1fr)] sm:items-center">
        <div className="mx-auto rounded-2xl border border-line bg-white p-3 sm:mx-0">
          {/* Une image plutôt que du SVG injecté : rien du serveur n'entre
              dans le DOM comme HTML. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`data:image/svg+xml;utf8,${encodeURIComponent(cle.qr_svg)}`}
            alt={t("qr")}
            className="size-40"
          />
        </div>
        <div className="min-w-0 text-[13px] leading-relaxed text-muted sm:text-sm">
          <p>
            <strong className="text-ink">1.</strong> {t("etape1")}
          </p>
          <p className="mt-2">{t("sansCamera")}</p>
          <code className="mt-1 block break-all rounded-lg bg-surface-muted px-2.5 py-1.5 font-mono text-xs text-ink">
            {cle.secret}
          </code>
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("etape2")}>
          <input
            value={code}
            onChange={(event) => setCode(event.target.value)}
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            maxLength={8}
            placeholder="123 456"
            className={codeClass}
          />
        </Field>
        <PasswordField
          label={t("etape3")}
          value={motDePasse}
          onChange={setMotDePasse}
          autoComplete="current-password"
          inputClassName={inputClass}
        />
      </div>
      {erreur && <p className="text-sm font-medium text-danger">{erreur}</p>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" pending={occupe}>
          {t("confirmer")}
        </Button>
        <GhostButton type="button" onClick={() => setCle(null)}>
          {t("annuler")}
        </GhostButton>
      </div>
    </form>
  );
}

function Active({
  etat,
  onCodes,
  onChange,
}: {
  etat: EtatMfa;
  onCodes: (codes: string[]) => void;
  onChange: () => void;
}) {
  const t = useTranslations("pro.securite.active");
  const toast = useToast();
  const [geste, setGeste] = useState<"aucun" | "codes" | "desactiver">("aucun");
  const [code, setCode] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [occupe, setOccupe] = useState(false);
  const [erreur, setErreur] = useState("");

  function ouvrir(suivant: typeof geste) {
    setGeste(suivant);
    setCode("");
    setMotDePasse("");
    setErreur("");
  }

  async function valider(event: FormEvent) {
    event.preventDefault();
    setOccupe(true);
    setErreur("");
    try {
      if (geste === "codes") {
        const resultat = await mfa.nouveauxCodes(motDePasse);
        onCodes(resultat.codes);
      } else {
        await mfa.desactiver(code, motDePasse);
        toast.success(t("desactiveeOk"));
        onChange();
      }
      ouvrir("aucun");
    } catch (caught) {
      setErreur(message(caught, t("echec")));
    } finally {
      setOccupe(false);
    }
  }

  return (
    <>
      <p className="text-[13px] leading-relaxed text-muted sm:text-sm">
        {t("restants")}{" "}
        <strong className={etat.codes_restants <= 2 ? "text-danger" : "text-ink"}>
          {etat.codes_restants}
        </strong>
        {etat.codes_restants <= 2 && ` — ${t("regenerer")}`}
      </p>

      {geste === "aucun" ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <GhostButton type="button" onClick={() => ouvrir("codes")}>
            {t("nouveauxCodes")}
          </GhostButton>
          <GhostButton type="button" onClick={() => ouvrir("desactiver")} className="text-danger">
            {t("desactiver")}
          </GhostButton>
        </div>
      ) : (
        <form onSubmit={valider} className="mt-4 grid gap-3 rounded-xl border border-line bg-surface-muted p-3 sm:p-4">
          <p className="text-[13px] font-medium text-ink sm:text-sm">
            {geste === "codes" ? t("avertissementCodes") : t("avertissementDesactiver")}
          </p>
          <div className={`grid gap-3 ${geste === "desactiver" ? "sm:grid-cols-2" : ""}`}>
            {geste === "desactiver" && (
              <Field label={t("codeApplication")}>
                <input
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  required
                  maxLength={20}
                  className={codeClass}
                />
              </Field>
            )}
            <PasswordField
              label={t("motDePasse")}
              value={motDePasse}
              onChange={setMotDePasse}
              autoComplete="current-password"
              inputClassName={inputClass}
            />
          </div>
          {erreur && <p className="text-sm font-medium text-danger">{erreur}</p>}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" pending={occupe}>
              {geste === "codes" ? t("generer") : t("desactiver")}
            </Button>
            <GhostButton type="button" onClick={() => ouvrir("aucun")}>
              {t("annuler")}
            </GhostButton>
          </div>
        </form>
      )}
    </>
  );
}

function CodesDeSecours({ codes, onFini }: { codes: string[]; onFini: () => void }) {
  const t = useTranslations("pro.securite.codes");
  const toast = useToast();
  const [range, setRange] = useState(false);
  const texte = codes.join("\n");

  function telecharger() {
    const lien = document.createElement("a");
    lien.href = URL.createObjectURL(new Blob([`${t("fichierTitre")}\n\n${texte}\n`], { type: "text/plain" }));
    lien.download = t("fichierNom");
    lien.click();
    URL.revokeObjectURL(lien.href);
  }

  return (
    <Card>
      <Titre icone="lock" badge={<Badge tone="success">{t("activee")}</Badge>}>
        {t("titre")}
      </Titre>
      <p className="text-[13px] leading-relaxed text-muted sm:text-sm">
        {t.rich("intro", { gras: (texte) => <strong>{texte}</strong> })}
      </p>
      <ul className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {codes.map((valeur) => (
          <li
            key={valeur}
            className="rounded-lg border border-line bg-surface-muted px-2 py-2 text-center font-mono text-sm tracking-wider text-ink"
          >
            {valeur}
          </li>
        ))}
      </ul>
      <div className="mt-4 flex flex-wrap gap-2">
        <GhostButton
          type="button"
          icon={<Icon name="copy" className="size-4" />}
          onClick={() => {
            navigator.clipboard
              ?.writeText(texte)
              .then(() => toast.success(t("copies")))
              .catch(() => toast.error(t("copieImpossible")));
          }}
        >
          {t("copier")}
        </GhostButton>
        <GhostButton type="button" onClick={telecharger}>
          {t("telecharger")}
        </GhostButton>
      </div>
      <label className="mt-4 flex items-start gap-2 text-sm text-ink">
        <input
          type="checkbox"
          checked={range}
          onChange={(event) => setRange(event.target.checked)}
          className="mt-0.5 size-4 accent-[var(--salon-primary)]"
        />
        {t("ranges")}
      </label>
      <Button type="button" disabled={!range} onClick={onFini} className="mt-3">
        {t("terminer")}
      </Button>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Mot de passe et sessions
// ---------------------------------------------------------------------------

function MotDePasse() {
  const t = useTranslations("pro.securite.motDePasse");
  const toast = useToast();
  const [actuel, setActuel] = useState("");
  const [nouveau, setNouveau] = useState("");
  const [occupe, setOccupe] = useState(false);
  const [erreur, setErreur] = useState("");

  async function changer(event: FormEvent) {
    event.preventDefault();
    setOccupe(true);
    setErreur("");
    try {
      await dashboardFetch("/api/v1/auth/password/change", {
        method: "POST",
        body: JSON.stringify({ current_password: actuel, new_password: nouveau }),
      });
      toast.success(t("ok"));
      setActuel("");
      setNouveau("");
    } catch (caught) {
      setErreur(message(caught, t("echec")));
    } finally {
      setOccupe(false);
    }
  }

  return (
    <Card>
      <Titre icone="edit">{t("titre")}</Titre>
      <form onSubmit={changer} className="grid gap-3">
        <PasswordField
          label={t("actuel")}
          value={actuel}
          onChange={setActuel}
          autoComplete="current-password"
          inputClassName={inputClass}
        />
        <PasswordField
          label={t("nouveau")}
          value={nouveau}
          onChange={setNouveau}
          autoComplete="new-password"
          inputClassName={inputClass}
        />
        <p className="text-xs leading-relaxed text-subtle">
          {t("regle")}
        </p>
        {erreur && <p className="text-sm font-medium text-danger">{erreur}</p>}
        <Button type="submit" pending={occupe} disabled={!actuel || nouveau.length < 10} className="w-full sm:w-auto">
          {t("changer")}
        </Button>
      </form>
    </Card>
  );
}

function Sessions() {
  const t = useTranslations("pro.securite.sessions");
  const toast = useToast();
  const [confirmer, setConfirmer] = useState(false);
  const [occupe, setOccupe] = useState(false);

  // Téléphone perdu, ordinateur partagé : fermer toutes les autres sessions
  // sans changer de mot de passe (audit du 16/10/2026, C-10).
  async function fermerLesAutres() {
    setOccupe(true);
    const ok = await toast.run(
      () => dashboardFetch("/api/v1/auth/sessions/autres", { method: "POST" }),
      { success: t("fermees") },
    );
    setOccupe(false);
    if (ok) setConfirmer(false);
  }

  return (
    <Card>
      <Titre icone="clock">{t("titre")}</Titre>
      <ul className="grid gap-2 text-[13px] leading-relaxed text-muted sm:text-sm">
        <li>{t.rich("duree", { gras: (texte) => <strong className="text-ink">{texte}</strong> })}</li>
        <li>{t("motDePasse")}</li>
        <li>{t("journal")}</li>
      </ul>
      <div className="mt-4 border-t border-line pt-4">
        <p className="text-[13px] leading-relaxed text-muted sm:text-sm">{t("fermerAide")}</p>
        {confirmer ? (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:flex">
            <Button type="button" pending={occupe} onClick={() => void fermerLesAutres()}>
              {t("confirmer")}
            </Button>
            <GhostButton type="button" onClick={() => setConfirmer(false)} disabled={occupe}>
              {t("annuler")}
            </GhostButton>
          </div>
        ) : (
          <GhostButton type="button" onClick={() => setConfirmer(true)} className="mt-3 w-full sm:w-auto">
            {t("fermer")}
          </GhostButton>
        )}
      </div>
    </Card>
  );
}
