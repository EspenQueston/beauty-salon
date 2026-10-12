import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { locale as segment } from "next/root-params";
import { adresses } from "@/i18n/adresses";
import { LANGUE_PAR_DEFAUT, estLangue } from "@/i18n/langues";
import { PLATFORM_DOMAIN } from "@/lib/site";
import { BarreAction, Progression } from "@/features/site/BarreAction";
import { ATOUTS, Fleche, QUESTIONS } from "@/features/site/contenu";
import { Journey } from "@/features/site/Journey";
import { homeFont } from "@/features/site/font";
import { HomeProvider, CreateSalonLink } from "@/features/site/HomeContext";
import { Film } from "@/features/site/Film";
import { ProductDemo } from "@/features/site/ProductDemo";
import { Pricing } from "@/features/site/Pricing";
import { References, Reassurance, SupportedCountries } from "@/features/site/Trust";
import { SiteFooter } from "@/features/site/SiteFooter";
import { SiteHeader } from "@/features/site/SiteHeader";
import { SitePreview } from "@/features/site/SitePreview";
import { Reveal } from "@/features/ui/Reveal";
import { HomeSection } from "@/features/site/HomeSection";
import { Relief } from "@/features/ui/Relief";
import { ScrollTop } from "@/features/ui/ScrollTop";

export async function generateMetadata(): Promise<Metadata> {
  const t=await getTranslations("accueil");
  const brut=await segment();
  return {title:t("titreOnglet"),description:t("description"),alternates:adresses(PLATFORM_DOMAIN,"/",estLangue(brut)?brut:LANGUE_PAR_DEFAUT)};
}

