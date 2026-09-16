"use client";

/**
 * Messages de réussite et d'échec.
 *
 * Un seul endroit pour tous les retours de l'application. Deux règles :
 *
 * - **une action, un message.** Enregistrer, supprimer, envoyer : chacune
 *   dit ce qui s'est passé. Un écran qui ne répond rien laisse croire que
 *   le clic n'a pas été pris.
 * - **un échec explique.** Le message reprend la raison renvoyée par l'API
 *   plutôt qu'un « une erreur est survenue » qui n'aide personne.
 *
 * Les messages d'erreur restent affichés jusqu'à fermeture : on n'a pas le
 * droit de faire disparaître une mauvaise nouvelle avant qu'elle soit lue.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

type Tone = "success" | "error" | "info";

interface Toast {
  id: number;
  tone: Tone;
  message: string;
}

interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
  /** Exécute une action, annonce le résultat, et renvoie si elle a réussi. */
  run: (
    action: () => Promise<unknown>,
    messages: { success: string; error?: string },
  ) => Promise<boolean>;
}

const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast doit être utilisé dans ToastProvider.");
  return api;
}

const AUTO_DISMISS = 4500;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (tone: Tone, message: string) => {
      const id = (counter.current += 1);
      setToasts((current) => [...current.slice(-3), { id, tone, message }]);

      // Les erreurs attendent une fermeture explicite.
      if (tone !== "error") {
        setTimeout(() => dismiss(id), AUTO_DISMISS);
      }
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(
    () => ({
      success: (message) => push("success", message),
      error: (message) => push("error", message),
      info: (message) => push("info", message),
      run: async (action, messages) => {
        try {
          await action();
          push("success", messages.success);
          return true;
        } catch (caught) {
          const detail =
            caught instanceof Error && caught.message ? caught.message : null;
          push("error", messages.error ?? detail ?? "L'action a échoué.");
          return false;
        }
      },
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4 sm:inset-x-auto sm:right-0 sm:items-end"
      >
        {toasts.map((toast) => (
          <ToastCard key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

const TONES: Record<Tone, { bg: string; fg: string; icon: ReactNode }> = {
  success: {
    bg: "bg-success-bg",
    fg: "text-success",
    icon: (
      <path d="M20 6 9 17l-5-5" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    ),
  },
  error: {
    bg: "bg-danger-bg",
    fg: "text-danger",
    icon: (
      <>
        <circle cx="12" cy="12" r="9" strokeWidth="2" />
        <path d="M12 7v6M12 16.5v.01" strokeWidth="2.5" strokeLinecap="round" />
      </>
    ),
  },
  info: {
    bg: "bg-info-bg",
    fg: "text-info",
    icon: (
      <>
        <circle cx="12" cy="12" r="9" strokeWidth="2" />
        <path d="M12 11v6M12 7.5v.01" strokeWidth="2.5" strokeLinecap="round" />
      </>
    ),
  },
};

function ToastCard({
  toast,
  onDismiss,
}: {
  toast: Toast;
  onDismiss: (id: number) => void;
}) {
  const tone = TONES[toast.tone];

  return (
    <div
      role={toast.tone === "error" ? "alert" : "status"}
      className="animate-toast-in pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-xl border border-line bg-surface p-3.5 shadow-float"
    >
      <span
        aria-hidden
        className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full ${tone.bg} ${tone.fg}`}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className="size-4">
          {tone.icon}
        </svg>
      </span>

      <p className="flex-1 text-sm leading-snug text-ink">{toast.message}</p>

      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Fermer"
        className="-m-1 rounded-md p-1 text-subtle transition hover:bg-surface-hover hover:text-ink"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className="size-4">
          <path d="m6 6 12 12M18 6 6 18" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
    </div>
  );
}
