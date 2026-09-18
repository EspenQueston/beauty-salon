import { notFound } from "next/navigation";

import { PageHero } from "@/features/salon/PageHero";
import { PAGE_SLIDES, salonSlides } from "@/features/salon/slides";
import { ShareCard } from "@/features/salon/ShareCard";
import { OpeningHours } from "@/features/salon/OpeningHours";
import { SalonIcon } from "@/features/salon/icons";
import { Card, GhostLink } from "@/features/salon/ui";
import {
  SERVICE_MODES,
  contactLinks,
  mapsHref,
  serviceAreas,
  socialLinks,
} from "@/features/salon/contact";
import { formatPrice } from "@/lib/format";
import { Reveal } from "@/features/ui/Reveal";
import { fetchSalon } from "@/lib/api";
import type { PublicSalon } from "@/lib/types";

type Props = { params: Promise<{ host: string }> };

export const metadata = { title: "Infos pratiques" };

/**
 * Tout ce qu'il faut savoir avant de venir.
 *
 * Regroupé sur une page plutôt qu'égrené en bas de l'accueil : ce sont les
 * informations qu'on revient chercher, souvent depuis un lien enregistré, et
 * qui doivent donc avoir une adresse à elles.
 */
export default async function InfosPage({ params }: Props) {
  const { host } = await params;
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  const maps = mapsHref(salon);
  const contacts = contactLinks(salon);
  const socials = socialLinks(salon);
  const areas = serviceAreas(salon);
  const travels = areas.length > 0 || salon.travel_zones.length > 0;
  const contactable = contacts.length > 0 || socials.length > 0;

  /*
   * Les cartes apparaissent en cascade, dans l'ordre où elles existent.
   *
   * Les retards étaient écrits en dur, alors que la moitié des cartes sont
   * conditionnelles : un salon sans horaires en sautait un, deux cartes
   * pouvaient partager le même. Un compteur tient l'escalier droit quelle
   * que soit la fiche.
   */
  let step = 0;
  const nextDelay = () => (step++ * 70);

  return (
    <>
      <PageHero
        slides={salonSlides(salon, PAGE_SLIDES)}
        eyebrow="Nous trouver"
        title="Infos pratiques"
        icon="pin"
        tone="infos"
      />

      <main className="mx-auto max-w-5xl px-4 pt-10">
        <div className="grid gap-5 lg:grid-cols-2">
        <Reveal delay={nextDelay()} className="h-full">
          <Card className="lift h-full">
            <Head icon="pin" title="Où nous sommes" />
            {salon.address || salon.city ? (
              <>
                <p className="text-[var(--site-muted)]">
                  {salon.address}
                  {salon.address && salon.city && <br />}
                  {salon.city}
                </p>
                <p className="mt-3 text-sm text-[var(--site-subtle)]">
                  {SERVICE_MODES[salon.service_mode]}
                </p>
                {maps && (
                  <div className="mt-5">
                    <GhostLink href={maps} external icon="arrow">
                      Voir l&apos;itinéraire
                    </GhostLink>
                  </div>
                )}
              </>
            ) : (
              <p className="text-[var(--site-muted)]">
                Adresse communiquée à la confirmation du rendez-vous.
              </p>
            )}
          </Card>
        </Reveal>

        {travels && (
          <Reveal delay={nextDelay()} className="h-full">
            <Card className="lift h-full">
              <Head icon="pin" title="Nous nous déplaçons" />
              <TravelCard salon={salon} areas={areas} />
            </Card>
          </Reveal>
        )}

        {salon.business_hours.length > 0 && (
          <Reveal delay={nextDelay()} className="h-full">
            <Card className="lift h-full">
              <Head icon="clock" title="Horaires d'ouverture" />
              <OpeningHours hours={salon.business_hours} timeZone={salon.timezone} />
            </Card>
          </Reveal>
        )}

        {contactable && (
          <Reveal delay={nextDelay()} className="h-full">
            <Card className="lift h-full">
              <Head icon="phone" title="Nous contacter" />

              <ul className="space-y-2">
                {contacts.map((contact) => (
                  <li key={contact.key}>
                    <a
                      href={contact.href}
                      {...(contact.external
                        ? { target: "_blank", rel: "noreferrer noopener" }
                        : {})}
                      className="flex items-center justify-between gap-3 rounded-lg py-1.5 text-[var(--site-muted)] transition hover:text-[var(--salon-ink)]"
                    >
                      <span className="flex items-center gap-2">
                        <SalonIcon name={contact.icon} className="size-4" />
                        {contact.label}
                      </span>
                      <span className="tabular text-sm">{contact.value}</span>
                    </a>
                  </li>
                ))}
              </ul>

              {socials.length > 0 && (
                <>
                  <p className="mt-5 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--site-subtle)]">
                    Nous suivre
                  </p>
                  <ul className="mt-3 flex flex-wrap gap-2">
                    {socials.map((social) => (
                      <li key={social.key}>
                        <a
                          href={social.href}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="inline-flex items-center gap-2 rounded-full border border-[var(--site-line)] px-3.5 py-2 text-sm font-medium text-[var(--site-muted)] transition hover:border-[var(--salon-primary)] hover:text-[var(--salon-ink)]"
                        >
                          <SalonIcon name={social.icon} className="size-4" />
                          {social.label}
                        </a>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </Card>
          </Reveal>
        )}

        <Reveal delay={nextDelay()} className="h-full">
          <CancellationCard salon={salon} />
        </Reveal>

          <Reveal delay={nextDelay()} className="lg:col-span-2">
            <ShareCard
              host={host}
              salonName={salon.name}
              socials={socials}
              wechatId={salon.wechat_id}
              wechatQr={salon.wechat_qr}
            />
          </Reveal>
        </div>
      </main>
    </>
  );
}

/**
 * Zones desservies et forfaits de trajet.
 *
 * Le montant est annoncé ici plutôt que découvert à l'arrivée : c'est la
 * seule ligne de la facture qu'une cliente ne peut pas deviner, et celle qui
 * fait le plus de litiges quand elle arrive en dernier.
 *
 * Deux colonnes dès le plus petit écran : une grille de quartiers se lit
 * comme un tableau de prix, pas comme une liste qu'on fait défiler.
 */
function TravelCard({
  salon,
  areas,
}: {
  salon: PublicSalon;
  areas: string[];
}) {
  const zones = salon.travel_zones;

  if (zones.length === 0) {
    return (
      <>
        <p className="text-[var(--site-muted)]">
          Nous intervenons à domicile dans les quartiers suivants.
        </p>
        <ul className="mt-4 flex flex-wrap gap-2">
          {areas.map((area) => (
            <li
              key={area}
              className="rounded-full border border-[var(--site-line)] px-3 py-1.5 text-sm text-[var(--site-muted)]"
            >
              {area}
            </li>
          ))}
        </ul>
        <p className="mt-4 text-sm text-[var(--site-subtle)]">
          Les frais de déplacement sont convenus avec le salon.
        </p>
      </>
    );
  }

  const free = zones.filter((zone) => Number(zone.fee_amount) === 0).length;

  return (
    <>
      <p className="text-[var(--site-muted)]">
        Forfait de déplacement, annoncé avant de réserver.
      </p>

      <ul className="mt-4 grid grid-cols-2 gap-2">
        {zones.map((zone) => {
          const gratuit = Number(zone.fee_amount) === 0;
          return (
            <li
              key={zone.id}
              className="flex min-w-0 flex-col justify-between gap-1 rounded-[var(--radius-salon)] border border-[var(--site-line)] px-3 py-2.5"
            >
              <span className="truncate text-sm text-[var(--site-ink)]">
                {zone.name}
              </span>
              <span
                className={`tabular text-sm font-semibold ${
                  gratuit ? "text-emerald-600" : "text-[var(--salon-ink)]"
                }`}
              >
                {gratuit ? "Offert" : formatPrice(zone.fee_amount, salon.currency)}
              </span>
            </li>
          );
        })}
      </ul>

      {free > 0 && (
        <p className="mt-4 text-sm text-[var(--site-subtle)]">
          {free > 1
            ? `${free} zones sont desservies sans frais.`
            : "Une zone est desservie sans frais."}
        </p>
      )}
    </>
  );
}

function Head({ icon, title }: { icon: "pin" | "clock" | "phone" | "calendar"; title: string }) {
  return (
    <h2 className="mb-4 flex items-center gap-2.5 font-semibold text-[var(--site-ink)]">
      <span
        className="flex size-9 items-center justify-center rounded-xl"
        style={{
          background: "var(--salon-accent)",
          color: "var(--salon-ink)",
        }}
      >
        <SalonIcon name={icon} className="size-4.5" />
      </span>
      {title}
    </h2>
  );
}

function CancellationCard({ salon }: { salon: PublicSalon }) {
  return (
    <Card className="lift h-full">
      <Head icon="calendar" title="Réservation et annulation" />

      {salon.cancellation_policy && (
        <p className="leading-relaxed text-[var(--site-muted)]">
          {salon.cancellation_policy}
        </p>
      )}

      <ul className="mt-4 space-y-2.5 text-sm text-[var(--site-muted)]">
        <Rule>
          Annulation gratuite jusqu&apos;à {salon.cancellation_deadline_hours} h
          avant le rendez-vous.
        </Rule>
        {salon.min_lead_time_minutes > 0 && (
          <Rule>
            Réservation possible jusqu&apos;à{" "}
            {formatLeadTime(salon.min_lead_time_minutes)} avant le créneau.
          </Rule>
        )}
        <Rule>
          Agenda ouvert sur {salon.max_advance_days} jours à l&apos;avance.
        </Rule>
      </ul>

      {/*
        La règle de retard est mise à part plutôt que fondue dans la liste.

        C'est la seule de ces règles qui coûte quelque chose à la cliente le
        jour même, et une phrase noyée dans une énumération ne se lit pas. Le
        bandeau ambre la distingue sans dramatiser : c'est un rappel, pas un
        avertissement.
      */}
      {salon.late_policy && <LateNotice salon={salon} />}
    </Card>
  );
}

function LateNotice({ salon }: { salon: PublicSalon }) {
  return (
    <div className="mt-5 rounded-[var(--radius-salon)] border border-amber-500/25 bg-amber-500/[0.07] p-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-[var(--site-ink)]">
        <SalonIcon name="clock" className="size-4 text-amber-600" />
        {salon.late_tolerance_minutes > 0
          ? `Retard toléré : ${salon.late_tolerance_minutes} minutes`
          : "Aucun retard toléré"}
      </p>
      <p className="mt-1.5 text-sm leading-relaxed text-[var(--site-muted)]">
        {salon.late_policy}
      </p>
    </div>
  );
}

function Rule({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2.5">
      <SalonIcon
        name="check"
        className="mt-0.5 size-4 shrink-0 text-[var(--salon-ink)]"
      />
      <span>{children}</span>
    </li>
  );
}

function formatLeadTime(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  return `${hours} h`;
}
