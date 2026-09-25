"use client";

/**
 * Parcours de réservation en quatre étapes.
 *
 * Aucun créneau n'est inventé côté navigateur : la liste vient de l'API, et
 * le backend la revalide au moment de la réservation. Si le créneau part
 * entre-temps, on affiche le refus et les alternatives qu'il propose plutôt
 * que de laisser la cliente devant une erreur muette.
 */

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Lien } from "@/features/ui/Lien";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import {
  ApiRequestError,
  createBooking,
  fetchAvailability,
  joinWaitlist,
} from "@/lib/api";
import {
  formatDate,
  formatDayKey,
  formatDuration,
  formatPrice,
  formatServicePrice,
  formatTime,
} from "@/lib/format";
import {
  illustrationUrl,
  pickIllustration,
  themeFromCategory,
} from "@/lib/illustrations";
import type {
  BookingConfirmation,
  PublicSalon,
  PublicService,
  ServiceOption,
  ServiceRequirement,
  Slot,
  TravelZone,
} from "@/lib/types";
import { SalonIcon } from "@/features/salon/icons";
import {
  EMPTY_BASKET,
  RequirementsStep,
  basketTotal,
  unanswered,
  type Basket,
} from "./Requirements";
import { SalonLogo } from "@/features/salon/SalonLogo";
import { BeautySalonCredit } from "@/features/salon/BeautySalonCredit";
import { contactLinks, mapsHref, whatsappHref } from "@/features/salon/contact";

/**
 * Fenêtre demandée au serveur.
 *
 * Trente jours : c'est le plafond que le salon peut régler, et le serveur
 * ne renverra rien au-delà de son propre horizon de toute façon. Demander
 * plus ferait transiter des journées vides sur un forfait mobile.
 */
const HORIZON_DAYS = 30;

function bookingDateTime(iso: string, timeZone: string, locale: string): string {
  return new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  }).format(new Date(iso));
}

/**
 * L'acompte annoncé sur une carte de prestation.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi il se calcule, au lieu de se lire
 * ---------------------------------------------------------------------------
 *
 * Chaque prestation portait autrefois un montant, et cette carte l'affichait
 * tel quel : « acompte de 5 000 ». La réservation, elle, appliquait la règle
 * du salon — 30 % de 25 000 — et réclamait 7 500. Le salon publiait donc un
 * chiffre et en facturait un autre, et c'est la cliente qui le découvrait à
 * l'écran du paiement.
 *
 * Le montant annoncé suit désormais la même règle que le montant réclamé.
 * Il est volontairement calculé sur la prestation **seule** : options et
 * fournitures dépendent de ce que la cliente choisira ensuite, et les
 * inclure ici annoncerait une somme qu'on ne peut pas tenir. Le détail
 * complet apparaît à l'étape du récapitulatif, avant tout engagement.
 */
function serviceDeposit(service: PublicService, salon: PublicSalon, locale = "fr-FR"): string {
  const rate = salon.deposit_rate || 0;
  const minimum = Number(salon.deposit_minimum) || 0;

  // Sur devis, aucun prix ferme : annoncer la règle vaut mieux qu'annoncer
  // un montant tiré d'un prix qui n'existe pas encore.
  if (service.price_kind === "quote") return `${rate} % du devis`;

  const price = Number(service.price_amount) || 0;
  const due = Math.floor(Math.max(minimum, (price * rate) / 100));
  return formatPrice(String(due), salon.currency, locale);
}

const CARD =
  "rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] shadow-[0_1px_3px_rgb(23_23_28_/_0.06)]";

const CHOICE =
  "w-full rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] p-4 text-left transition hover:border-[var(--salon-primary)] hover:shadow-[0_4px_14px_-4px_rgb(23_23_28_/_0.14)]";

const INPUT =
  "w-full rounded-xl border border-[var(--site-line)] bg-[var(--site-surface)] px-3.5 py-2.5 text-[var(--site-ink)] transition focus:border-[var(--salon-primary)]";

const PRIMARY =
  "inline-flex items-center justify-center rounded-xl bg-[var(--salon-primary)] px-6 py-3.5 font-semibold text-white shadow-sm transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60";

/*
  Le schéma est une **fonction** de la langue.

  Les messages d'erreur d'un schéma Zod sont figés à sa construction. Écrit
  au niveau du module, il les fixait une fois pour toutes au démarrage du
  serveur — en français, quelle que soit la page. Construit à l'usage, il les
  demande au catalogue de la requête en cours.
*/
function schemaContact(t: (cle: string) => string) {
  return z.object({
    full_name: z.string().min(2, t("erreurs.nom")),
    phone: z
      .string()
      .min(6, t("erreurs.numeroCourt"))
      .regex(/^[0-9+\s().-]+$/, t("erreurs.numeroInvalide")),
    email: z.string().email(t("erreurs.email")).or(z.literal("")),
    customer_note: z.string().max(1000).optional(),
    // Obligatoire seulement pour un rendez-vous a domicile : la regle depend
    // du lieu choisi, que le schema ne connait pas. Elle est donc verifiee a
    // l'envoi, la ou l'information existe.
    address: z.string().max(255).optional(),
    accepts_policy: z.literal(true, {
      message: t("erreurs.politique"),
    }),
    marketing_consent: z.boolean().optional(),
    // Champ piège, laissé vide par une vraie visiteuse.
    website: z.string().max(0).optional(),
  });
}

type ContactValues = z.infer<ReturnType<typeof schemaContact>>;

type Step = "service" | "staff" | "options" | "slot" | "contact" | "done";

