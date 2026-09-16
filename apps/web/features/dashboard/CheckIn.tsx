"use client";

/**
 * Enregistrer une arrivée : le scanner du salon.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi cet écran existe
 * ---------------------------------------------------------------------------
 *
 * La cliente porte un QR depuis des mois — dans son espace, dans l'e-mail de
 * confirmation, sur la page de suivi de son rendez-vous. Le salon, lui,
 * n'avait aucun endroit pour le lire. Le code était donc un décor : il
 * promettait un geste que personne ne pouvait faire.
 *
 * ---------------------------------------------------------------------------
 * Deux chemins, pas un
 * ---------------------------------------------------------------------------
 *
 * L'appareil photo manque les jours où il faudrait qu'il marche. Permission
 * refusée la première fois et jamais redemandée ; objectif rayé ; poste fixe
 * à l'accueil sans caméra ; page ouverte en HTTP sur le réseau du salon, où
 * `getUserMedia` refuse de s'exécuter hors contexte sécurisé.
 *
 * La saisie du code à six caractères n'est donc pas un repli honteux caché
 * derrière un lien : c'est le second onglet, à égalité, et c'est vers lui
 * qu'on bascule automatiquement quand la caméra échoue — avec la raison
 * écrite, parce qu'une caméra noire sans explication fait redémarrer le
 * téléphone.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi pas simplement le bouton de l'agenda
 * ---------------------------------------------------------------------------
 *
 * Il existe, et il reste. Mais il se clique de mémoire : à midi, avec quatre
 * clientes dans le salon, on note « arrivée » sur la mauvaise ligne et
 * l'agenda ment jusqu'au soir. Le code est porté par la cliente elle-même —
 * il désigne *son* rendez-vous, pas celui qu'on croit.
 *
 * ---------------------------------------------------------------------------
 * Le décodage
 * ---------------------------------------------------------------------------
 *
 * `BarcodeDetector` quand le navigateur l'a — c'est le décodeur du système,
 * gratuit en poids et bien plus rapide. Sinon `jsQR`, chargé seulement à
 * l'ouverture de cet écran : l'agenda et la fiche d'une cliente n'ont pas à
 * payer 40 ko pour un lecteur qu'elles n'ouvriront jamais.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { DashboardError, dashboardFetch } from "@/lib/dashboard";
import { Button, GhostButton, inputClass } from "@/features/ui";
import { Icon } from "./icons";

/* --------------------------------------------------------------------------
 * Ce que le serveur renvoie
 * ---------------------------------------------------------------------- */

interface CheckedBooking {
  id: string;
  status: string;
  starts_at: string;
  service_name: string;
  customer_name: string;
  customer_phone: string;
  staff_member_name: string;
}

interface Outcome {
  tone: "success" | "warning" | "error";
  title: string;
  detail: string;
  booking?: CheckedBooking;
}

/**
 * Le rendez-vous visé, quand le scanner est ouvert depuis une ligne de
 * l'agenda plutôt que depuis le bouton général.
 *
 * Sa présence change deux choses. L'écran nomme la cliente attendue — on sait
 * qui l'on scanne avant de scanner. Et le serveur refuse tout code qui en
 * désigne un autre : scanner le QR de la voisine pendant qu'on est sur la
 * ligne d'Espoir est exactement l'erreur que le QR existe pour empêcher.
 */
export interface CheckInTarget {
  id: string;
  customer_name: string;
  service_name: string;
  starts_at: string;
}

/** Un code d'arrivée fait six caractères de cet alphabet, et rien d'autre. */
const ALPHABET = "ACDEFHJKMNPRTVWXY347";
const CODE_LENGTH = 6;

/* --------------------------------------------------------------------------
 * Le décodeur
 * ---------------------------------------------------------------------- */

/**
 * `BarcodeDetector` n'est pas dans les types du DOM : il n'existe que sur
 * Chrome et les navigateurs Android. On le déclare au minimum de ce qu'on en
 * utilise plutôt que d'élargir l'interface globale — ce lecteur est le seul
 * endroit du produit qui s'en sert.
 */
interface NativeDetector {
  detect: (source: CanvasImageSource) => Promise<{ rawValue: string }[]>;
}

