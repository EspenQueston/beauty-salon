"use client";

import { useTranslations } from "next-intl";
import { Reveal } from "@/features/ui/Reveal";

const STEPS = ["creer", "remplir", "partager"] as const;

function StepIcon({ index }: { index: number }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden className="size-6 sm:size-7">
    {index===0 ? <><path d="M3 10 12 3l9 7v10H3V10Z"/><path d="M9 20v-7h6v7"/></> : index===1 ? <><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><path d="M17.5 14v7M14 17.5h7"/></> : <><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m9 10 6-3m-6 7 6 3"/></>}
  </svg>;
}

export function Journey() {
  const t=useTranslations("accueil.etapes");
  return <ol className="simple-journey relative grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-5">
    {STEPS.map((key,index)=><Reveal as="li" key={key} variant="cinema" order={index} className={`min-w-0 ${index===2?"col-span-2 sm:col-span-1":""}`}>
      <article className="journey-card relative h-full overflow-hidden rounded-2xl border border-line bg-surface p-4 sm:rounded-3xl sm:p-6">
        <div aria-hidden className="journey-card-glow"/>
        <div className="relative flex items-center justify-between gap-2">
          <span className="journey-step-icon grid size-11 place-items-center rounded-2xl border border-salon/20 bg-salon-soft text-salon-ink sm:size-14"><StepIcon index={index}/></span>
          <span aria-hidden className="text-xs font-semibold tracking-widest text-salon-ink">0{index+1}</span>
        </div>
        <div className="relative mt-5"><h3 className="text-sm font-bold tracking-tight text-ink sm:text-lg">{t(`${key}.titre`)}</h3><p className="mt-2 text-xs leading-relaxed text-muted sm:text-sm">{t(`${key}.resume`)}</p></div>
        <span aria-hidden className="journey-card-line absolute inset-x-5 bottom-0 h-0.5 rounded-full bg-salon sm:inset-x-6"/>
      </article>
    </Reveal>)}
  </ol>;
}