export function BookingFlow({
  salon,
  host,
  initialServiceId,
}: {
  salon: PublicSalon;
  host: string;
  /** Prestation choisie depuis le catalogue (`/reserver?service=…`). */
  initialServiceId?: string;
}) {
  const services = useMemo(
    () => salon.categories.flatMap((category) => category.services),
    [salon.categories],
  );

  /**
   * Arriver depuis une carte du catalogue saute la première étape.
   *
   * L'identifiant vient de l'URL, donc de l'extérieur : on ne le croit que
   * s'il désigne une prestation réellement proposée. Sinon on repart de la
   * liste, ce qui est toujours un état valide.
   */
  const preselected = initialServiceId
    ? (services.find((entry) => entry.id === initialServiceId) ?? null)
    : null;

  const staffFor = useCallback(
    (chosen: PublicService) =>
      salon.staff_members.filter((member) =>
        chosen.staff_member_ids.includes(member.id),
      ),
    [salon.staff_members],
  );

  const [step, setStep] = useState<Step>(() => {
    if (!preselected) return "service";
    return staffFor(preselected).length > 1 ? "staff" : "slot";
  });
  const [service, setService] = useState<PublicService | null>(preselected);
  const [staffId, setStaffId] = useState<string | null>(null);
  const [optionIds, setOptionIds] = useState<string[]>([]);
  const [basket, setBasket] = useState<Basket>(EMPTY_BASKET);
  const router = useRouter();

  /*
    Remonter en haut à chaque étape.

    React remplace le contenu mais laisse la position de défilement où elle
    était. On descend pour choisir un créneau dans une longue liste, l'étape
    suivante s'ouvre — et on se retrouve au milieu du formulaire de
    coordonnées, parfois sous son dernier champ, sans comprendre pourquoi la
    page « commence » là.

    Saut instantané et non fluide : faire défiler mille pixels en douceur
    donne le tournis et retarde la lecture de ce qu'on vient d'ouvrir.
  */
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [step]);
  const [slot, setSlot] = useState<Slot | null>(null);
  const [confirmation, setConfirmation] = useState<BookingConfirmation | null>(
    null,
  );

  const eligibleStaff = useMemo(
    () => (service ? staffFor(service) : []),
    [service, staffFor],
  );

  // Mémoïsé : `service?.options ?? []` fabrique un tableau neuf à chaque
  // rendu, ce qui relancerait le calcul en dessous à chaque fois.
  const options = useMemo(() => service?.options ?? [], [service]);
  const requirements = useMemo(() => service?.requirements ?? [], [service]);
  const chosenOptions = useMemo(
    () => options.filter((option) => optionIds.includes(option.id)),
    [options, optionIds],
  );

  /** Étape suivante après le choix du prestataire, selon ce qui existe. */
  const afterStaff = (chosen: PublicService): Step =>
    chosen.options.length > 0 || chosen.requirements.length > 0
      ? "options"
      : "slot";

  function chooseService(chosen: PublicService) {
    setService(chosen);
    setStaffId(null);
    setSlot(null);
    // Les options et les fournitures appartiennent à la prestation :
    // changer de prestation les remet à zéro plutôt que de traîner un choix
    // qui n'existe plus.
    setOptionIds([]);
    setBasket(EMPTY_BASKET);
    // Une seule personne peut réaliser la prestation : inutile de demander.
    setStep(staffFor(chosen).length > 1 ? "staff" : afterStaff(chosen));
  }

  if (step === "done" && confirmation) {
    return <Confirmation salon={salon} confirmation={confirmation} />;
  }

  return (
    /*
      Deux colonnes à partir du grand écran : le parcours à gauche, la
      réassurance à droite.

      Une page de paiement nue est l'endroit où l'on doute — « est-ce le bon
      salon ? », « où est-ce, exactement ? », « et si je dois annuler ? ».
      Répondre à côté du formulaire évite d'aller chercher ailleurs, donc de
      quitter le parcours. La colonne passe sous le formulaire sur mobile :
      elle rassure, elle ne précède pas l'action.
    */
    <div className="mx-auto grid w-full max-w-5xl gap-8 px-4 pb-8 pt-24 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
      <div className="min-w-0">
        <header className="mb-6">
          <Lien
            href="/"
            className="text-sm text-[var(--site-muted)] underline-offset-2 hover:underline"
          >
            {salon.name}
          </Lien>
        </header>

        <Steps
          current={step}
          hasStaffStep={eligibleStaff.length > 1}
          hasOptionsStep={options.length > 0 || requirements.length > 0}
        />

        {step === "service" && (
          <ServiceStep
            salon={salon}
            services={services}
            onChoose={chooseService}
          />
        )}

        {step === "staff" && service && (
          <StaffStep
            staff={eligibleStaff}
            onChoose={(id) => {
              setStaffId(id);
              setStep(afterStaff(service));
            }}
            onBack={() => setStep("service")}
          />
        )}

        {step === "options" && service && (
          <OptionsStep
            salon={salon}
            service={service}
            selected={optionIds}
            onToggle={(id) => {
              // Changer d'options change la durée, donc les créneaux : celui
              // qui était retenu ne l'est peut-être plus.
              setSlot(null);
              setOptionIds((current) =>
                current.includes(id)
                  ? current.filter((entry) => entry !== id)
                  : [...current, id],
              );
            }}
            requirements={requirements}
            basket={basket}
            onBasket={setBasket}
            currency={salon.currency}
            onNext={() => setStep("slot")}
            onBack={() =>
              setStep(eligibleStaff.length > 1 ? "staff" : "service")
            }
          />
        )}

        {step === "slot" && service && (
          <SlotStep
            // Changer de prestation ou de prestataire remonte le composant :
            // la liste de créneaux repart de zéro sans réinitialisation
            // manuelle dans l'effet.
            // Changer de prestation, de prestataire ou d'options remonte le
            // composant : la liste de créneaux repart de zéro sans
            // réinitialisation manuelle dans l'effet.
            key={`${service.id}-${staffId ?? "any"}-${[...optionIds].sort().join(",")}`}
            salon={salon}
            host={host}
            service={service}
            staffId={staffId}
            optionIds={optionIds}
            extraMinutes={chosenOptions.reduce(
              (total, option) => total + option.duration_delta_minutes,
              0,
            )}
            onChoose={(chosen) => {
              setSlot(chosen);
              setStep("contact");
            }}
            onBack={() =>
              setStep(
                options.length > 0
                  ? "options"
                  : eligibleStaff.length > 1
                    ? "staff"
                    : "service",
              )
            }
          />
        )}

        {step === "contact" && service && slot && (
          <ContactStep
            salon={salon}
            host={host}
            service={service}
            slot={slot}
            options={chosenOptions}
            basket={basket}
            requirements={requirements}
            onBack={() => setStep("slot")}
            onDone={(result) => {
              /*
              Un acompte à régler en ligne renvoie vers la page de paiement
              plutôt que vers l'écran de confirmation.

              Afficher « rendez-vous enregistré » puis demander de payer
              inverserait l'ordre : la cliente croit avoir fini, referme
              l'onglet, et le créneau se libère une demi-heure plus tard sans
              qu'elle comprenne pourquoi.

              Si elle referme quand même, rien n'est perdu de vue : la page
              de paiement se retrouve depuis son espace, et la page de suivi
              dit où en est le rendez-vous.
            */
              if (result.payment_token) {
                // `router.push` plutôt qu'un `location.assign` : ce dernier
                // recharge toute l'application pour une navigation interne,
                // ce qui sur un réseau mobile lent ajoute plusieurs secondes
                // juste avant le paiement.
                router.push(
                  `/paiement?token=${encodeURIComponent(result.payment_token)}`,
                );
                return;
              }
              setConfirmation(result);
              setStep("done");
            }}
            onSlotLost={() => setStep("slot")}
          />
        )}
      </div>

      <TrustPanel salon={salon} service={service} />
    </div>
  );
}

/**
 * Colonne de réassurance, à droite du parcours.
 *
 * Elle ne répète pas le formulaire : elle répond aux questions qui font
 * abandonner. Qui est ce salon, à quoi ressemble son travail, où est-il, et
 * que se passe-t-il si je dois annuler.
 *
 * Tout vient des données du salon. Rien n'est inventé : pas de « 4,9 étoiles »
 * décoratif, pas de compteur de clientes fictif. Un argument de confiance
 * qu'on ne peut pas vérifier produit l'effet inverse.
 */
