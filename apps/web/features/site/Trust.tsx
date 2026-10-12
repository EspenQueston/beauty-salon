"use client";

import { useTranslations } from "next-intl";
import Image from "next/image";
import { useState } from "react";
import { salonUrl } from "@/lib/site";
import { useHome } from "./HomeContext";
import { Reveal } from "@/features/ui/Reveal";
import { HomeSection } from "@/features/site/HomeSection";

export function References() {
  const {data} = useHome();
  const t = useTranslations("conversion.trust");
  const references = data?.references.filter(item=>item.quote);
  if(!references?.length) return null;
  return <HomeSection id="retours">
    <div><h2 className="text-2xl font-semibold text-ink sm:text-4xl">{t("title")}</h2>
    <p className="mt-3 hidden text-sm text-muted sm:block">{t("subtitle")}</p></div>
    <div className="mt-5 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
      {references.map((reference,index)=><Reveal as="figure" key={reference.slug} variant="cinema" order={index} className="home-card min-w-0 rounded-2xl border border-line bg-surface p-3 sm:p-5">
        <blockquote className="text-xs leading-relaxed text-ink [overflow-wrap:anywhere] sm:text-sm">“{reference.quote}”</blockquote>
        <figcaption className="mt-4 flex flex-col items-start gap-2 sm:mt-5 sm:flex-row sm:items-center sm:gap-3">
          {reference.portrait ? <Image unoptimized src={reference.portrait} alt={reference.author} width={44} height={44} loading="lazy" className="size-8 shrink-0 rounded-full object-cover sm:size-11" />:<span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-salon-soft text-sm font-semibold text-salon-ink sm:size-11">{reference.author.slice(0,1)}</span>}
          <div className="min-w-0 text-xs [overflow-wrap:anywhere] sm:text-sm"><p className="font-semibold text-ink">{reference.author}</p><a href={salonUrl(reference.slug)} target="_blank" rel="noopener noreferrer" className="text-salon-ink underline underline-offset-4">{reference.salon} ↗</a></div>
        </figcaption>
      </Reveal>)}
    </div>
  </HomeSection>;
}

export function Reassurance() {
  const {data} = useHome();
  const t = useTranslations("conversion.trust");
  const support=data?.support;
  return <HomeSection id="assistance">
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
      {["mobile","data","publication"].map((key,index)=><Reveal as="article" key={key} variant="cinema" order={index} className={`verre lisere halo home-card min-w-0 rounded-2xl p-4 sm:p-5 ${key==="publication"?"col-span-2":""}`}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden className="mb-4 size-6 text-salon-ink">{key==="mobile"?<><rect x="6" y="2" width="12" height="20" rx="3"/><path d="M10 18h4"/></>:key==="data"?<><path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5"/></>:<><circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/></>}</svg>
        <h3 className="text-sm font-semibold text-ink">{t(`${key}Title`)}</h3><p className="mt-2 hidden text-xs leading-relaxed text-muted sm:block sm:text-sm">{t(key)}</p>
        <details className="mt-1 sm:hidden"><summary className="min-h-11 cursor-pointer py-3 text-xs text-salon-ink">{t("details")}</summary><p className="text-xs leading-relaxed text-muted">{t(key)}</p></details>
      </Reveal>)}
      <Reveal as="article" variant="cinema" order={1} className="journey-shell relative col-span-2 overflow-hidden rounded-2xl border border-line p-5 lg:col-span-4 sm:p-7">
        <div aria-hidden className="journey-orb" />
        <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="max-w-md"><h3 className="text-lg font-semibold tracking-tight text-ink sm:text-xl">{t("supportTitle")}</h3><p className="mt-2 hidden text-sm leading-relaxed text-muted sm:block">{t("support")}</p></div>
          <div className="flex flex-wrap gap-2 text-xs font-semibold">
            {support?.email && <a href={`mailto:${support.email}`} className="flex min-h-11 items-center rounded-xl border border-line bg-surface px-4 text-ink">{t("email")}</a>}
            {support?.whatsapp && <a href={`https://wa.me/${support.whatsapp.replace(/\D/g,"")}`} target="_blank" rel="noopener noreferrer" className="flex min-h-11 items-center rounded-xl border border-line bg-surface px-4 text-ink">WhatsApp ↗</a>}
            <a href="#questions" className="flex min-h-11 items-center gap-3 rounded-xl bg-salon px-4 text-white">{t("faq")} <span aria-hidden>↗</span></a>
          </div>
        </div>
      </Reveal>
    </div>
  </HomeSection>;
}

export function SupportedCountries() {
  const {data} = useHome();
  const t=useTranslations("conversion.pricing");
  const motion=useTranslations("site");
  const [paused,setPaused]=useState(false);
  const countries=(data?.supported_countries??[{code:"CG"},{code:"CD"},{code:"CN"},{code:"BJ"},{code:"BF"},{code:"CI"},{code:"TG"},{code:"SN"},{code:"NE"}]).map(item=>t(`countries.${item.code}`));
  return <div className="country-flow relative overflow-hidden border-y border-line bg-surface/60 py-3">
    <p className="sr-only">{t("availableIn")} {countries.join(", ")}</p>
    <div aria-hidden className="country-flow-track items-center" data-arretee={paused?"":undefined}>
      {[0,1].map(copy=><div key={copy} className="country-flow-copy flex shrink-0 items-center gap-6 px-3 sm:gap-10 sm:px-5">
        <span className="text-xs uppercase tracking-wider text-muted">{t("availableIn")}</span>
        {countries.map(country=><span key={country} className="flex shrink-0 items-center gap-2 text-xs text-muted sm:text-sm"><span className="size-1.5 rounded-full bg-salon" />{country}</span>)}
      </div>)}
    </div>
    <div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-surface to-transparent" />
    <button type="button" aria-pressed={paused} aria-label={motion(paused?"territoiresReprendre":"territoiresPause")} onClick={()=>setPaused(!paused)} className="absolute right-2 top-1/2 grid size-11 -translate-y-1/2 place-items-center rounded-full border border-line bg-surface text-ink shadow-sm">
      <span aria-hidden>{paused?"▶":"Ⅱ"}</span>
    </button>
  </div>;
}