type Decoder = (
  canvas: HTMLCanvasElement,
  context: CanvasRenderingContext2D,
) => Promise<string | null>;

/**
 * `patient` : accepte de chercher plus longtemps.
 *
 * Le flux vidéo décode soixante fois par minute et n'a pas besoin d'insister
 * sur une image donnée — la suivante arrive dans 140 ms. Une photo importée,
 * elle, n'a pas de suivante : c'est celle-là qu'il faut lire, quitte à
 * essayer aussi la vidéo inversée d'un écran photographié de travers.
 */
async function buildDecoder(patient = false): Promise<Decoder> {
  const globals = globalThis as unknown as {
    BarcodeDetector?: new (options: { formats: string[] }) => NativeDetector;
  };

  if (globals.BarcodeDetector) {
    const detector = new globals.BarcodeDetector({ formats: ["qr_code"] });
    return async (canvas) => {
      const found = await detector.detect(canvas);
      return found[0]?.rawValue ?? null;
    };
  }

  // Import dynamique : le lecteur ne pèse sur le paquet que si on l'ouvre.
  const { default: jsQR } = await import("jsqr");
  return async (canvas, context) => {
    const frame = context.getImageData(0, 0, canvas.width, canvas.height);
    const found = jsQR(frame.data, frame.width, frame.height, {
      inversionAttempts: patient ? "attemptBoth" : "dontInvert",
    });
    return found?.data ?? null;
  };
}

/* --------------------------------------------------------------------------
 * Lire un QR dans une image déjà enregistrée
 * ---------------------------------------------------------------------- */

/**
 * Charge un fichier image en élément `<img>`.
 *
 * Par `<img>` et non `createImageBitmap` : le premier marche jusque sur les
 * vieilles vues web Android qu'on trouve encore sur les téléphones d'entrée
 * de gamme visés, le second non. La différence de vitesse est sans objet —
 * on décode une image, pas un flux.
 */
function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("unreadable"));
    };
    image.src = url;
  });
}

/**
 * Cherche un QR dans une image, à deux résolutions.
 *
 * Une photo de téléphone moderne fait douze millions de pixels ; la passer
 * telle quelle à un décodeur logiciel prend plusieurs secondes sur un
 * appareil modeste, pour aucun gain — un QR se lit très bien à 1600 points.
 *
 * Et quand la première passe échoue, on réessaie à 800 : réduire moyenne le
 * bruit d'une photo prise de près, sous néon, sur un écran qui scintille.
 * C'est exactement le cas où la caméra directe avait déjà renoncé.
 */
async function decodeImageFile(file: File): Promise<string | null> {
  const image = await loadImage(file);
  const decoder = await buildDecoder(true);

  const surface = document.createElement("canvas");
  const context = surface.getContext("2d", { willReadFrequently: true });
  if (!context) return null;

  for (const cap of [1600, 800]) {
    const scale = Math.min(1, cap / Math.max(image.width, image.height));
    surface.width = Math.max(1, Math.round(image.width * scale));
    surface.height = Math.max(1, Math.round(image.height * scale));
    context.drawImage(image, 0, 0, surface.width, surface.height);

    const value = await decoder(surface, context).catch(() => null);
    if (value) return value;
  }
  return null;
}

/* --------------------------------------------------------------------------
 * Le bouton et son tiroir
 * ---------------------------------------------------------------------- */

