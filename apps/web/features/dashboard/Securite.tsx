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
  const { membership, reload: rechargerSession } = useDashboard();
  const { data, error, reload } = useResource<EtatMfa>("/api/v1/auth/mfa", membership.tenant.id);

  return (
    <>
      <PageHeader
        title="Sécurité"
        description="Protégez l'accès à votre salon : double authentification, mot de passe et sessions."
      />
      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] lg:gap-6">
        <div className="min-w-0">
          {error ? (
            <ErrorState>Impossible de lire l&apos;état de la double authentification.</ErrorState>
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
          etat.enabled ? <Badge tone="success">Activée</Badge> : <Badge tone="warning">Désactivée</Badge>
        }
      >
        Double authentification
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
      setErreur(message(caught, "Préparation impossible. Réessayez."));
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
      toast.success("Double authentification activée.");
      onCodes(resultat.codes);
    } catch (caught) {
      setErreur(message(caught, "Activation impossible. Réessayez."));
    } finally {
      setOccupe(false);
    }
  }

  if (!cle) {
    return (
      <>
        <p className="text-[13px] leading-relaxed text-muted sm:text-sm">
          Un mot de passe peut fuiter, se deviner ou se voler. Avec la double authentification,
          chaque connexion demande aussi un code à six chiffres affiché par une application sur
          votre téléphone : sans lui, votre mot de passe seul n&apos;ouvre rien.
        </p>
        <ul className="mt-3 grid gap-1.5 text-[13px] text-muted sm:grid-cols-2 sm:text-sm">
          {["Google Authenticator", "Microsoft Authenticator", "1Password, Bitwarden…", "Gratuit, sans SMS"].map(
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
          Activer la double authentification
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
            alt="QR code à scanner avec votre application d'authentification"
            className="size-40"
          />
        </div>
        <div className="min-w-0 text-[13px] leading-relaxed text-muted sm:text-sm">
          <p>
            <strong className="text-ink">1.</strong> Dans votre application, ajoutez un compte et
            scannez ce QR code.
          </p>
          <p className="mt-2">Pas d&apos;appareil photo ? Saisissez cette clé :</p>
          <code className="mt-1 block break-all rounded-lg bg-surface-muted px-2.5 py-1.5 font-mono text-xs text-ink">
            {cle.secret}
          </code>
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="2. Code affiché par l'application">
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
          label="3. Votre mot de passe"
          value={motDePasse}
          onChange={setMotDePasse}
          autoComplete="current-password"
          inputClassName={inputClass}
        />
      </div>
      {erreur && <p className="text-sm font-medium text-danger">{erreur}</p>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" pending={occupe}>
          Confirmer et activer
        </Button>
        <GhostButton type="button" onClick={() => setCle(null)}>
          Annuler
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
        toast.success("Double authentification désactivée.");
        onChange();
      }
      ouvrir("aucun");
    } catch (caught) {
      setErreur(message(caught, "Opération impossible. Réessayez."));
    } finally {
      setOccupe(false);
    }
  }

  return (
    <>
      <p className="text-[13px] leading-relaxed text-muted sm:text-sm">
        Chaque connexion demande le code de votre application. Codes de secours restants :{" "}
        <strong className={etat.codes_restants <= 2 ? "text-danger" : "text-ink"}>
          {etat.codes_restants}
        </strong>
        {etat.codes_restants <= 2 && " — régénérez-les sans attendre."}
      </p>

      {geste === "aucun" ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <GhostButton type="button" onClick={() => ouvrir("codes")}>
            Nouveaux codes de secours
          </GhostButton>
          <GhostButton type="button" onClick={() => ouvrir("desactiver")} className="text-danger">
            Désactiver
          </GhostButton>
        </div>
      ) : (
        <form onSubmit={valider} className="mt-4 grid gap-3 rounded-xl border border-line bg-surface-muted p-3 sm:p-4">
          <p className="text-[13px] font-medium text-ink sm:text-sm">
            {geste === "codes"
              ? "Les codes actuels cesseront de fonctionner."
              : "Votre mot de passe suffira de nouveau pour vous connecter."}
          </p>
          <div className={`grid gap-3 ${geste === "desactiver" ? "sm:grid-cols-2" : ""}`}>
            {geste === "desactiver" && (
              <Field label="Code de l'application">
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
              label="Mot de passe"
              value={motDePasse}
              onChange={setMotDePasse}
              autoComplete="current-password"
              inputClassName={inputClass}
            />
          </div>
          {erreur && <p className="text-sm font-medium text-danger">{erreur}</p>}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" pending={occupe}>
              {geste === "codes" ? "Générer de nouveaux codes" : "Désactiver"}
            </Button>
            <GhostButton type="button" onClick={() => ouvrir("aucun")}>
              Annuler
            </GhostButton>
          </div>
        </form>
      )}
    </>
  );
}

function CodesDeSecours({ codes, onFini }: { codes: string[]; onFini: () => void }) {
  const toast = useToast();
  const [range, setRange] = useState(false);
  const texte = codes.join("\n");

  function telecharger() {
    const lien = document.createElement("a");
    lien.href = URL.createObjectURL(new Blob([`Codes de secours Beauty Salon\n\n${texte}\n`], { type: "text/plain" }));
    lien.download = "codes-de-secours-beauty-salon.txt";
    lien.click();
    URL.revokeObjectURL(lien.href);
  }

  return (
    <Card>
      <Titre icone="lock" badge={<Badge tone="success">Activée</Badge>}>
        Vos codes de secours
      </Titre>
      <p className="text-[13px] leading-relaxed text-muted sm:text-sm">
        Si vous perdez votre téléphone, chacun de ces codes ouvre <strong>une</strong> connexion.
        Ils ne seront plus jamais affichés : rangez-les maintenant, hors de ce téléphone.
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
              .then(() => toast.success("Codes copiés."))
              .catch(() => toast.error("Copie impossible : recopiez-les à la main."));
          }}
        >
          Copier
        </GhostButton>
        <GhostButton type="button" onClick={telecharger}>
          Télécharger (.txt)
        </GhostButton>
      </div>
      <label className="mt-4 flex items-start gap-2 text-sm text-ink">
        <input
          type="checkbox"
          checked={range}
          onChange={(event) => setRange(event.target.checked)}
          className="mt-0.5 size-4 accent-[var(--salon-primary)]"
        />
        J&apos;ai rangé mes codes en lieu sûr.
      </label>
      <Button type="button" disabled={!range} onClick={onFini} className="mt-3">
        Terminer
      </Button>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Mot de passe et sessions
// ---------------------------------------------------------------------------

function MotDePasse() {
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
      toast.success("Mot de passe changé. Vos autres appareils ont été déconnectés.");
      setActuel("");
      setNouveau("");
    } catch (caught) {
      setErreur(message(caught, "Changement impossible. Réessayez."));
    } finally {
      setOccupe(false);
    }
  }

  return (
    <Card>
      <Titre icone="edit">Mot de passe</Titre>
      <form onSubmit={changer} className="grid gap-3">
        <PasswordField
          label="Mot de passe actuel"
          value={actuel}
          onChange={setActuel}
          autoComplete="current-password"
          inputClassName={inputClass}
        />
        <PasswordField
          label="Nouveau mot de passe"
          value={nouveau}
          onChange={setNouveau}
          autoComplete="new-password"
          inputClassName={inputClass}
        />
        <p className="text-xs leading-relaxed text-subtle">
          10 caractères au moins. Les mots de passe courants ou déjà publiés dans une fuite de
          données sont refusés.
        </p>
        {erreur && <p className="text-sm font-medium text-danger">{erreur}</p>}
        <Button type="submit" pending={occupe} disabled={!actuel || nouveau.length < 10} className="w-full sm:w-auto">
          Changer le mot de passe
        </Button>
      </form>
    </Card>
  );
}

function Sessions() {
  return (
    <Card>
      <Titre icone="clock">Sessions</Titre>
      <ul className="grid gap-2 text-[13px] leading-relaxed text-muted sm:text-sm">
        <li>
          Une session se ferme d&apos;elle-même après <strong className="text-ink">3 jours</strong>{" "}
          sans activité, et au plus tard après 14 jours.
        </li>
        <li>Changer votre mot de passe déconnecte tous vos autres appareils.</li>
        <li>Chaque connexion et chaque changement sensible sont consignés par l&apos;équipe Beauty Salon.</li>
      </ul>
    </Card>
  );
}