function SectionTitle({title,subtitle,eyebrow}: {title:string;subtitle:string;eyebrow?:string}) {
  return <div className="home-section-titre mb-6 max-w-2xl sm:mb-8">
    {eyebrow && <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-salon-ink">{eyebrow}</p>}
    <h2 className="text-2xl font-semibold leading-tight tracking-tight text-ink sm:text-4xl">{title}</h2>
    <p className="mt-3 hidden text-sm leading-relaxed text-muted sm:block sm:text-base">{subtitle}</p>
  </div>;
}

export default async function PlatformHome() {
  const t=await getTranslations("accueil");
  const h=await getTranslations("conversion");
  const secondHeading=h("headlineSecond");
  const keyword=h("headlineKeyword");
  const keywordAt=secondHeading.indexOf(keyword);
  return <HomeProvider><div id="haut" className={`${homeFont.variable} home-conversion min-h-svh min-w-0 bg-bg pb-24 sm:pb-0`}>
    <Progression /><SiteHeader />
    <main>
      <section id="accroche" className="relative isolate overflow-hidden px-4 pb-8 pt-28 sm:px-6 sm:pb-12 sm:pt-36">
        <div aria-hidden className="aurore"><span /><span /><span /></div>
        <div className="relative z-10 mx-auto grid max-w-7xl items-center gap-7 lg:grid-cols-2 lg:gap-10">
          <div className="min-w-0 lg:order-1">
            <p className="home-hero-entry text-xs font-semibold uppercase tracking-wider text-salon-ink">{h("audience")}</p>
            <h1 className="home-headline mt-4 max-w-2xl text-[2rem] font-extrabold leading-[1.16] tracking-tight text-ink sm:text-5xl lg:text-[3.2rem]">
              <span className="home-hero-entry block">{h("headlineFirst")}</span>
              <span className="home-hero-entry mt-1 block">{keywordAt>=0 ? <>{secondHeading.slice(0,keywordAt)}<span className="hero-highlight">{keyword}</span>{secondHeading.slice(keywordAt+keyword.length)}</> : secondHeading}</span>
            </h1>
            <p className="home-hero-entry hero-intro mt-4 max-w-xl text-sm leading-relaxed text-muted sm:mt-5 sm:text-lg"><span className="sm:hidden">{h("mobileIntro")}</span><span className="hidden sm:inline">{h("intro")}</span></p>
            <div className="mt-6 flex flex-wrap gap-3">
              <CreateSalonLink className="eclat flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-salon px-5 py-3.5 text-sm font-semibold text-white shadow-sm transition hover:brightness-110 sm:w-auto"><Fleche /></CreateSalonLink>
              <a href="#film" className="flex min-h-11 w-full items-center justify-center rounded-xl border border-line bg-surface/70 px-5 py-3 text-sm font-semibold text-ink transition hover:bg-surface-hover sm:w-auto">{h("seeFilm")}</a>
            </div>
          </div>
          <Reveal id="film" variant="cinema" order={1} className="min-w-0 scroll-mt-24 lg:order-2">
            <div className="verre halo rounded-3xl p-2 sm:p-4">
              <p className="mb-3 px-2 text-xs font-semibold uppercase tracking-wider text-salon-ink">{h("filmEyebrow")}</p>
              <Film />
            </div>
          </Reveal>
        </div>
      </section>
      <Reveal variant="cinema"><SupportedCountries /></Reveal>
      <div className="home-sections">
        <HomeSection id="apercu">
          <SectionTitle title={h("previewTitle")} subtitle={h("previewSubtitle")} eyebrow={h("previewEyebrow")} />
          <div className="verre lisere halo rounded-3xl p-4 sm:p-6"><SitePreview /></div>
        </HomeSection>
        <HomeSection id="fonctionnalites" ton="nuance">
          <SectionTitle title={t("atouts.titre")} subtitle={t("atouts.sous")} />
          <div className="grid grid-cols-2 gap-3 sm:gap-5">
            {ATOUTS.map((atout,index)=><Reveal key={atout.cle} variant="cinema" order={index} className="h-full"><Relief reflet={false} className="h-full"><article className="verre lisere halo home-card h-full rounded-2xl p-4 sm:p-6">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden className="size-6 text-salon-ink">{atout.icone}</svg>
              <h3 className="mt-3 text-sm font-semibold text-ink sm:text-lg">{t(`atouts.${atout.cle}.titre`)}</h3>
              <p className="mt-2 text-xs leading-relaxed text-muted sm:text-sm"><span className="sm:hidden">{t(`atouts.${atout.cle}.corpsMobile`)}</span><span className="hidden sm:inline">{t(`atouts.${atout.cle}.corpsCourt`)}</span></p>
            </article></Relief></Reveal>)}
          </div>
        </HomeSection>
        <HomeSection id="demonstration">
          <div className="home-demo verre lisere halo rounded-3xl p-4 sm:p-6">
          <h2 className="text-base font-semibold text-ink sm:text-xl">{h("demoTitle")}</h2>
          <div className="mt-5 grid items-start gap-5 lg:grid-cols-2">
            <Reveal variant="cinema"><ProductDemo /></Reveal>
            <ol className="hidden space-y-3 sm:block">
              {["choose","reserve","manage"].map((key,index)=><Reveal as="li" key={key} variant="cinema" order={index} className="home-card flex gap-3 rounded-2xl border border-line bg-surface p-4 sm:p-5"><span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-salon-soft text-sm font-semibold text-salon-ink">{index+1}</span><div><h3 className="text-sm font-semibold text-ink sm:text-base">{h(`demoSteps.${key}Title`)}</h3><p className="mt-1 text-sm leading-relaxed text-muted">{h(`demoSteps.${key}`)}</p></div></Reveal>)}
            </ol>
          </div>
          </div>
        </HomeSection>
        <References />
        <HomeSection id="tarifs" ton="nuance">
          <SectionTitle title={h("pricing.title")} subtitle={h("pricing.subtitle")} />
          <Pricing />
        </HomeSection>
        <HomeSection id="etapes" ton="vedette">
          <SectionTitle title={t("etapes.titre")} subtitle={t("etapes.sous")} />
          <Journey />
        </HomeSection>
        <Reassurance />
        <HomeSection id="questions" ton="nuance">
          <SectionTitle title={t("questions.titre")} subtitle={t("questions.sous")} />
          <div className="space-y-3">{QUESTIONS.map((key,index)=><Reveal key={key} variant="cinema" order={index}><details className="faq-mobile verre lisere halo home-card group rounded-2xl px-4 sm:px-6">
            <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 py-4 text-sm font-semibold text-ink [&::-webkit-details-marker]:hidden sm:text-base"><span className="flex items-center gap-3"><span aria-hidden className="text-xs text-salon-ink/70">0{index+1}</span>{t(`questions.${key}.q`)}</span><span aria-hidden className="text-salon-ink transition-transform duration-300 group-open:rotate-45">+</span></summary>
            <p className="pb-5 text-sm leading-relaxed text-muted">{t(`questions.${key}.a`)}</p>
          </details></Reveal>)}</div>
        </HomeSection>
        <HomeSection id="appel" className="home-callout text-center text-white">
          <h2 className="text-2xl font-semibold tracking-tight sm:text-4xl">{t("appel.titre")}</h2>
          <p className="mx-auto mt-3 hidden max-w-lg text-sm leading-relaxed text-white/90 sm:block sm:text-base">{t("appel.sous")}</p>
          <CreateSalonLink className="eclat mx-auto mt-6 flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-semibold text-salon sm:w-fit"><Fleche /></CreateSalonLink>
        </HomeSection>
      </div>
    </main>
    <Reveal variant="cinema"><SiteFooter /></Reveal>
    <div className="hidden sm:contents"><ScrollTop offset="1.5rem" /></div>
    <BarreAction apres="accroche" avant="appel" masquePar={["apercu","tarifs"]} />
  </div></HomeProvider>;
}