export function CheckInButton({
  tenantId,
  onCheckedIn,
}: {
  tenantId: string;
  /** L'agenda derrière se recharge : la ligne doit changer d'état sous les
   *  yeux, sinon on scanne une seconde fois pour vérifier. */
  onCheckedIn: () => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        type="button"
        onClick={() => setOpen(true)}
        icon={<Icon name="scan" className="size-4" />}
      >
        Arrivée
      </Button>

      {open && (
        <CheckInPanel
          tenantId={tenantId}
          onCheckedIn={onCheckedIn}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

export function CheckInPanel({
  tenantId,
  target,
  onCheckedIn,
  onSkip,
  onClose,
}: {
  tenantId: string;
  target?: CheckInTarget;
  onCheckedIn: () => void;
  /**
   * Noter l'arrivée sans code.
   *
   * Indispensable, et pas une commodité : toutes les clientes n'ont pas de
   * téléphone qui affiche un QR, et une cliente sans code doit pouvoir être
   * reçue. Sans cette porte, le scanner deviendrait une condition d'accès au
   * salon.
   *
   * Elle reste volontairement discrète et placée en bas : c'est le chemin
   * qu'on prend quand les deux autres ont échoué, pas celui qu'on prend par
   * habitude — sinon on retombe sur le clic de mémoire, et l'agenda se
   * remet à mentir.
   */
  onSkip?: () => void;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<"scan" | "image" | "code">("scan");
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [sending, setSending] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  /**
   * L'envoi, commun aux deux chemins.
   *
   * Un seul point d'entrée parce que les deux doivent aboutir au même
   * endroit : mêmes contrôles côté serveur, même trace dans le journal. Un
   * chemin de saisie plus permissif que l'autre serait une porte dérobée.
   */
  // L'identifiant est extrait avant le rappel plutôt que lu dedans : le
  // compilateur React n'accepte une dépendance mémorisée que si elle est la
  // valeur elle-même, pas une propriété lue à l'intérieur.
  const targetId = target?.id;

  const submit = useCallback(
    async (payload: { token?: string; code?: string }) => {
      setSending(true);
      try {
        const data = await dashboardFetch<{
          detail: string;
          code?: string;
          booking: CheckedBooking;
        }>(
          "/api/v1/bookings/check-in/",
          {
            method: "POST",
            // Le rendez-vous visé voyage avec le code : c'est le serveur qui
            // refuse un code qui en désigne un autre, pas la page. Une
            // comparaison faite ici se contournerait en rejouant la requête.
            body: JSON.stringify({ ...payload, booking: targetId }),
          },
          tenantId,
        );

        const already = data.code === "already_checked_in";
        setOutcome({
          tone: already ? "warning" : "success",
          title: already ? "Déjà notée arrivée" : "Arrivée enregistrée",
          detail: data.detail,
          booking: data.booking,
        });
        if (!already) onCheckedIn();
      } catch (error) {
        const failure = error as DashboardError;
        // Le refus transporte parfois le rendez-vous fautif : savoir
        // *lequel* est annulé, et pour qui, est ce qui permet de trancher au
        // comptoir plutôt que de relire tout l'agenda.
        const body = failure.body as { booking?: CheckedBooking } | undefined;
        setOutcome({
          tone: "error",
          title:
            failure.code === "already_checked_in"
              ? "Déjà notée arrivée"
              : "Impossible d'enregistrer",
          detail: failure.message,
          booking: body?.booking,
        });
      } finally {
        setSending(false);
      }
    },
    [tenantId, onCheckedIn, targetId],
  );

  /** La caméra a renoncé : on bascule sur la saisie, en disant pourquoi. */
  const onCameraFailure = useCallback((reason: string) => {
    setCameraError(reason);
    setMode("code");
  }, []);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Enregistrer une arrivée"
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6"
    >
      <button
        type="button"
        aria-label="Fermer"
        onClick={onClose}
        className="absolute inset-0 bg-black/55 backdrop-blur-[2px]"
      />

      {/*
        Plein écran par le bas sur téléphone, carte centrée au-delà. C'est
        l'écran qu'on ouvre debout, une cliente en face : la zone de visée
        doit prendre la largeur, et le bouton de fermeture tomber sous le
        pouce plutôt que dans un coin.
      */}
      <div className="relative flex max-h-[92dvh] w-full flex-col overflow-hidden rounded-t-3xl border border-line bg-surface shadow-float sm:max-w-lg sm:rounded-3xl">
        <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3.5 sm:px-5">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold tracking-tight text-ink sm:text-lg">
              {/* Ouvert depuis une ligne, l'écran dit qui l'on attend. Sans ce
                  nom, on scanne à l'aveugle et le refus « ce code est celui de
                  quelqu'un d'autre » arrive sans qu'on sache qui était
                  attendu. */}
              {target ? `Arrivée de ${target.customer_name}` : "Enregistrer une arrivée"}
            </h2>
            <p className="mt-0.5 truncate text-xs text-muted">
              {target
                ? `${target.service_name} · ${new Intl.DateTimeFormat("fr-FR", {
                    hour: "2-digit",
                    minute: "2-digit",
                  }).format(new Date(target.starts_at))}`
                : "Scannez le QR de la cliente, ou saisissez son code."}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fermer"
            className="-mr-1.5 shrink-0 rounded-lg p-1.5 text-muted transition hover:bg-surface-hover hover:text-ink"
          >
            <Icon name="close" className="size-5" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-4 sm:px-5">
          {outcome ? (
            <Result
              outcome={outcome}
              onAgain={() => {
                setOutcome(null);
                setCameraError(null);
              }}
              onClose={onClose}
            />
          ) : (
            <>
              {/*
                Trois chemins vers le même geste, et aucun n'est un
                sous-produit des autres : la caméra quand la cliente est là
                avec son téléphone allumé, l'image quand elle a envoyé une
                capture par WhatsApp ou que la caméra refuse, le code quand
                il ne reste que la voix.

                Libellés courts — « Caméra », pas « Scanner le QR code » :
                trois onglets doivent tenir sur 320 points sans se couper.
              */}
              <div className="mb-4 flex rounded-xl border border-line bg-surface-muted p-1">
                {(
                  [
                    ["scan", "Caméra", "scan"],
                    ["image", "Image", "image"],
                    ["code", "Code", "edit"],
                  ] as const
                ).map(([value, label, icon]) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={mode === value}
                    onClick={() => setMode(value)}
                    className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-sm transition sm:px-3 ${
                      mode === value
                        ? "salon-gradient font-medium text-white shadow-sm"
                        : "text-muted hover:text-ink"
                    }`}
                  >
                    <Icon name={icon} className="size-4 shrink-0" />
                    {label}
                  </button>
                ))}
              </div>

              {mode === "scan" && (
                <Scanner
                  paused={sending}
                  onFound={(token) => void submit({ token })}
                  onFailure={onCameraFailure}
                />
              )}

              {mode === "image" && (
                <ImagePicker
                  pending={sending}
                  onFound={(token) => void submit({ token })}
                  onTypeInstead={() => setMode("code")}
                />
              )}

              {mode === "code" && (
                <CodeForm
                  pending={sending}
                  cameraError={cameraError}
                  onSubmit={(code) => void submit({ code })}
                />
              )}

              {/*
                La porte de sortie.

                Toutes les clientes n'ont pas de téléphone qui affiche un QR,
                et une cliente sans code doit pouvoir être reçue — sinon le
                scanner devient une condition d'accès au salon. Elle est en
                bas, en petit, séparée par un filet : c'est le chemin qu'on
                prend quand les trois autres ont échoué, pas celui qu'on prend
                par habitude.
              */}
              {target && onSkip && (
                <div className="mt-5 border-t border-line pt-3.5 text-center">
                  <button
                    type="button"
                    onClick={onSkip}
                    className="text-xs text-muted underline underline-offset-2 transition hover:text-ink"
                  >
                    {target.customer_name} n&apos;a pas son code — noter
                    l&apos;arrivée quand même
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------
 * La visée
 * ---------------------------------------------------------------------- */

function Scanner({
  paused,
  onFound,
  onFailure,
}: {
  paused: boolean;
  onFound: (token: string) => void;
  onFailure: (reason: string) => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);

  /*
    Les rappels vivent dans une référence plutôt que dans les dépendances de
    l'effet.

    L'effet ouvre la caméra ; le relancer la ferme et la rouvre, ce qui fait
    clignoter l'image et redemande parfois la permission. Or `onFound` change
    d'identité à chaque rendu du parent. Sans cette indirection, la moindre
    frappe ailleurs dans le panneau redémarrerait le flux vidéo.
  */
  const handlers = useRef({ onFound, onFailure });
  useEffect(() => {
    handlers.current = { onFound, onFailure };
  });

  // `paused` traverse la même porte : la boucle de décodage doit le lire à
  // chaque image sans qu'un changement ne réinitialise la caméra.
  const halted = useRef(paused);
  useEffect(() => {
    halted.current = paused;
  });

  useEffect(() => {
    let stream: MediaStream | null = null;
    let frame = 0;
    let stopped = false;
    let decoder: Decoder | null = null;
    let last = 0;

    async function start() {
      /*
        `getUserMedia` n'existe pas hors contexte sécurisé. C'est le cas le
        plus fréquent en salon : la tablette ouvre `http://192.168.1.12:3100`
        sur le réseau local, et le navigateur refuse la caméra sans jamais
        afficher d'erreur visible. On le dit, plutôt que de montrer un
        rectangle noir.
      */
      if (!navigator.mediaDevices?.getUserMedia) {
        handlers.current.onFailure(
          window.isSecureContext
            ? "Cet appareil ne propose pas de caméra au navigateur."
            : "La caméra n'est accessible qu'en HTTPS. Sur une adresse en http://, le navigateur la refuse.",
        );
        return;
      }

      try {
        stream = await navigator.mediaDevices.getUserMedia({
          // Caméra arrière : c'est elle qu'on pointe vers le téléphone de la
          // cliente. `ideal` et non `exact` — sur un ordinateur portable il
          // n'y en a qu'une, et `exact` échouerait au lieu de la prendre.
          video: { facingMode: { ideal: "environment" } },
          audio: false,
        });
      } catch (error) {
        const denied =
          error instanceof DOMException &&
          (error.name === "NotAllowedError" || error.name === "SecurityError");
        handlers.current.onFailure(
          denied
            ? "L'accès à la caméra a été refusé. Autorisez-le dans les réglages du navigateur, ou saisissez le code."
            : "Aucune caméra disponible sur cet appareil.",
        );
        return;
      }

      if (stopped) {
        for (const track of stream.getTracks()) track.stop();
        return;
      }

      const element = video.current;
      if (!element) return;
      element.srcObject = stream;
      await element.play().catch(() => undefined);

      decoder = await buildDecoder();
      setReady(true);

      const surface = canvas.current;
      const context = surface?.getContext("2d", { willReadFrequently: true });
      if (!surface || !context) return;

      const tick = async (now: number) => {
        if (stopped) return;
        frame = requestAnimationFrame(tick);

        // Un décodage toutes les 140 ms, pas soixante par seconde : au-delà
        // on ne lit pas un QR plus vite, on vide la batterie et on fait
        // chauffer un téléphone d'entrée de gamme.
        if (halted.current || now - last < 140) return;
        last = now;

        if (element.readyState < element.HAVE_CURRENT_DATA) return;

        surface.width = element.videoWidth;
        surface.height = element.videoHeight;
        if (!surface.width || !surface.height) return;

        context.drawImage(element, 0, 0, surface.width, surface.height);
        const value = await decoder?.(surface, context).catch(() => null);
        if (value && !stopped) {
          halted.current = true;
          handlers.current.onFound(value);
        }
      };

      frame = requestAnimationFrame(tick);
    }

    void start();

    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      // Sans cet arrêt explicite, la petite lumière de la caméra reste
      // allumée après la fermeture du panneau — et c'est exactement le genre
      // de détail qui fait désinstaller une application.
      if (stream) for (const track of stream.getTracks()) track.stop();
    };
  }, []);

  return (
    <div>
      <div className="relative overflow-hidden rounded-2xl bg-black">
        <video
          ref={video}
          playsInline
          muted
          className="aspect-[4/3] w-full object-cover"
        />
        <canvas ref={canvas} className="hidden" />

        {/* La mire : quatre coins, pas un cadre plein. Un cadre continu se
            confond avec le bord du QR et on vise à côté. */}
        <div aria-hidden className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="relative size-[58%] max-w-[15rem]">
            {["left-0 top-0 border-l-2 border-t-2 rounded-tl-lg",
              "right-0 top-0 border-r-2 border-t-2 rounded-tr-lg",
              "left-0 bottom-0 border-b-2 border-l-2 rounded-bl-lg",
              "right-0 bottom-0 border-b-2 border-r-2 rounded-br-lg",
            ].map((corner) => (
              <span
                key={corner}
                className={`absolute size-8 border-white/90 ${corner}`}
              />
            ))}
          </div>
        </div>

        {!ready && (
          <p className="absolute inset-x-0 bottom-3 text-center text-xs text-white/80">
            Ouverture de la caméra…
          </p>
        )}
      </div>

      <p className="mt-3 text-center text-sm text-muted">
        Pointez l&apos;appareil vers le QR de la cliente. L&apos;arrivée
        s&apos;enregistre dès que le code est lu.
      </p>
    </div>
  );
}

/* --------------------------------------------------------------------------
 * L'image déjà enregistrée
 * ---------------------------------------------------------------------- */

/**
 * Importer un QR depuis un fichier.
 *
 * ---------------------------------------------------------------------------
 * Ce n'est pas un doublon de la caméra
 * ---------------------------------------------------------------------------
 *
 * La cliente envoie sa capture d'écran par WhatsApp la veille ; la gérante
 * la reçoit sur l'ordinateur de l'accueil, qui n'a pas de caméra. Ou bien
 * elle photographie l'écran de la cliente parce que la permission caméra a
 * été refusée une fois et que le navigateur ne la redemande plus. Ou encore
 * le QR arrive en pièce jointe d'un e-mail de confirmation transféré.
 *
 * Trois situations quotidiennes où le code existe, est valide, et où aucun
 * des deux autres chemins ne fonctionne.
 *
 * ---------------------------------------------------------------------------
 * Trois gestes pour un même dépôt
 * ---------------------------------------------------------------------------
 *
 * Le bouton sur téléphone — il ouvre la galerie ou l'appareil photo selon ce
 * que la personne choisit. Le glisser-déposer sur ordinateur, parce que le
 * fichier est déjà dans une fenêtre à côté. Et le collage, parce qu'une
 * capture reçue sur WhatsApp Web se copie d'un clic droit et se colle ici
 * sans jamais toucher au disque — c'est le geste le plus court des trois, et
 * celui qu'on n'offre presque jamais.
 */
function ImagePicker({
  pending,
  onFound,
  onTypeInstead,
}: {
  pending: boolean;
  onFound: (token: string) => void;
  onTypeInstead: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [reading, setReading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const handle = useCallback(
    async (file: File | null | undefined) => {
      if (!file) return;

      if (!file.type.startsWith("image/")) {
        setProblem("Ce fichier n'est pas une image.");
        return;
      }

      setProblem(null);
      setReading(true);
      try {
        const value = await decodeImageFile(file);
        if (value) onFound(value);
        else
          setProblem(
            "Aucun QR n'a été trouvé dans cette image. Essayez une capture plus nette, ou saisissez le code à six caractères.",
          );
      } catch {
        // Un HEIC d'iPhone, un fichier tronqué : le navigateur ne sait pas
        // le peindre, et il n'y a rien à décoder. Le dire vaut mieux que de
        // laisser tourner un sablier.
        setProblem(
          "Ce format d'image n'a pas pu être ouvert. Essayez une capture d'écran au format JPEG ou PNG.",
        );
      } finally {
        setReading(false);
      }
    },
    [onFound],
  );

  /*
    Le collage est écouté sur la fenêtre, pas sur une zone à cliquer d'abord.

    Coller impose déjà de viser le panneau du regard ; exiger en plus un clic
    préalable dans un rectangle, sans rien qui le dise, transforme un
    raccourci en devinette.
  */
  useEffect(() => {
    const onPaste = (event: ClipboardEvent) => {
      const item = [...(event.clipboardData?.items ?? [])].find((entry) =>
        entry.type.startsWith("image/"),
      );
      if (!item) return;
      event.preventDefault();
      void handle(item.getAsFile());
    };

    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [handle]);

  const busy = reading || pending;

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
          void handle(event.dataTransfer.files[0]);
        }}
        className={`rounded-2xl border-2 border-dashed px-4 py-8 text-center transition ${
          dragging
            ? "border-salon bg-salon-soft"
            : "border-line-strong bg-surface-muted"
        }`}
      >
        <span
          aria-hidden
          className="salon-gradient mx-auto flex size-12 items-center justify-center rounded-2xl text-white"
        >
          <Icon name="image" className="size-6" />
        </span>

        <p className="mt-3 text-sm font-medium text-ink">
          {busy ? "Lecture de l'image…" : "Déposez la capture du QR"}
        </p>
        <p className="mt-1 text-xs text-muted">
          {/* Le collage n'est mentionné qu'au-delà du téléphone : il n'y a
              pas de Ctrl+V sur un écran tactile, et promettre un geste
              impossible use la confiance dans tout le reste. */}
          <span className="hidden sm:inline">
            Glissez-la ici, collez-la avec Ctrl+V, ou{" "}
          </span>
          <span className="sm:hidden">Prenez une photo, ou </span>
          choisissez un fichier.
        </p>

        <input
          ref={input}
          type="file"
          accept="image/*"
          className="sr-only"
          onChange={(event) => {
            void handle(event.target.files?.[0]);
            // Le champ est vidé pour que redéposer *le même* fichier
            // redéclenche la lecture : sans cela, un second essai après un
            // échec ne produit aucun événement.
            event.target.value = "";
          }}
        />

        <GhostButton
          type="button"
          pending={busy}
          onClick={() => input.current?.click()}
          className="mt-4"
        >
          Choisir une image
        </GhostButton>
      </div>

      {problem && (
        <div className="mt-3 rounded-xl bg-warning-bg px-3 py-2.5">
          <p className="flex items-start gap-2 text-sm text-warning">
            <Icon name="clock" className="mt-0.5 size-4 shrink-0" />
            <span>{problem}</span>
          </p>
          <button
            type="button"
            onClick={onTypeInstead}
            className="mt-1.5 pl-6 text-xs font-medium text-warning underline underline-offset-2"
          >
            Saisir le code à la place
          </button>
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------------------
 * La saisie
 * ---------------------------------------------------------------------- */

function CodeForm({
  pending,
  cameraError,
  onSubmit,
}: {
  pending: boolean;
  cameraError: string | null;
  onSubmit: (code: string) => void;
}) {
  const [value, setValue] = useState("");

  /*
    Un seul champ, pas six cases.

    Six cases séparées se filment bien mais se collent mal : un code reçu par
    message ne s'y colle pas d'un geste, et un lecteur d'écran y annonce six
    champs sans nom. Le champ unique accepte le collage, la dictée vocale et
    le clavier physique du poste d'accueil.

    Les caractères hors alphabet sont écartés à la frappe plutôt que
    rattrapés : rien n'est deviné ici, parce que deviner un « O » en « Q »
    transformerait parfois une faute en code valide — celui d'une autre
    cliente.
  */
  const cleaned = value.toUpperCase().replace(/[^A-Z0-9]/g, "");
  const kept = [...cleaned].filter((char) => ALPHABET.includes(char)).join("");
  const rejected = [...cleaned].filter((char) => !ALPHABET.includes(char));
  const complete = kept.length === CODE_LENGTH;

  return (
    <div>
      {cameraError && (
        <p className="mb-4 flex items-start gap-2 rounded-xl bg-warning-bg px-3 py-2.5 text-sm text-warning">
          <Icon name="clock" className="mt-0.5 size-4 shrink-0" />
          <span>{cameraError}</span>
        </p>
      )}

      <label className="block">
        <span className="mb-1.5 block text-sm font-medium text-ink">
          Code d&apos;arrivée
        </span>
        <input
          autoFocus
          value={kept.length > 3 ? `${kept.slice(0, 3)} ${kept.slice(3)}` : kept}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && complete && !pending) onSubmit(kept);
          }}
          inputMode="text"
          autoCapitalize="characters"
          autoComplete="off"
          spellCheck={false}
          placeholder="A4K NM3"
          aria-describedby="checkin-code-help"
          className={`${inputClass} tabular text-center text-2xl font-semibold tracking-[0.3em]`}
        />
      </label>

      <p id="checkin-code-help" className="mt-2 text-xs text-muted">
        Six caractères, sous le QR de la cliente.{" "}
        {rejected.length > 0 ? (
          <span className="text-warning">
            Nos codes ne contiennent jamais {rejected.slice(0, 3).join(", ")} —
            relisez : c&apos;est sans doute {suggestion(rejected[0])}.
          </span>
        ) : (
          <span className="text-subtle">
            Ni O ni 0, ni I ni 1, ni S ni 5 : ces caractères n&apos;y figurent
            pas.
          </span>
        )}
      </p>

      <div className="mt-4 flex items-center gap-2">
        {/* Les pastilles disent où l'on en est sans compter les caractères
            soi-même : six creux qui se remplissent. */}
        <span aria-hidden className="flex flex-1 gap-1.5">
          {Array.from({ length: CODE_LENGTH }, (_, index) => (
            <span
              key={index}
              className={`h-1.5 flex-1 rounded-full transition ${
                index < kept.length ? "bg-salon" : "bg-line-strong"
              }`}
            />
          ))}
        </span>

        <Button
          type="button"
          pending={pending}
          disabled={!complete}
          onClick={() => onSubmit(kept)}
        >
          Enregistrer
        </Button>
      </div>
    </div>
  );
}

/**
 * Ce qu'un caractère exclu est probablement.
 *
 * C'est une aide à la relecture, affichée à la personne — jamais une
 * substitution appliquée au code. La différence est tout l'intérêt : c'est
 * elle qui regarde l'écran de la cliente et tranche, pas nous.
 */
function suggestion(char: string): string {
  const pairs: Record<string, string> = {
    O: "un D ou un Q mal lu",
    Q: "un D",
    "0": "un D",
    I: "un J",
    "1": "un 7",
    L: "un J",
    S: "un 5 qui n'existe pas non plus — regardez à nouveau",
    "5": "un F",
    B: "un E",
    "8": "un E",
    Z: "un 7",
    "2": "un 7",
    G: "un 6 ou un C",
    "6": "un C",
    U: "un V",
    "9": "un 4",
  };
  return pairs[char] ?? "un autre caractère";
}

/* --------------------------------------------------------------------------
 * Le verdict
 * ---------------------------------------------------------------------- */

const TONES: Record<
  Outcome["tone"],
  { chip: string; icon: "check" | "clock" | "close" }
> = {
  success: { chip: "bg-success-bg text-success", icon: "check" },
  warning: { chip: "bg-warning-bg text-warning", icon: "clock" },
  error: { chip: "bg-danger-bg text-danger", icon: "close" },
};

function Result({
  outcome,
  onAgain,
  onClose,
}: {
  outcome: Outcome;
  onAgain: () => void;
  onClose: () => void;
}) {
  const tone = TONES[outcome.tone];
  const booking = outcome.booking;

  return (
    <div>
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className={`flex size-11 shrink-0 items-center justify-center rounded-2xl ${tone.chip}`}
        >
          <Icon name={tone.icon} className="size-6" />
        </span>
        <div className="min-w-0 pt-0.5">
          <p className="text-base font-semibold text-ink">{outcome.title}</p>
          <p className="mt-0.5 text-sm leading-relaxed text-muted">
            {outcome.detail}
          </p>
        </div>
      </div>

      {booking && (
        /*
          La fiche du rendez-vous, même en cas de refus.

          C'est ce qui permet de trancher debout : « annulé » ne dit rien
          tant qu'on ne sait pas de quel rendez-vous ni de quelle cliente il
          s'agit. Deux colonnes dès le téléphone — quatre informations
          courtes empilées feraient défiler un écran qu'on lit en trois
          secondes.
        */
        <dl className="mt-4 grid grid-cols-2 gap-x-3 gap-y-3 rounded-2xl border border-line bg-surface-muted p-3.5">
          <Line label="Cliente" value={booking.customer_name} />
          <Line label="Prestation" value={booking.service_name} />
          <Line
            label="Heure"
            value={new Intl.DateTimeFormat("fr-FR", {
              weekday: "short",
              day: "numeric",
              month: "short",
              hour: "2-digit",
              minute: "2-digit",
            }).format(new Date(booking.starts_at))}
          />
          <Line label="Avec" value={booking.staff_member_name} />
        </dl>
      )}

      <div className="mt-5 flex flex-wrap gap-2">
        <Button
          type="button"
          onClick={onAgain}
          icon={<Icon name="scan" className="size-4" />}
        >
          Suivante
        </Button>
        <GhostButton type="button" onClick={onClose}>
          Fermer
        </GhostButton>
      </div>
    </div>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[0.68rem] uppercase tracking-[0.08em] text-subtle">
        {label}
      </dt>
      <dd className="mt-0.5 truncate text-sm font-medium text-ink">
        {value || "—"}
      </dd>
    </div>
  );
}
