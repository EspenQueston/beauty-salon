import { useTranslations } from "next-intl";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { PageHero } from "@/features/salon/PageHero";
import { PAGE_SLIDES, salonSlides } from "@/features/salon/slides";
import { ShareCard } from "@/features/salon/ShareCard";
import { OpeningHours } from "@/features/salon/OpeningHours";
import { SalonIcon } from "@/features/salon/icons";
import { Card, GhostLink } from "@/features/salon/ui";
import {
  contactLinks,
  mapsHref,
  serviceAreas,
  socialLinks,
} from "@/features/salon/contact";
import { Prix } from "@/features/salon/Devise";
import { Reveal } from "@/features/ui/Reveal";
import { fetchSalon } from "@/lib/salon-serveur";
import type { PublicSalon } from "@/lib/types";

type Props = { params: Promise<{ host: string }> };

/* Le titre suit la langue de l'adresse : `export const metadata` est figé
   à la compilation et ne peut pas la connaître. */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("salon.titres");
  return { title: t("infos") };
}

/**
 * Tout ce qu'il faut savoir avant de venir.
 *
 * Regroupé sur une page plutôt qu'égrené en bas de l'accueil : ce sont les
 * informations qu'on revient chercher, souvent depuis un lien enregistré, et
 * qui doivent donc avoir une adresse à elles.
 */
export default async function InfosPage({ params }: Props) {
  const t = await getTranslations("salon");
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
  const nextDelay = () => step++ * 70;

  return (
    <>
      <PageHero
        slides={salonSlides(salon, PAGE_SLIDES)}
        eyebrow={t("pages.infosSurtitre")}
        title={t("pages.infosTitre")}
        icon="pin"
        tone="infos"
      />

      <main className="mx-auto max-w-5xl px-4 pt-10">
        <div className="grid gap-5 lg:grid-cols-2">
          <Reveal delay={nextDelay()} className="h-full">
            <Card className="lift h-full">
              <Head icon="pin" title={t("pages.ouNousSommes")} />
              {salon.address || salon.city ? (
                <>
                  <p className="text-[var(--site-muted)]">
                    {salon.address}
                    {salon.address && salon.city && <br />}
                    {salon.city}
                  </p>
                  <p className="mt-3 text-sm text-[var(--site-subtle)]">
                    {t(`modes.${salon.service_mode}`)}
                  </p>
                  {maps && (
                    <div className="mt-5">
                      <GhostLink href={maps} external icon="arrow">
                        {t("titresAccueil.itineraire")}
                      </GhostLink>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-[var(--site-muted)]">
                  {t("pages.adresseCachee")}
                </p>
              )}
            </Card>
          </Reveal>

          {travels && (
            <Reveal delay={nextDelay()} className="h-full">
              <Card className="lift h-full">
                <Head icon="pin" title={t("pages.deplacement")} />
                <TravelCard salon={salon} areas={areas} />
              </Card>
            </Reveal>
          )}

          {salon.business_hours.length > 0 && (
            <Reveal delay={nextDelay()} className="h-full">
              <Card className="lift h-full">
                <Head icon="clock" title={t("pages.horaires")} />
                <OpeningHours
                  hours={salon.business_hours}
                  timeZone={salon.timezone}
                />
              </Card>
            </Reveal>
          )}

          {contactable && (
            <Reveal delay={nextDelay()} className="h-full">
              <Card className="lift h-full">
                <Head icon="phone" title={t("pages.nousContacter")} />

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
                      {t("pages.nousSuivre")}
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
function TravelCard({ salon, areas }: { salon: PublicSalon; areas: string[] }) {
  const t = useTranslations("salon");
  const zones = salon.travel_zones;

  if (zones.length === 0) {
    return (
      <>
        <p className="text-[var(--site-muted)]">
          {t("pages.deplacementCorps")}
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
          {t("pages.deplacementFrais")}
        </p>
      </>
    );
  }

  const free = zones.filter((zone) => Number(zone.fee_amount) === 0).length;

  return (
    <>
      <p className="text-[var(--site-muted)]">
        {t("pages.deplacementForfait")}
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
                {gratuit ? (
                  t("pages.offert")
                ) : (
                  <Prix montant={zone.fee_amount} />
                )}
              </span>
            </li>
          );
        })}
      </ul>

      {free > 0 && (
        <p className="mt-4 text-sm text-[var(--site-subtle)]">
          {t("pages.zoneGratuite", { n: free })}
        </p>
      )}
    </>
  );
}

function Head({
  icon,
  title,
}: {
  icon: "pin" | "clock" | "phone" | "calendar";
  title: string;
}) {
  return (
    <h2 className="mb-4 flex items-center gap-2.5 font-semibold text-[var(--site-ink)]">
      <span
        className="flex size-9 items-center justify-center rounded-xl"
        style={{
          background: "var(--salon-accent)",
          color: "var(--salon-ink-accent)",
        }}
      >
        <SalonIcon name={icon} className="size-4.5" />
      </span>
      {title}
    </h2>
  );
}

function CancellationCard({ salon }: { salon: PublicSalon }) {
  const t = useTranslations("salon");
  return (
    <Card className="lift h-full">
      <Head icon="calendar" title={t("pages.reservationAnnulation")} />

      {salon.cancellation_policy && (
        <p className="leading-relaxed text-[var(--site-muted)]">
          {salon.cancellation_policy}
        </p>
      )}

      <ul className="mt-4 space-y-2.5 text-sm text-[var(--site-muted)]">
        <Rule>
          {t("pages.annulationGratuite", {
            heures: salon.cancellation_deadline_hours,
          })}
        </Rule>
        {salon.min_lead_time_minutes > 0 && (
          <Rule>
            {t("pages.delaiMinimum", {
              delai: formatLeadTime(salon.min_lead_time_minutes),
            })}
          </Rule>
        )}
        <Rule>
          {t("pages.agendaOuvert", { jours: salon.max_advance_days })}
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
  const t = useTranslations("salon");
  return (
    <div className="mt-5 rounded-[var(--radius-salon)] border border-amber-500/25 bg-amber-500/[0.07] p-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-[var(--site-ink)]">
        <SalonIcon name="clock" className="size-4 text-amber-600" />
        {salon.late_tolerance_minutes > 0
          ? t("pages.retardTolere", { minutes: salon.late_tolerance_minutes })
          : t("pages.aucunRetard")}
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
