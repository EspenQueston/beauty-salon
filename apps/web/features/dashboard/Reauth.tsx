"use client";

/**
 * Confirmer son identité avant un geste sensible.
 *
 * Le serveur refuse certaines écritures (« reauth_requise ») sans preuve
 * d'identité de moins de dix minutes : changer le numéro où les clientes
 * envoient leurs acomptes, par exemple. Une session volée ne suffit plus à
 * détourner l'argent en silence (audit du 16/10/2026, C-04).
 *
 * `useReauth()` rend `avecReauth(action)` : l'action est tentée ; si le
 * serveur demande une confirmation, la fenêtre s'ouvre (mot de passe, ou
 * code de double authentification), puis l'action est rejouée une fois.
 * Annuler la fenêtre fait échouer l'action, sans rien modifier.
 */

import { useTranslations } from "next-intl";
import { useCallback, useRef, useState, type ReactNode } from "react";

import { DashboardError, dashboardFetch } from "@/lib/dashboard";
import { Button, GhostButton, inputClass } from "@/features/ui";
import { Modal } from "@/features/ui/Modal";
import { PasswordField } from "@/features/ui/PasswordField";

type Attente = { resoudre: (ok: boolean) => void };

export function useReauth(): {
  avecReauth: <T>(action: () => Promise<T>) => Promise<T>;
  fenetre: ReactNode;
} {
  const [ouverte, setOuverte] = useState(false);
  const attente = useRef<Attente | null>(null);

  const demander = useCallback(
    () =>
      new Promise<boolean>((resoudre) => {
        attente.current = { resoudre };
        setOuverte(true);
      }),
    [],
  );

  const fermer = useCallback((ok: boolean) => {
    setOuverte(false);
    attente.current?.resoudre(ok);
    attente.current = null;
  }, []);

  const avecReauth = useCallback(
    async <T,>(action: () => Promise<T>): Promise<T> => {
      try {
        return await action();
      } catch (erreur) {
        if (!(erreur instanceof DashboardError) || erreur.code !== "reauth_requise") throw erreur;
        if (!(await demander())) throw erreur;
        return action();
      }
    },
    [demander],
  );

  return {
    avecReauth,
    fenetre: ouverte ? <FenetreReauth onFin={fermer} /> : null,
  };
}

function FenetreReauth({ onFin }: { onFin: (ok: boolean) => void }) {
  const t = useTranslations("pro.reauth");
  const [motDePasse, setMotDePasse] = useState("");
  const [code, setCode] = useState("");
  const [parCode, setParCode] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  async function confirmer(event?: React.FormEvent) {
    event?.preventDefault();
    setEnvoi(true);
    setErreur(null);
    try {
      await dashboardFetch("/api/v1/auth/reauth", {
        method: "POST",
        body: JSON.stringify(parCode ? { code } : { password: motDePasse }),
      });
      onFin(true);
    } catch (e) {
      setErreur(e instanceof Error && e.message ? e.message : t("erreur"));
    } finally {
      setEnvoi(false);
    }
  }

  const pret = parCode ? code.trim().length >= 6 : motDePasse.length > 0;

  return (
    <Modal
      titre={t("titre")}
      sousTitre={t("pourquoi")}
      onFermer={() => onFin(false)}
      occupe={envoi}
      largeur="max-w-md"
      pied={
        <div className="flex flex-wrap justify-end gap-2">
          <GhostButton type="button" onClick={() => onFin(false)} disabled={envoi}>
            {t("annuler")}
          </GhostButton>
          <Button type="submit" form="reauth" pending={envoi} disabled={!pret}>
            {t("confirmer")}
          </Button>
        </div>
      }
    >
      <form id="reauth" onSubmit={confirmer} className="space-y-3">
        {parCode ? (
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-ink">{t("code")}</span>
            <input
              value={code}
              onChange={(event) => setCode(event.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              className={inputClass}
            />
          </label>
        ) : (
          <PasswordField
            label={t("motDePasse")}
            value={motDePasse}
            onChange={setMotDePasse}
            autoComplete="current-password"
            autoFocus
            inputClassName={inputClass}
          />
        )}
        <button
          type="button"
          onClick={() => {
            setParCode((v) => !v);
            setErreur(null);
          }}
          className="text-xs font-medium text-muted underline-offset-2 hover:text-ink hover:underline"
        >
          {parCode ? t("parMotDePasse") : t("parCode")}
        </button>
        {erreur && (
          <p role="alert" className="text-sm text-danger">
            {erreur}
          </p>
        )}
      </form>
    </Modal>
  );
}