function TrustPanel({
  salon,
  service,
}: {
  salon: PublicSalon;
  service: PublicService | null;
}) {
  const t = useTranslations("reservation");
  const locale = useLocale();
  const contacts = contactLinks(salon);
  const maps = mapsHref(salon);
  const whatsapp = whatsappHref(salon.whatsapp_number);

  // Un aperçu du travail : les médias mis en avant, sinon le début de la
  // galerie. Trois vignettes suffisent à donner une idée.
  const preview = [
    ...salon.gallery.filter((asset) => asset.featured),
    ...salon.gallery.filter((asset) => !asset.featured),
  ]
    .filter((asset) => !asset.content_type?.startsWith("video/"))
    .slice(0, 3);

  return (
    <aside className="space-y-4 lg:sticky lg:top-24">
      {/* ------------------------------------------------ identité du salon */}
      <div className={`${CARD} p-5`}>
        <div className="flex items-center gap-3">
          <SalonLogo
            logo={salon.logo}
            name={salon.name}
            className="size-12 text-lg"
          />
          <div className="min-w-0">
            <p className="truncate font-semibold text-[var(--site-ink)]">
              {salon.name}
            </p>
            {salon.city && (
              <p className="truncate text-sm text-[var(--site-muted)]">
                {salon.city}
              </p>
            )}
          </div>
        </div>

        {salon.rating?.average != null && (
          <p className="mt-3 flex items-center gap-2 text-sm">
            <span className="flex items-center gap-0.5 text-[var(--salon-ink)]">
              {[1, 2, 3, 4, 5].map((step) => (
                <SalonIcon
                  key={step}
                  name="star"
                  className="size-3.5"
                  filled={step <= Math.round(salon.rating!.average!)}
                />
              ))}
            </span>
            <span className="tabular font-semibold text-[var(--site-ink)]">
              {salon.rating.average.toFixed(1)}
            </span>
            <span className="text-[var(--site-muted)]">
              · {t("catalogue.avis", { n: salon.rating.count })}
            </span>
          </p>
        )}

        {preview.length > 0 && (
          <ul className="mt-4 grid grid-cols-3 gap-1.5">
            {preview.map((asset) => (
              <li key={asset.id}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={asset.url}
                  alt={asset.alt_text || ""}
                  loading="lazy"
                  className="aspect-square w-full rounded-lg object-cover"
                />
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* --------------------------------------------- prestation en cours */}
      {service && (
        <div className={`${CARD} p-5`}>
          <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--site-subtle)]">
            {t("etapes.choix")}
          </p>
          <div className="mt-3 flex items-center gap-3">
            <ServiceThumb service={service} />
            <div className="min-w-0">
              <p className="font-medium text-[var(--site-ink)]">
                {service.name}
              </p>
              <p className="mt-0.5 text-sm text-[var(--site-muted)]">
                {formatDuration(service.duration_minutes)} ·{" "}
                {formatServicePrice(service, salon.currency, locale)}
              </p>
            </div>
          </div>
          {service.description && (
            <p className="mt-3 text-sm leading-relaxed text-[var(--site-muted)]">
              {service.description}
            </p>
          )}
        </div>
      )}

      {/* ------------------------------------------------------- pratique */}
      <div className={`${CARD} p-5`}>
        <ul className="space-y-3 text-sm">
          {salon.address && (
            <li className="flex items-start gap-2.5">
              <SalonIcon
                name="pin"
                className="mt-0.5 size-4 shrink-0 text-[var(--salon-ink)]"
              />
              <span className="text-[var(--site-muted)]">
                {salon.address}
                {salon.city && `, ${salon.city}`}
                {maps && (
                  <>
                    {" — "}
                    <a
                      href={maps}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="font-medium text-[var(--salon-ink)] underline-offset-2 hover:underline"
                    >
                      {t("catalogue.itineraire")}
                    </a>
                  </>
                )}
              </span>
            </li>
          )}

          {contacts.map((contact) => (
            <li key={contact.key}>
              <a
                href={contact.href}
                {...(contact.external
                  ? { target: "_blank", rel: "noreferrer noopener" }
                  : {})}
                className="flex items-start gap-2.5 text-[var(--site-muted)] transition hover:text-[var(--salon-ink)]"
              >
                <SalonIcon
                  name={contact.icon}
                  className="mt-0.5 size-4 shrink-0 text-[var(--salon-ink)]"
                />
                {contact.value}
              </a>
            </li>
          ))}

          <li className="flex items-start gap-2.5">
            <SalonIcon
              name="check"
              className="mt-0.5 size-4 shrink-0 text-[var(--salon-ink)]"
            />
            <span className="text-[var(--site-muted)]">
              {t("catalogue.annulationGratuite", {
                hours: salon.cancellation_deadline_hours,
              })}
            </span>
          </li>

          {salon.late_policy && (
            <li className="flex items-start gap-2.5">
              <SalonIcon
                name="clock"
                className="mt-0.5 size-4 shrink-0 text-[var(--salon-ink)]"
              />
              <span className="text-[var(--site-muted)]">
                {salon.late_tolerance_minutes > 0
                  ? t("catalogue.retardJusqua", {
                      minutes: salon.late_tolerance_minutes,
                    })
                  : t("catalogue.aucunRetard")}
              </span>
            </li>
          )}

          <li className="flex items-start gap-2.5">
            <SalonIcon
              name="check"
              className="mt-0.5 size-4 shrink-0 text-[var(--salon-ink)]"
            />
            <span className="text-[var(--site-muted)]">
              {t("catalogue.confirmationImmediate")}
            </span>
          </li>
        </ul>

        {whatsapp && (
          <a
            href={whatsapp}
            target="_blank"
            rel="noreferrer noopener"
            className="mt-4 flex items-center justify-center gap-2 rounded-xl border border-[var(--site-line)] px-4 py-2.5 text-sm font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)] hover:text-[var(--salon-ink)]"
          >
            <SalonIcon name="whatsapp" className="size-4" />
            {t("catalogue.uneQuestion")}
          </a>
        )}
      </div>
    </aside>
  );
}

function Steps({
  current,
  hasStaffStep,
  hasOptionsStep,
}: {
  current: Step;
  hasStaffStep: boolean;
  hasOptionsStep: boolean;
}) {
  const t = useTranslations("reservation");
  // Les étapes qui n'existent pas pour cette prestation ne sont pas
  // affichées : montrer « 4 » puis sauter directement à « 5 » ferait croire
  // à une erreur, et allonger la barre décourage avant de commencer.
  const labels: [Step, string][] = [
    ["service", t("etapes.prestation")],
    ...(hasStaffStep ? ([["staff", t("etapes.prestataire")]] as [Step, string][]) : []),
    ...(hasOptionsStep ? ([["options", t("etapes.options")]] as [Step, string][]) : []),
    ["slot", t("etapes.creneau")],
    ["contact", t("etapes.coordonnees")],
  ];
  const index = labels.findIndex(([key]) => key === current);

  return (
    <nav aria-label={t("etapes.progression")} className="mb-7">
      <ol className="flex items-center gap-2">
        {labels.map(([key, label], position) => {
          const reached = position <= index;
          return (
            <li key={key} className="flex flex-1 items-center gap-2">
              <span
                aria-current={key === current ? "step" : undefined}
                className={`flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition ${
                  reached
                    ? "bg-[var(--salon-primary)] text-white"
                    : "bg-[var(--site-surface)] text-[var(--site-subtle)] ring-1 ring-[var(--site-line)]"
                }`}
              >
                {position < index ? "✓" : position + 1}
              </span>
              <span
                className={`hidden text-sm sm:block ${
                  key === current
                    ? "font-medium text-[var(--site-ink)]"
                    : "text-[var(--site-muted)]"
                }`}
              >
                {label}
              </span>
              {position < labels.length - 1 && (
                <span
                  aria-hidden
                  className={`h-px flex-1 ${
                    position < index
                      ? "bg-[var(--salon-primary)]"
                      : "bg-[var(--site-line)]"
                  }`}
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function ServiceStep({
  salon,
  services,
  onChoose,
}: {
  salon: PublicSalon;
  services: PublicService[];
  onChoose: (service: PublicService) => void;
}) {
  const t = useTranslations("reservation");
  const locale = useLocale();
  return (
    <section>
      <h1 className="mb-5 text-2xl font-semibold tracking-tight text-[var(--site-ink)]">
        {t("catalogue.quellePrestation")}
      </h1>

      {services.length === 0 ? (
        <p className={`${CARD} p-6 text-sm text-[var(--site-muted)]`}>
          {t("catalogue.vide")}
        </p>
      ) : (
        /*
          Chaque prestation porte sa vignette. Une liste de noms oblige à
          connaître déjà le vocabulaire du métier — « twists » et « box
          braids » ne disent rien à qui découvre. L'image tranche en une
          fraction de seconde, et c'est l'étape où l'on abandonne le plus.
        */
        <ul className="space-y-2.5">
          {services.map((service) => (
            <li key={service.id}>
              <button
                type="button"
                onClick={() => onChoose(service)}
                className={`${CHOICE} flex items-center gap-3.5`}
              >
                <ServiceThumb service={service} />

                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                    <span className="text-[0.95rem] font-medium text-[var(--site-ink)]">
                      {service.name}
                    </span>
                    <span className="tabular shrink-0 font-semibold text-[var(--salon-ink)]">
                      {formatServicePrice(service, salon.currency, locale)}
                    </span>
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-[var(--site-muted)]">
                    <span>{formatDuration(service.duration_minutes)}</span>
                    {/* L'acompte annoncé est celui qui sera réclamé.
                        Auparavant la carte affichait le montant inscrit sur
                        la fiche, et la page de règlement en demandait un
                        autre, calculé au pourcentage : 5 000 annoncés,
                        7 500 réclamés. */}
                    {service.requires_deposit && (
                      <>
                        <span aria-hidden>·</span>
                        <span>{t("catalogue.acompteDe", { amount: serviceDeposit(service, salon, locale) })}</span>
                      </>
                    )}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * Vignette d'une prestation, avec repli sur une illustration.
 *
 * Le repli suit le nom de la prestation : « Pose gel » sort une main
 * manucurée, pas un fauteuil de barbier. Il est déterministe, donc la même
 * prestation garde la même vignette d'un écran à l'autre — la cliente
 * retrouve visuellement ce qu'elle a choisi à l'étape précédente.
 */
function ServiceThumb({ service }: { service: PublicService }) {
  const source = service.image
    ? service.image.url
    : illustrationUrl(
        pickIllustration(service.id, themeFromCategory(service.name)).id,
        { width: 220, ratio: 1 },
      );

  return (
    <span className="relative size-16 shrink-0 overflow-hidden rounded-xl bg-black/[0.04] sm:size-20">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={source}
        alt=""
        loading="lazy"
        className="size-full object-cover"
      />
      {!service.image && (
        <span
          aria-hidden
          className="absolute inset-0 opacity-25 mix-blend-multiply"
          style={{ background: "var(--salon-primary)" }}
        />
      )}
    </span>
  );
}

function StaffStep({
  staff,
  onChoose,
  onBack,
}: {
  staff: PublicSalon["staff_members"];
  onChoose: (id: string | null) => void;
  onBack: () => void;
}) {
  const t = useTranslations("reservation");
  return (
    <section>
      <BackLink onClick={onBack} />
      <h1 className="mb-5 text-2xl font-semibold tracking-tight text-[var(--site-ink)]">
        {t("catalogue.avecQui")}
      </h1>

      <ul className="space-y-2.5">
        <li>
          <button
            type="button"
            onClick={() => onChoose(null)}
            className={CHOICE}
          >
            <span className="font-medium text-[var(--site-ink)]">
              {t("catalogue.peuImporte")}
            </span>
            <span className="mt-0.5 block text-sm text-[var(--site-muted)]">
              {t("catalogue.plusDeCreneaux")}
            </span>
          </button>
        </li>

        {staff.map((member) => (
          <li key={member.id}>
            <button
              type="button"
              onClick={() => onChoose(member.id)}
              className={`${CHOICE} flex items-center gap-3`}
            >
              {member.photo ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={member.photo.url}
                  alt=""
                  className="size-11 shrink-0 rounded-full object-cover"
                />
              ) : (
                <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-[var(--salon-accent)] font-semibold text-[var(--salon-ink-accent)]">
                  {member.name.slice(0, 1).toUpperCase()}
                </span>
              )}

              <span className="min-w-0">
                <span className="block font-medium text-[var(--site-ink)]">
                  {member.name}
                </span>
                {member.specialty && (
                  <span className="block text-sm text-[var(--site-muted)]">
                    {member.specialty}
                  </span>
                )}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function SlotStep({
  salon,
  host,
  service,
  staffId,
  optionIds,
  extraMinutes,
  onChoose,
  onBack,
}: {
  salon: PublicSalon;
  host: string;
  service: PublicService;
  staffId: string | null;
  optionIds: string[];
  /** Temps ajouté par les options, pour l'affichage de la durée. */
  extraMinutes: number;
  onChoose: (slot: Slot) => void;
  onBack: () => void;
}) {
  const t = useTranslations("reservation");
  const locale = useLocale();
  const [slots, setSlots] = useState<Slot[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [horizon, setHorizon] = useState<Horizon>("month");

  useEffect(() => {
    let cancelled = false;
    const today = new Date();
    const end = new Date(today);
    end.setDate(end.getDate() + HORIZON_DAYS);

    fetchAvailability({
      host,
      serviceId: service.id,
      staffMemberId: staffId ?? undefined,
      from: today.toISOString().slice(0, 10),
      to: end.toISOString().slice(0, 10),
      // Le serveur recalcule la durée à partir de ces identifiants : les
      // créneaux proposés sont ceux qui contiennent vraiment la prestation
      // rallongée, pas ceux de la durée de base.
      optionIds,
    })
      .then((result) => !cancelled && setSlots(result))
      .catch(() => !cancelled && setError(t("erreurs.disponibilites")));

    return () => {
      cancelled = true;
    };
    // `t` : stable tant que la langue ne change pas, et une bascule de langue
    // recharge la page entière — mais le linter ne le sait pas, et l'omettre
    // masquerait un vrai oubli le jour où la dépendance cessera d'être stable.
  }, [host, service.id, staffId, optionIds, t]);

  /*
    La prestation tient-elle dans au moins une plage d'ouverture ?

    Distingue « le salon est complet » de « les journées du salon sont trop
    courtes pour cette prestation ». Les deux donnent une liste vide, mais
    l'un s'attend et l'autre jamais — proposer la liste d'attente dans le
    second cas serait une promesse intenable.
  */
  const needed = service.duration_minutes + extraMinutes;
  const tooLongForEveryBlock = useMemo(() => {
    const blocks = salon.business_hours ?? [];
    if (blocks.length === 0) return false;

    const minutesOf = (value: string) => {
      const [h, m] = value.split(":");
      return Number(h) * 60 + Number(m);
    };

    return blocks.every(
      (block) => minutesOf(block.ends_at) - minutesOf(block.starts_at) < needed,
    );
  }, [salon.business_hours, needed]);

  // Un seul créneau par heure : proposer la même heure pour trois
  // prestataires différents n'aide pas la cliente à choisir.
  const byDay = useMemo(() => {
    if (!slots) return [];
    const groups = new Map<string, Slot[]>();
    const seen = new Set<string>();

    for (const item of slots) {
      if (seen.has(item.starts_at)) continue;
      seen.add(item.starts_at);
      const key = formatDayKey(item.starts_at, salon.timezone);
      groups.set(key, [...(groups.get(key) ?? []), item]);
    }
    return [...groups.entries()];
  }, [slots, salon.timezone]);

  // Dérivé, jamais stocké : la fenêtre choisie ne change pas les données,
  // seulement ce qu'on en montre.
  const visibleDays = useMemo(
    () =>
      byDay.filter(([, daySlots]) =>
        within(daySlots[0].starts_at, horizon, salon.timezone),
      ),
    [byDay, horizon, salon.timezone],
  );

  return (
    <section>
      <BackLink onClick={onBack} />
      <h1 className="text-2xl font-semibold tracking-tight text-[var(--site-ink)]">
        {t("creneaux.titre")}
      </h1>
      <p className="mb-6 mt-1.5 text-sm text-[var(--site-muted)]">
        {service.name} ·{" "}
        {/* La durée annoncée est celle du rendez-vous réel, options
            comprises : afficher « 2 h » pour un créneau de 3 h 30 ferait
            croire à une erreur au moment de comparer avec l'agenda. */}
        {formatDuration(service.duration_minutes + extraMinutes)}
        {extraMinutes > 0 && (
          <span className="text-[var(--site-subtle)]">
            {" "}
            {t("options.avecVosOptions")}
          </span>
        )}
      </p>

      {slots === null && !error && (
        <div className="space-y-6" aria-busy>
          {[0, 1].map((group) => (
            <div key={group}>
              <div className="skeleton mb-3 h-4 w-40 rounded" />
              <div className="flex flex-wrap gap-2">
                {[0, 1, 2, 3, 4, 5].map((cell) => (
                  <div key={cell} className="skeleton h-10 w-20 rounded-xl" />
                ))}
              </div>
            </div>
          ))}
          <span className="sr-only">{t("creneaux.chargement")}</span>
        </div>
      )}

      {error && (
        <p
          className={`${CARD} p-4 text-sm text-[var(--site-ink)]`}
          role="alert"
        >
          {error}
        </p>
      )}

      {/*
        Vide, mais jamais muet.

        Trouvé en testant : deux options portaient la pose à 5 h 15 alors que
        l'après-midi du salon en fait 5 — plus aucun créneau, et un écran
        blanc sans explication. Le moteur avait raison, l'écran avait tort.

        Quand des options sont en cause, on le dit et on propose le seul
        geste utile : revenir les alléger. Sans options, le message reste
        celui d'un agenda plein.
      */}
      {slots?.length === 0 &&
        (extraMinutes > 0 ? (
          <div
            className={`${CARD} border-l-4 border-l-amber-500 p-5 text-sm text-[var(--site-ink)]`}
          >
            <p className="font-medium">
              {t("creneaux.aucunAvecOptions", {
                duration: formatDuration(service.duration_minutes + extraMinutes),
              })}
            </p>
            <p className="mt-1.5 text-[var(--site-muted)]">
              {t("creneaux.optionsTropLongues", {
                duration: formatDuration(extraMinutes),
              })}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={onBack}
                className={`${PRIMARY} px-5 py-2.5`}
              >
                {t("creneaux.revoirOptions")}
              </button>
              {whatsappHref(salon.whatsapp_number) && (
                <a
                  href={whatsappHref(salon.whatsapp_number) as string}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-2 rounded-xl border border-[var(--site-line)] px-5 py-2.5 font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)]"
                >
                  <SalonIcon name="whatsapp" className="size-4" />
                  {t("creneaux.ecrireAuSalon")}
                </a>
              )}
            </div>
          </div>
        ) : tooLongForEveryBlock ? (
          /*
            Aucune plage du salon ne dure assez longtemps.

            Ce cas se confondait avec « agenda plein », et c'est ce qui le
            rendait pénible : la liste d'attente promettait une place qui ne
            se libérerait jamais, puisque le problème n'est pas l'occupation
            mais la longueur des journées.

            On le dit donc, et on renvoie vers le salon — seul capable
            d'ouvrir plus tôt ou de proposer un autre format.
          */
          <div
            className={`${CARD} border-l-4 border-l-amber-500 p-5 text-sm text-[var(--site-ink)] sm:p-6`}
          >
            <p className="font-medium">
              {t("creneaux.prestationTropLongue", {
                service: service.name,
                duration: formatDuration(service.duration_minutes + extraMinutes),
              })}
            </p>
            <p className="mt-1.5 text-[var(--site-muted)]">
              {t("creneaux.journeesTropCourtes", { salon: salon.name })}
            </p>
            {whatsappHref(salon.whatsapp_number) && (
              <a
                href={whatsappHref(salon.whatsapp_number) as string}
                target="_blank"
                rel="noreferrer noopener"
                className={`${PRIMARY} mt-4 px-5 py-2.5`}
              >
                <SalonIcon name="whatsapp" className="size-4" />
                {t("creneaux.ecrireAuSalon")}
              </a>
            )}
          </div>
        ) : (
          <div className={`${CARD} p-5 text-sm text-[var(--site-ink)] sm:p-6`}>
            <p className="font-medium">{t("creneaux.aucunTroisSemaines")}</p>
            <p className="mt-1.5 text-[var(--site-muted)]">
              {t("creneaux.listeAttente")}
            </p>
            <WaitlistForm host={host} service={service} staffId={staffId} />
          </div>
        ))}

      <div className="space-y-7">
        {/*
          Trois fenêtres de lecture.

          Trente jours de créneaux font une page qu'on ne parcourt pas :
          on cherche « cette semaine » ou « ce mois-ci », pas la liste
          complète. Le filtre est posé sur ce qui est déjà chargé — aucun
          aller-retour réseau, donc la bascule est instantanée.
        */}
        {byDay.length > 1 && (
          <div
            role="tablist"
            aria-label={t("creneaux.periode")}
            className="mb-4 flex rounded-xl border border-[var(--site-line)] bg-[var(--site-surface)] p-0.5"
          >
            {(
              [
                ["day", t("creneaux.aujourdhui")],
                ["week", t("creneaux.septJours")],
                ["month", t("creneaux.trenteJours")],
              ] as [Horizon, string][]
            ).map(([key, label]) => {
              const count = countWithin(byDay, key, salon.timezone);
              return (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={horizon === key}
                  onClick={() => setHorizon(key)}
                  className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-sm transition ${
                    horizon === key
                      ? "salon-gradient font-medium text-white"
                      : "text-[var(--site-muted)] hover:text-[var(--site-ink)]"
                  }`}
                >
                  {label}
                  <span
                    className={`tabular text-xs ${
                      horizon === key
                        ? "text-white/70"
                        : "text-[var(--site-subtle)]"
                    }`}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {visibleDays.length === 0 && byDay.length > 0 && (
          <p className="mb-4 rounded-xl border border-[var(--site-line)] p-4 text-sm text-[var(--site-muted)]">
            {t("creneaux.rienCettePeriode")}
          </p>
        )}

        {visibleDays.map(([day, daySlots]) => (
          <div key={day}>
            <h2 className="mb-2.5 text-sm font-semibold text-[var(--site-ink)] first-letter:uppercase">
              {formatDate(daySlots[0].starts_at, salon.timezone, locale)}
              <span className="ml-2 font-normal text-[var(--site-subtle)]">
                {t("creneaux.nombre", { n: daySlots.length })}
              </span>
            </h2>

            <div className="flex flex-wrap gap-2">
              {daySlots.map((item) => (
                <button
                  key={item.starts_at}
                  type="button"
                  onClick={() => onChoose(item)}
                  className="tabular rounded-xl border border-[var(--site-line)] bg-[var(--site-surface)] px-4 py-2.5 text-sm font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)] hover:bg-[var(--salon-primary)] hover:text-white"
                >
                  {formatTime(item.starts_at, salon.timezone)}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ContactStep({
  salon,
  host,
  service,
  slot,
  options,
  basket,
  requirements,
  onBack,
  onDone,
  onSlotLost,
}: {
  salon: PublicSalon;
  host: string;
  service: PublicService;
  slot: Slot;
  options: ServiceOption[];
  basket: Basket;
  requirements: ServiceRequirement[];
  onBack: () => void;
  onDone: (confirmation: BookingConfirmation) => void;
  onSlotLost: () => void;
}) {
  const t = useTranslations("reservation");
  const langue = useLocale();
  const [submitError, setSubmitError] = useState<string | null>(null);

  /*
   * Lieu du rendez-vous.
   *
   * `travels` : la prestation peut se faire ailleurs qu'au salon, et le
   * salon a bien déclaré des zones — sans grille, il n'y a rien à choisir.
   * `homeOnly` : la question ne se pose pas, on n'affiche pas de bascule
   * pour un choix qui n'en est pas un.
   */
  const zones = salon.travel_zones;
  const homeOnly = service.location_mode === "home";
  const travels = zones.length > 0 && service.location_mode !== "salon";

  const [atHome, setAtHome] = useState(homeOnly && travels);
  const [zoneId, setZoneId] = useState<string | null>(
    // Une seule zone desservie : la choisir pour la cliente. Lui présenter
    // une liste d'un seul élément est une question dont on connaît déjà la
    // réponse.
    travels && zones.length === 1 ? zones[0].id : null,
  );
  const [zoneError, setZoneError] = useState<string | null>(null);

  const zone = atHome
    ? (zones.find((entry) => entry.id === zoneId) ?? null)
    : null;

  // Généré une fois par tentative : rejouer la même requête ne crée pas
  // une seconde réservation.
  const idempotencyKey = useRef(crypto.randomUUID());

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ContactValues>({
    resolver: zodResolver(schemaContact(t)),
    defaultValues: { email: "", customer_note: "", website: "", address: "" },
  });

  const submit = useCallback(
    async (values: ContactValues) => {
      setSubmitError(null);
      setZoneError(null);

      // Le serveur refait ces deux contrôles ; les faire ici évite un
      // aller-retour pour une erreur qu'on peut voir tout de suite.
      if (atHome && !zone) {
        setZoneError(t("erreurs.zone"));
        return;
      }
      if (zone && !values.address?.trim()) {
        setError("address", {
          message: t("erreurs.adresse"),
        });
        return;
      }

      try {
        const confirmation = await createBooking({
          host,
          idempotencyKey: idempotencyKey.current,
          payload: {
            service: service.id,
            staff_member: slot.staff_member_id,
            starts_at: slot.starts_at,
            full_name: values.full_name,
            phone: values.phone,
            email: values.email || undefined,
            customer_note: values.customer_note,
            options: options.map((option) => option.id),
            // Seuls l'identifiant et la quantité partent : le prix est relu
            // en base côté serveur.
            items: Object.entries(basket.items).map(([product, quantity]) => ({
              product,
              quantity,
            })),
            owned_requirements: basket.owned,
            travel_zone: zone?.id,
            address: zone ? values.address?.trim() : undefined,
            marketing_consent: values.marketing_consent ?? false,
            accepts_policy: true,
            /*
              La langue dans laquelle elle vient de lire tout ceci.

              Elle est retenue sur la reservation, et decide de la langue de
              la confirmation, du rappel de la veille et de la demande
              d avis. Sans elle, une cliente qui a tout lu en anglais — les
              prestations, le prix, la politique d annulation qu elle vient
              de cocher — recevrait son justificatif en francais.
            */
            language: langue,
            website: values.website ?? "",
          },
        });
        onDone(confirmation);
      } catch (error) {
        if (
          error instanceof ApiRequestError &&
          error.code === "slot_unavailable"
        ) {
          setSubmitError(t("erreurs.creneauPris"));
          // Nouvelle tentative = nouvelle clé d'idempotence.
          idempotencyKey.current = crypto.randomUUID();
          setTimeout(onSlotLost, 1500);
          return;
        }
        setSubmitError(
          error instanceof ApiRequestError ? error.message : t("erreurs.echec"),
        );
      }
    },
    [
      host,
      service.id,
      slot,
      options,
      basket,
      atHome,
      zone,
      setError,
      onDone,
      onSlotLost,
      t,
      langue,
    ],
  );

  return (
    <section>
      <BackLink onClick={onBack} />
      <h1 className="mb-5 text-2xl font-semibold tracking-tight text-[var(--site-ink)]">
        {t("coordonnees.titre")}
      </h1>

      <div
        className={`${CARD} mb-6 flex items-start gap-3 border-l-4 border-l-[var(--salon-primary)] p-4`}
      >
        <div className="min-w-0 text-sm">
          <p className="font-medium text-[var(--site-ink)]">{service.name}</p>
          <p className="mt-1 text-[var(--site-muted)] first-letter:uppercase">
            {bookingDateTime(slot.starts_at, salon.timezone, langue)}
          </p>
          {/*
            Le total se recompose sous les yeux de la cliente.

            Les frais de déplacement sont la seule ligne qu'elle ne peut pas
            deviner : la voir apparaître au moment où elle choisit sa zone
            vaut mieux que la découvrir sur la facture — ou pire, à l'arrivée
            du prestataire.
          */}
          <p className="mt-1 tabular font-medium text-[var(--salon-ink)]">
            {formatServicePrice(service, salon.currency, langue)}
          </p>

          {/* Les options sont rappelées ligne par ligne, pas fondues dans un
              total : la cliente doit reconnaître ce qu'elle a coché deux
              écrans plus tôt. */}
          {options.length > 0 && (
            <ul className="mt-2 space-y-0.5 border-t border-[var(--site-line)] pt-2">
              {options.map((option) => (
                <li
                  key={option.id}
                  className="flex flex-wrap items-baseline justify-between gap-x-2 text-[var(--site-muted)]"
                >
                  <span className="min-w-0">{option.name}</span>
                  <span className="tabular">
                    {Number(option.price_delta) === 0
                      ? t("attente.inclus")
                      : `+ ${formatPrice(option.price_delta, salon.currency, langue)}`}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {/* Les fournitures achetées, ligne par ligne : la cliente doit
              reconnaître ce qu'elle a mis au panier deux écrans plus tôt. */}
          {requirements.flatMap((requirement) =>
            requirement.products
              .filter((product) => basket.items[product.id])
              .map((product) => (
                <p
                  key={product.id}
                  className="mt-1 flex flex-wrap items-baseline justify-between gap-x-2 text-[var(--site-muted)]"
                >
                  <span className="min-w-0">
                    {product.name}
                    <span className="tabular text-[var(--site-subtle)]">
                      {" "}
                      × {basket.items[product.id]}
                    </span>
                  </span>
                  <span className="tabular">
                    {formatPrice(
                      String(Number(product.price) * basket.items[product.id]),
                      salon.currency,
                      langue,
                    )}
                  </span>
                </p>
              )),
          )}

          {zone && (
            <div className="mt-2 border-t border-[var(--site-line)] pt-2">
              <p className="flex flex-wrap items-baseline gap-x-1.5 text-[var(--site-muted)]">
                <span>
                  {Number(zone.fee_amount) === 0
                    ? t("lieu.deplacementOffert")
                    : t("lieu.fraisDeplacement", {
                        amount: formatPrice(zone.fee_amount, salon.currency, langue),
                      })}
                </span>
                <span className="text-[var(--site-subtle)]">· {zone.name}</span>
              </p>
              {Number(zone.fee_amount) > 0 && (
                <p className="mt-1 tabular text-base font-semibold text-[var(--site-ink)]">
                  {formatPrice(
                    String(
                      Number(service.price_amount) +
                        options.reduce(
                          (total, option) => total + Number(option.price_delta),
                          0,
                        ) +
                        basketTotal(requirements, basket) +
                        Number(zone.fee_amount),
                    ),
                    salon.currency,
                    langue,
                  )}
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* handleSubmit est appelé dans le gestionnaire, pas pendant le rendu :
          react-hook-form lit des refs, ce qui n'a rien à y faire. */}
      <form
        onSubmit={(event) => void handleSubmit(submit)(event)}
        className="space-y-4"
        noValidate
      >
        {travels && (
          <LocationStep
            salon={salon}
            zones={zones}
            homeOnly={homeOnly}
            atHome={atHome}
            zoneId={zoneId}
            zoneError={zoneError}
            addressError={errors.address?.message}
            addressField={register("address")}
            onChangeMode={(home) => {
              setAtHome(home);
              setZoneError(null);
              if (!home) setZoneId(null);
              else if (zones.length === 1) setZoneId(zones[0].id);
            }}
            onChangeZone={(id) => {
              setZoneId(id);
              setZoneError(null);
            }}
          />
        )}

        <Field label={t("coordonnees.nomComplet")} error={errors.full_name?.message}>
          <input
            {...register("full_name")}
            autoComplete="name"
            className={INPUT}
          />
        </Field>

        <Field
          label={t("coordonnees.telephone")}
          hint={t("coordonnees.telephoneAide")}
          error={errors.phone?.message}
        >
          <input
            {...register("phone")}
            type="tel"
            autoComplete="tel"
            inputMode="tel"
            className={INPUT}
          />
        </Field>

        <Field
          label={t("coordonnees.emailFacultatif")}
          hint={t("coordonnees.emailAide")}
          error={errors.email?.message}
        >
          <input
            {...register("email")}
            type="email"
            autoComplete="email"
            className={INPUT}
          />
        </Field>

        <Field label={t("coordonnees.message")}>
          <textarea {...register("customer_note")} rows={3} className={INPUT} />
        </Field>

        {/* Piège à robots : masqué visuellement et retiré du parcours clavier. */}
        <div aria-hidden className="absolute left-[-9999px]">
          <label htmlFor="website">{t("coordonnees.siteWeb")}</label>
          <input
            id="website"
            tabIndex={-1}
            autoComplete="off"
            {...register("website")}
          />
        </div>

        <div className={`${CARD} space-y-3 p-4`}>
          <label className="flex items-start gap-2.5 text-sm">
            <input
              type="checkbox"
              {...register("accepts_policy")}
              className="mt-0.5 size-4 accent-[var(--salon-primary)]"
            />
            <span className="text-[var(--site-ink)]">
              {t("coordonnees.acceptePolitique")}
              {salon.cancellation_policy && (
                <span className="mt-1 block text-[var(--site-muted)]">
                  {salon.cancellation_policy}
                </span>
              )}
              {/* Le retard est rappelé ici, au moment de l'engagement, plutôt
                  que sur une page d'information que personne ne rouvre. */}
              {salon.late_policy && (
                <span className="mt-2 block text-[var(--site-muted)]">
                  <span className="font-medium text-[var(--site-ink)]">
                    {salon.late_tolerance_minutes > 0
                      ? t("catalogue.retardMinutes", {
                          minutes: salon.late_tolerance_minutes,
                        })
                      : t("catalogue.aucunRetard")}
                  </span>{" "}
                  {salon.late_policy}
                </span>
              )}
            </span>
          </label>
          {errors.accepts_policy && (
            <p className="text-sm font-medium text-red-600">
              {errors.accepts_policy.message}
            </p>
          )}

          <label className="flex items-start gap-2.5 text-sm">
            <input
              type="checkbox"
              {...register("marketing_consent")}
              className="mt-0.5 size-4 accent-[var(--salon-primary)]"
            />
            <span className="text-[var(--site-ink)]">
              {t("coordonnees.offres")}
            </span>
          </label>
        </div>

        {submitError && (
          <p
            role="alert"
            className="rounded-xl bg-red-50 p-3 text-sm font-medium text-red-700"
          >
            {submitError}
          </p>
        )}

        <button
          type="submit"
          disabled={isSubmitting}
          className={`${PRIMARY} w-full`}
        >
          {isSubmitting ? t("coordonnees.envoi") : t("coordonnees.confirmer")}
        </button>

        <p className="text-center text-xs text-[var(--site-subtle)]">
          {t("coordonnees.usage")}
        </p>
      </form>
    </section>
  );
}

function Confirmation({
  salon,
  confirmation,
}: {
  salon: PublicSalon;
  confirmation: BookingConfirmation;
}) {
  const t = useTranslations("reservation");
  const locale = useLocale();
  const whatsapp = salon.whatsapp_number.replace(/[^0-9]/g, "");
  const when = bookingDateTime(confirmation.starts_at, salon.timezone, locale);

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-16 text-center">
      <span className="inline-flex size-14 items-center justify-center rounded-full bg-[var(--salon-accent)] text-[var(--salon-ink-accent)]">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          className="size-7"
        >
          <path
            d="M20 6 9 17l-5-5"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>

      <h1 className="mt-5 text-2xl font-semibold tracking-tight text-[var(--site-ink)]">
        {t("attente.enregistre")}
      </h1>
      <p className="mt-2 text-[var(--site-muted)]">
        {t("attente.demandeRecue", { salon: salon.name })}
      </p>

      <div className={`${CARD} mx-auto mt-7 max-w-sm p-5 text-left`}>
        <p className="font-medium text-[var(--site-ink)]">
          {confirmation.service_name}
        </p>
        <p className="mt-1.5 text-sm text-[var(--site-muted)] first-letter:uppercase">
          {when}
        </p>
        <p className="mt-1 text-sm text-[var(--site-muted)]">
          {t("attente.avec")} {confirmation.staff_member_name}
        </p>

        {confirmation.options_snapshot.length > 0 && (
          <ul className="mt-3 space-y-0.5 border-t border-[var(--site-line)] pt-3 text-sm">
            {confirmation.options_snapshot.map((option) => (
              <li
                key={option.name}
                className="flex flex-wrap items-baseline justify-between gap-x-2 text-[var(--site-muted)]"
              >
                <span className="min-w-0">{option.name}</span>
                <span className="tabular">
                  {Number(option.price) === 0
                    ? t("attente.inclus")
                    : `+ ${formatPrice(option.price, salon.currency, locale)}`}
                </span>
              </li>
            ))}
          </ul>
        )}

        {/*
          Les fournitures achetées.

          Cet écran sert de reçu — c'est lui qu'on photographie. Y lire
          « Box braids » seul après avoir payé 690 pour une prestation
          affichée à 450 est le genre d'écart qui fait rappeler le salon.
        */}
        {confirmation.items_snapshot.length > 0 && (
          <ul className="mt-3 space-y-0.5 border-t border-[var(--site-line)] pt-3 text-sm">
            {confirmation.items_snapshot.map((item) => (
              <li
                key={item.name}
                className="flex flex-wrap items-baseline justify-between gap-x-2 text-[var(--site-muted)]"
              >
                <span className="min-w-0">
                  {item.name}
                  <span className="tabular text-[var(--site-subtle)]">
                    {" "}
                    × {item.quantity}
                  </span>
                </span>
                <span className="tabular">
                  {formatPrice(item.total, salon.currency, locale)}
                </span>
              </li>
            ))}
          </ul>
        )}

        {/* Le total dès que quelque chose s'ajoute à la prestation :
            c'est le chiffre que la cliente vient vérifier, et le seul
            qu'elle ne pouvait pas deviner en arrivant sur la page. */}
        {(confirmation.items_snapshot.length > 0 ||
          confirmation.options_snapshot.length > 0 ||
          Number(confirmation.travel_fee_amount ?? 0) > 0) && (
          <p className="mt-3 flex flex-wrap items-baseline justify-between gap-x-2 border-t border-[var(--site-line)] pt-3 text-sm font-medium text-[var(--site-ink)]">
            <span>{t("total")}</span>
            <span className="tabular">
              {formatPrice(confirmation.total_amount, salon.currency, locale)}
            </span>
          </p>
        )}

        {/* Le déplacement est répété ici : c'est l'écran qu'on capture en
            photo pour s'en souvenir, et le seul montant que la cliente ne
            pouvait pas deviner en arrivant sur la page. */}
        {confirmation.travel_zone_name && (
          <p className="mt-3 flex items-start gap-2 rounded-xl bg-[var(--site-surface-muted,transparent)] text-sm text-[var(--site-muted)]">
            <SalonIcon
              name="home"
              className="mt-0.5 size-4 shrink-0 text-[var(--salon-ink)]"
            />
            <span>
              {t("attente.aDomicile")} · {confirmation.travel_zone_name}
              {Number(confirmation.travel_fee_amount) > 0 && (
                <>
                  {" — "}
                  <span className="tabular font-medium text-[var(--site-ink)]">
                    {t("attente.deplacementInclus", {
                      amount: formatPrice(
                        confirmation.travel_fee_amount,
                        salon.currency,
                        locale,
                      ),
                    })}
                  </span>
                </>
              )}
            </span>
          </p>
        )}

        {Number(confirmation.deposit_amount) > 0 && (
          <p className="mt-4 rounded-xl bg-[var(--salon-accent)]/40 p-3 text-sm text-[var(--site-ink)]">
            {t("attente.acompteDemande", {
              amount: formatPrice(confirmation.deposit_amount, salon.currency, locale),
            })}
          </p>
        )}
      </div>

      <div className="mt-7 flex flex-wrap justify-center gap-3">
        {whatsapp && (
          <a
            href={`https://wa.me/${whatsapp}`}
            target="_blank"
            rel="noreferrer noopener"
            className="rounded-xl border border-[var(--site-line)] bg-[var(--site-surface)] px-6 py-3 font-medium text-[var(--site-ink)] transition hover:bg-black/[0.03]"
          >
            {t("attente.contacterWhatsApp")}
          </a>
        )}
        <Lien
          href="/"
          className="rounded-xl px-6 py-3 font-medium text-[var(--site-muted)] underline-offset-2 hover:underline"
        >
          {t("attente.revenirAuSalon")}
        </Lien>
      </div>
      <div className="mt-8">
        <BeautySalonCredit />
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-[var(--site-ink)]">
        {label}
      </span>
      {children}
      {hint && !error && (
        <span className="mt-1.5 block text-xs text-[var(--site-muted)]">
          {hint}
        </span>
      )}
      {error && (
        <span className="mt-1.5 block text-xs font-medium text-red-600">
          {error}
        </span>
      )}
    </label>
  );
}

function BackLink({ onClick }: { onClick: () => void }) {
  const t = useTranslations("reservation");
  return (
    <button
      type="button"
      onClick={onClick}
      className="mb-3 inline-flex items-center gap-1.5 text-sm text-[var(--site-muted)] transition hover:text-[var(--site-ink)]"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        aria-hidden
        className="size-4"
      >
        <path
          d="M15 6l-6 6 6 6"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {t("retour")}
    </button>
  );
}

/* -------------------------------------------------------------------------
 * Lieu du rendez-vous
 * ---------------------------------------------------------------------- */

/**
 * Au salon ou chez moi, et à quel prix.
 *
 * ---------------------------------------------------------------------------
 * Ce que ce bloc évite
 * ---------------------------------------------------------------------------
 *
 * Sans lui, une prestation à domicile se réservait comme une autre et les
 * frais de trajet se négociaient au téléphone — ou se découvraient sur le pas
 * de la porte. C'est la situation qui fait le plus de rendez-vous annulés :
 * personne n'aime apprendre un prix après avoir dit oui.
 *
 * Le montant apparaît donc au moment du choix, pas après, et le récapitulatif
 * en haut de page se recompose en même temps.
 *
 * Deux colonnes de quartiers dès le plus petit écran : une grille de tarifs
 * se compare d'un coup d'œil, alors qu'une colonne unique se fait défiler.
 */
function LocationStep({
  salon,
  zones,
  homeOnly,
  atHome,
  zoneId,
  zoneError,
  addressError,
  addressField,
  onChangeMode,
  onChangeZone,
}: {
  salon: PublicSalon;
  zones: TravelZone[];
  homeOnly: boolean;
  atHome: boolean;
  zoneId: string | null;
  zoneError: string | null;
  addressError?: string;
  addressField: ReturnType<
    ReturnType<typeof useForm<ContactValues>>["register"]
  >;
  onChangeMode: (atHome: boolean) => void;
  onChangeZone: (id: string) => void;
}) {
  const t = useTranslations("reservation");
  const locale = useLocale();
  return (
    <div className={`${CARD} space-y-4 p-4`}>
      <p className="text-sm font-medium text-[var(--site-ink)]">
        {t("lieu.question")}
      </p>

      {/* Une prestation exclusivement à domicile n'ouvre pas de bascule :
          proposer un choix dont une branche est impossible fait douter du
          reste du formulaire. */}
      {!homeOnly && (
        <div
          role="radiogroup"
          aria-label={t("lieu.titre")}
          className="grid grid-cols-2 gap-2"
        >
          <ModeChoice
            selected={!atHome}
            icon="pin"
            label={t("lieu.auSalon")}
            hint={salon.city || t("lieu.surPlace")}
            onSelect={() => onChangeMode(false)}
          />
          <ModeChoice
            selected={atHome}
            icon="home"
            label={t("lieu.chezMoi")}
            hint={t("lieu.prestataireSeDeplace")}
            onSelect={() => onChangeMode(true)}
          />
        </div>
      )}

      {atHome && (
        <div className="space-y-4">
          {zones.length > 1 && (
            <fieldset>
              <legend className="mb-2 text-sm text-[var(--site-muted)]">
                {t("lieu.quartier")}
              </legend>
              <div className="grid grid-cols-2 gap-2">
                {zones.map((entry) => {
                  const chosen = entry.id === zoneId;
                  const free = Number(entry.fee_amount) === 0;
                  return (
                    <button
                      key={entry.id}
                      type="button"
                      role="radio"
                      aria-checked={chosen}
                      onClick={() => onChangeZone(entry.id)}
                      className={`flex min-w-0 flex-col gap-1 rounded-xl border p-3 text-left transition ${
                        chosen
                          ? "border-[var(--salon-primary)] bg-[var(--salon-primary)]/[0.07]"
                          : "border-[var(--site-line)] hover:border-[var(--salon-primary)]/50"
                      }`}
                    >
                      <span className="truncate text-sm text-[var(--site-ink)]">
                        {entry.name}
                      </span>
                      <span
                        className={`tabular text-sm font-semibold ${
                          free ? "text-emerald-600" : "text-[var(--salon-ink)]"
                        }`}
                      >
                        {free
                          ? t("lieu.offert")
                          : formatPrice(entry.fee_amount, salon.currency, locale)}
                      </span>
                    </button>
                  );
                })}
              </div>
              {zoneError && (
                <p className="mt-2 text-sm font-medium text-red-600">
                  {zoneError}
                </p>
              )}
            </fieldset>
          )}

          {/* Zone unique : on l'annonce au lieu de la faire choisir. */}
          {zones.length === 1 && (
            <p className="text-sm text-[var(--site-muted)]">
              {t("lieu.zoneDesservie", { zone: zones[0].name })} ·{" "}
              <span className="tabular font-semibold text-[var(--salon-ink)]">
                {Number(zones[0].fee_amount) === 0
                  ? t("lieu.deplacementOffertMinuscule")
                  : formatPrice(zones[0].fee_amount, salon.currency, locale)}
              </span>
            </p>
          )}

          <Field
            label={t("lieu.adresse")}
            hint={t("lieu.adresseAide")}
            error={addressError}
          >
            <input
              {...addressField}
              autoComplete="street-address"
              placeholder={t("lieu.adresseExemple")}
              className={INPUT}
            />
          </Field>
        </div>
      )}
    </div>
  );
}

function ModeChoice({
  selected,
  icon,
  label,
  hint,
  onSelect,
}: {
  selected: boolean;
  icon: "pin" | "home";
  label: string;
  hint: string;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={`flex min-w-0 items-start gap-2.5 rounded-xl border p-3 text-left transition ${
        selected
          ? "border-[var(--salon-primary)] bg-[var(--salon-primary)]/[0.07]"
          : "border-[var(--site-line)] hover:border-[var(--salon-primary)]/50"
      }`}
    >
      <SalonIcon
        name={icon}
        className={`mt-0.5 size-4 shrink-0 ${
          selected ? "text-[var(--salon-ink)]" : "text-[var(--site-subtle)]"
        }`}
      />
      <span className="min-w-0">
        <span className="block text-sm font-medium text-[var(--site-ink)]">
          {label}
        </span>
        <span className="block truncate text-xs text-[var(--site-subtle)]">
          {hint}
        </span>
      </span>
    </button>
  );
}

/* -------------------------------------------------------------------------
 * Options
 * ---------------------------------------------------------------------- */

/**
 * Ce qui s'ajoute à la prestation : longueur, mèches, retrait de l'ancienne
 * coiffure.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi cette étape vient avant le créneau
 * ---------------------------------------------------------------------------
 *
 * Parce qu'une option prend du temps, et que le temps décide du créneau. La
 * placer après reviendrait à faire choisir une heure, puis à la retirer —
 * c'est le genre de retour en arrière qui fait abandonner une réservation.
 *
 * Le total et la durée se recomposent à chaque case cochée, sous les yeux de
 * la cliente : c'est le seul moment où l'on peut encore changer d'avis sans
 * que cela coûte quelque chose.
 *
 * Aucune option n'est pré-cochée. Un supplément coché d'avance se remarque à
 * la facture, pas à l'écran.
 *
 * Deux colonnes dès le petit écran : ces cartes sont courtes, une colonne
 * unique gaspille la largeur et allonge le défilement.
 */
function OptionsStep({
  salon,
  service,
  selected,
  onToggle,
  requirements,
  basket,
  onBasket,
  currency,
  onNext,
  onBack,
}: {
  salon: PublicSalon;
  service: PublicService;
  selected: string[];
  onToggle: (id: string) => void;
  requirements: ServiceRequirement[];
  basket: Basket;
  onBasket: (basket: Basket) => void;
  currency: string;
  onNext: () => void;
  onBack: () => void;
}) {
  const t = useTranslations("reservation");
  const locale = useLocale();
  const chosen = service.options.filter((option) =>
    selected.includes(option.id),
  );

  const extraMinutes = chosen.reduce(
    (total, option) => total + option.duration_delta_minutes,
    0,
  );
  const extraPrice = chosen.reduce(
    (total, option) => total + Number(option.price_delta),
    0,
  );

  const supplies = basketTotal(requirements, basket);
  const blocking = unanswered(requirements, basket);

  const totalMinutes = service.duration_minutes + extraMinutes;
  const totalPrice = Number(service.price_amount) + extraPrice + supplies;

  return (
    <section>
      <BackLink onClick={onBack} />
      <h1 className="mb-1.5 text-2xl font-semibold tracking-tight text-[var(--site-ink)]">
        {requirements.length > 0
          ? t("options.avantDeVenir")
          : t("options.uneOption")}
      </h1>
      <p className="mb-5 text-sm text-[var(--site-muted)]">
        {requirements.length > 0
          ? t("options.prevoir")
          : t("options.facultatif")}
      </p>

      {/* Les fournitures d'abord : elles peuvent empêcher la réservation,
          les options non. */}
      {requirements.length > 0 && (
        <div className="mb-6">
          <RequirementsStep
            requirements={requirements}
            basket={basket}
            currency={currency}
            onChange={onBasket}
          />
        </div>
      )}

      {service.options.length > 0 && requirements.length > 0 && (
        <h2 className="mb-2.5 text-sm font-semibold uppercase tracking-wide text-[var(--site-subtle)]">
          {t("options.titre")}
        </h2>
      )}

      <ul className="grid grid-cols-2 gap-2.5 sm:gap-3">
        {service.options.map((option) => {
          const active = selected.includes(option.id);
          const free = Number(option.price_delta) === 0;

          return (
            <li key={option.id}>
              <button
                type="button"
                role="checkbox"
                aria-checked={active}
                onClick={() => onToggle(option.id)}
                className={`flex size-full flex-col rounded-2xl border p-3 text-left transition sm:p-4 ${
                  active
                    ? "border-[var(--salon-primary)] bg-[var(--salon-primary)]/[0.07]"
                    : "border-[var(--site-line)] bg-[var(--site-surface)] hover:border-[var(--salon-primary)]/50"
                }`}
              >
                <span className="flex items-start justify-between gap-2">
                  <span className="min-w-0 text-sm font-medium text-[var(--site-ink)]">
                    {option.name}
                  </span>
                  {/* La coche est dessinée, pas native : une case à cocher
                      posée dans un coin se rate au doigt, alors que toute la
                      carte est cliquable. */}
                  <span
                    aria-hidden
                    className={`mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-md border transition ${
                      active
                        ? "border-[var(--salon-primary)] bg-[var(--salon-primary)] text-white"
                        : "border-[var(--site-line)]"
                    }`}
                  >
                    {active && <SalonIcon name="check" className="size-3" />}
                  </span>
                </span>

                {option.description && (
                  <span className="mt-1 text-xs leading-relaxed text-[var(--site-subtle)]">
                    {option.description}
                  </span>
                )}

                <span className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 pt-0.5">
                  <span
                    className={`tabular text-sm font-semibold ${
                      free ? "text-emerald-600" : "text-[var(--salon-ink)]"
                    }`}
                  >
                    {free
                      ? t("options.inclus")
                      : `+ ${formatPrice(option.price_delta, salon.currency, locale)}`}
                  </span>
                  {option.duration_delta_minutes > 0 && (
                    <span className="tabular text-xs text-[var(--site-subtle)]">
                      + {formatDuration(option.duration_delta_minutes)}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      {/*
        Le total vivant.

        Il est collé en bas sur téléphone : avec six options, le récapitulatif
        posé en fin de liste serait hors écran au moment précis où il sert.

        La marge basse réserve sa propre hauteur : sans elle, il recouvrait la
        dernière carte de la liste, qu'on ne pouvait plus ni lire ni cocher.
      */}
      <div className="sticky bottom-3 z-10 mt-5 pb-2">
        <div
          className={`${CARD} flex flex-wrap items-center justify-between gap-3 p-3.5 backdrop-blur sm:p-4`}
        >
          <div className="min-w-0">
            <p
              aria-live="polite"
              className="flex flex-wrap items-baseline gap-x-2 text-sm"
            >
              <span className="tabular text-lg font-semibold text-[var(--site-ink)]">
                {formatPrice(String(totalPrice), salon.currency, locale)}
              </span>
              <span className="tabular text-[var(--site-muted)]">
                {" · "}
                {formatDuration(totalMinutes)}
              </span>
            </p>
            <p className="mt-0.5 text-xs text-[var(--site-subtle)]">
              {blocking.length > 0 ? (
                <span className="font-medium text-amber-600">
                  {t("options.fournituresRequises", {
                    items: blocking.map((item) => item.label).join(", "),
                  })}
                </span>
              ) : chosen.length === 0 && supplies === 0 ? (
                t("options.sansOption")
              ) : (
                [
                  chosen.length > 0 && t("options.nombre", { n: chosen.length }),
                  supplies > 0 && t("options.fournituresCompris"),
                  extraMinutes > 0 &&
                    t("options.tempsAjoute", { duration: formatDuration(extraMinutes) }),
                ]
                  .filter(Boolean)
                  .join(" · ")
              )}
            </p>
          </div>

          <button
            type="button"
            onClick={onNext}
            disabled={blocking.length > 0}
            className={`${PRIMARY} px-5 py-2.5 disabled:cursor-not-allowed disabled:opacity-60`}
          >
            {blocking.length > 0
              ? t("options.repondezCiDessus")
              : chosen.length === 0 && supplies === 0
                ? t("options.continuer")
                : t("options.choisirCreneau")}
          </button>
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------
 * Liste d'attente
 * ---------------------------------------------------------------------- */

/**
 * Demander à être rappelée quand l'agenda est plein.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi ici précisément
 * ---------------------------------------------------------------------------
 *
 * C'est le seul endroit où l'on sait avec certitude que la cliente voulait
 * réserver et n'a pas pu. Un lien « liste d'attente » posé ailleurs dans le
 * menu ne serait cliqué par personne : on ne s'inscrit pas sur une file
 * d'attente avant d'avoir constaté la file.
 *
 * Le formulaire est court — nom, téléphone, période — parce qu'il arrive
 * après une déception. Chaque champ de plus est une raison de renoncer.
 * L'e-mail reste facultatif : dans les marchés visés, le rappel se fait au
 * téléphone.
 *
 * L'inscription ne réserve rien, et le texte le dit. Laisser croire à une
 * priorité qui n'existe pas produirait des clientes qui se présentent sans
 * rendez-vous.
 */
function WaitlistForm({
  host,
  service,
  staffId,
}: {
  host: string;
  service: PublicService;
  staffId: string | null;
}) {
  const t = useTranslations("reservation");
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [note, setNote] = useState("");

  const today = new Date();
  const horizon = new Date(today);
  horizon.setDate(horizon.getDate() + HORIZON_DAYS);
  const [from, setFrom] = useState(today.toISOString().slice(0, 10));
  const [to, setTo] = useState(horizon.toISOString().slice(0, 10));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim() || !phone.trim()) return;

    setPending(true);
    setFailure(null);
    try {
      await joinWaitlist({
        host,
        payload: {
          service: service.id,
          staff_member: staffId,
          full_name: name.trim(),
          phone: phone.trim(),
          preferred_from: from,
          preferred_to: to,
          note: note.trim(),
        },
      });
      setDone(true);
    } catch (caught) {
      setFailure(
        caught instanceof ApiRequestError
          ? caught.message
          : t("erreurs.inscription"),
      );
    } finally {
      setPending(false);
    }
  }

  if (done) {
    return (
      <p
        role="status"
        className="mt-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-[var(--site-ink)]"
      >
        <span className="font-medium">{t("attente.cestNote")}</span>{" "}
        {t("attente.rappel", { phone })}
      </p>
    );
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`${PRIMARY} mt-4 px-5 py-2.5`}
      >
        {t("attente.mePrevenir")}
      </button>
    );
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="mt-4 space-y-2.5">
      {/* Deux colonnes dès le téléphone : quatre champs empilés donnent une
          impression de formulaire long, ce qui fait renoncer. */}
      <div className="grid grid-cols-2 gap-2.5">
        <label className="col-span-2 block">
          <span className="mb-1 block text-xs text-[var(--site-muted)]">
            {t("attente.votreNom")}
          </span>
          <input
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            className={INPUT}
          />
        </label>

        <label className="col-span-2 block">
          <span className="mb-1 block text-xs text-[var(--site-muted)]">
            {t("coordonnees.telephone")}
          </span>
          <input
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            type="tel"
            inputMode="tel"
            className={INPUT}
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-xs text-[var(--site-muted)]">
            {t("attente.aPartirDu")}
          </span>
          <input
            value={from}
            onChange={(event) => setFrom(event.target.value)}
            type="date"
            className={INPUT}
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-xs text-[var(--site-muted)]">
            {t("attente.jusquAu")}
          </span>
          <input
            value={to}
            onChange={(event) => setTo(event.target.value)}
            type="date"
            min={from}
            className={INPUT}
          />
        </label>

        <label className="col-span-2 block">
          <span className="mb-1 block text-xs text-[var(--site-muted)]">
            {t("attente.precision")}
          </span>
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder={t("attente.precisionExemple")}
            className={INPUT}
          />
        </label>
      </div>

      {failure && (
        <p role="alert" className="text-sm font-medium text-red-600">
          {failure}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="submit"
          disabled={pending || !name.trim() || !phone.trim()}
          className={`${PRIMARY} px-5 py-2.5 disabled:opacity-60`}
        >
          {pending ? t("coordonnees.envoi") : t("attente.inscrire")}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="px-2 py-2 text-sm text-[var(--site-muted)] transition hover:text-[var(--site-ink)]"
        >
          {t("attente.annuler")}
        </button>
      </div>

      <p className="text-xs text-[var(--site-subtle)]">
        {t("attente.avertissement")}
      </p>
    </form>
  );
}

/* -------------------------------------------------------------------------
 * Fenêtres de lecture des créneaux
 * ---------------------------------------------------------------------- */

type Horizon = "day" | "week" | "month";

const SPAN: Record<Horizon, number> = { day: 1, week: 7, month: 31 };

/**
 * Ce créneau tombe-t-il dans la fenêtre choisie ?
 *
 * La comparaison se fait sur la **date locale du salon**, pas sur l'instant
 * UTC : à Guangzhou, un créneau de 8 h du matin est la veille en UTC, et
 * « aujourd'hui » n'aurait alors pas le même sens pour la cliente et pour le
 * salon.
 */
function within(iso: string, horizon: Horizon, timeZone: string): boolean {
  const day = localDayNumber(iso, timeZone);
  const today = localDayNumber(new Date().toISOString(), timeZone);
  return day - today < SPAN[horizon];
}

function countWithin(
  days: [string, Slot[]][],
  horizon: Horizon,
  timeZone: string,
): number {
  return days.reduce(
    (total, [, slots]) =>
      total +
      (within(slots[0].starts_at, horizon, timeZone) ? slots.length : 0),
    0,
  );
}

/** Numéro de jour absolu dans le fuseau du salon, pour comparer sans heure. */
function localDayNumber(iso: string, timeZone: string): number {
  const parts = new Intl.DateTimeFormat("fr-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(iso));
  return Math.floor(Date.parse(`${parts}T00:00:00Z`) / 86_400_000);
}
