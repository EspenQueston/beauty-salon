"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { salonUrl } from "@/lib/site";
import { useHome } from "./HomeContext";

export function ProductDemo({compact=false}: {compact?:boolean}) {
  const t = useTranslations("conversion.demo");
  const {data,track} = useHome();
  const [step,setStep] = useState(0);
  const [service,setService] = useState("cut");
  const [slot,setSlot] = useState("10:30");
  const example = data?.references.find(reference=>reference.showcase);
  const advance = () => {setStep(value=>value+1);if(step===2)track("demo_completed")};

  return <div className={`min-w-0 rounded-3xl border border-line bg-surface shadow-card ${compact?"p-4 sm:p-5":"p-4 sm:p-6"}`}>
    <div className="flex items-center justify-between gap-3">
      <span className="rounded-full bg-salon-soft px-2.5 py-1 text-xs font-semibold text-salon-ink">{t("badge")}</span>
      <span className="text-xs text-muted">{t("step",{step:Math.min(step+1,3)})}</span>
    </div>
    <ol className="mt-4 grid grid-cols-3 gap-2 text-center text-xs font-medium">
      {["service","slot","agenda"].map((key,index)=><li key={key} className={`rounded-lg px-1 py-2 ${step>=index?"bg-salon-soft text-salon-ink":"bg-surface-muted text-muted"}`}>{t(key)}</li>)}
    </ol>
    <div className="mt-5" aria-live="polite"><div key={step} className="demo-step">
      <h3 className="text-base font-semibold text-ink sm:text-lg">{t(step===0?"chooseService":step===1?"chooseSlot":step===2?"confirm":"received")}</h3>
      {step===0 && <div className="mt-3 grid grid-cols-2 gap-2">
        {["cut","care"].map(key=><button key={key} type="button" aria-pressed={service===key} onClick={()=>setService(key)} className={`rounded-xl border p-3 text-left text-sm ${service===key?"border-salon bg-salon-soft text-salon-ink":"border-line text-ink"}`}>
          <span className="block font-semibold">{t(key)}</span><span className="mt-1 block text-xs text-muted">{t(key==="cut"?"cutDuration":"careDuration")}</span>
        </button>)}
      </div>}
      {step===1 && <><p className="mt-1 text-sm text-muted">{t("exampleDay")}</p><div className="mt-3 grid grid-cols-3 gap-2">
        {["10:30","11:30","14:00"].map(time=><button key={time} type="button" aria-pressed={slot===time} onClick={()=>setSlot(time)} className={`rounded-xl border py-3 text-sm font-semibold ${slot===time?"border-salon bg-salon-soft text-salon-ink":"border-line text-ink"}`}>{time}</button>)}
      </div></>}
      {step===2 && <div className="mt-3 rounded-xl bg-surface-muted p-4 text-sm text-ink"><p className="font-semibold">{t(service)} · {slot}</p><p className="mt-1 text-muted">{t("exampleClient")}</p></div>}
      {step===3 && <div className="mt-3 rounded-xl border border-success/30 bg-success/5 p-4 text-sm">
        <p className="font-semibold text-success">✓ {t("inAgenda")}</p>
        <div className="mt-3 flex gap-3 text-ink"><span className="font-semibold">{slot}</span><div><p>{t(service)}</p><p className="mt-1 text-xs text-muted">{t("exampleClient")}</p></div></div>
      </div>}
    </div></div>
    <button type="button" onClick={step===3?()=>setStep(0):advance} className="mt-5 w-full rounded-xl bg-salon px-4 py-3 text-sm font-semibold text-white transition hover:brightness-110">{t(step===3?"restart":step===2?"simulate":"next")}</button>
    <p className="mt-3 text-xs leading-relaxed text-muted">{t("notice")}</p>
    {example && !compact && <a href={salonUrl(example.slug)} target="_blank" rel="noopener noreferrer" className="mt-4 inline-flex min-h-11 items-center text-sm font-semibold text-salon-ink underline underline-offset-4">{t("liveExample",{name:example.salon})} ↗</a>}
  </div>;
}
