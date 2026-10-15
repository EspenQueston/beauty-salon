"use client";

import { useState, useSyncExternalStore } from "react";
import { useLocale, useTranslations } from "next-intl";
import { CreateSalonLink, useHome } from "./HomeContext";
import { Reveal } from "@/features/ui/Reveal";
import { countryFromTimezone } from "@/lib/locale";

const wideScreen = () => window.matchMedia("(min-width: 640px)").matches;
const subscribeScreen = (update: () => void) => {
  const query = window.matchMedia("(min-width: 640px)");
  query.addEventListener("change", update);
  return () => query.removeEventListener("change", update);
};
const serverScreen = () => false;
const noSubscription = () => () => {};
const serverCountry = () => null;

export function Pricing() {
  const t = useTranslations("conversion.pricing");
  const locale = useLocale();
  const {data,failed,retry} = useHome();
  const [countryCode,setCountry] = useState("");
  const [currencyCode,setCurrency] = useState("");
  const [months,setMonths] = useState(1);
  const desktop = useSyncExternalStore(subscribeScreen, wideScreen, serverScreen);
  const [expanded,setExpanded] = useState<Record<string,boolean>>({});
  // Le pays du visiteur (deviné par son fuseau, sans permission) s'il a des
  // tarifs ; sinon la Chine, où sont la plupart des salons ; sinon le premier
  // pays tarifé. Le choix reste visible et modifiable juste au-dessus.
  const guess = useSyncExternalStore(noSubscription, countryFromTimezone, serverCountry);
  const priced = data?.countries ?? [];
  const defaultCountry = priced.find(item=>item.code===guess)?.code ?? priced.find(item=>item.code==="CN")?.code ?? priced[0]?.code;
  const selectedCountry = countryCode || defaultCountry || data?.supported_countries[0]?.code || "CG";
  const country = data?.countries.find(item=>item.code===selectedCountry);
  const currency = country?.currencies.find(item=>item.code===currencyCode) ?? country?.currencies[0];
  const format = (amount:string) => new Intl.NumberFormat(locale,{maximumFractionDigits:2}).format(Number(amount));

  return <div className="mt-6">
    <Reveal variant="cinema" className="flex flex-wrap items-end gap-3 rounded-2xl border border-line bg-surface p-3 sm:p-4">
      <label className="min-w-0 flex-1 text-sm font-medium text-ink">{t("country")}
        <select aria-label={t("country")} value={selectedCountry} onChange={event=>{setCountry(event.target.value);setCurrency("")}} className="mt-2 w-full min-w-0 rounded-xl border border-line bg-bg px-3 py-2.5">
          {(data?.supported_countries??[{code:"CG",name:"Congo-Brazzaville"}]).map(item=><option key={item.code} value={item.code}>{t.has(`countries.${item.code}`)?t(`countries.${item.code}`):item.name}</option>)}
        </select>
      </label>
      {currency && <label className="text-sm font-medium text-ink">{t("currency")}
        <select aria-label={t("currency")} value={currency.code} onChange={event=>setCurrency(event.target.value)} className="mt-2 block rounded-xl border border-line bg-bg px-3 py-2.5">
          {country?.currencies.map(item=><option key={item.code} value={item.code}>{item.code}{item.saspay?` · ${t(item.code==="USD"?"canal.carte":"canal.mobileMoney")}`:""}</option>)}
        </select>
      </label>}
      <div className="grid w-full grid-cols-2 gap-1 rounded-xl bg-surface-muted p-1 sm:w-auto" role="group" aria-label={t("period")}>
        {[1,12].map(period=><button key={period} type="button" aria-pressed={months===period} onClick={()=>setMonths(period)} className={`rounded-lg px-4 py-2.5 text-sm font-semibold ${months===period?"bg-surface text-salon-ink shadow-sm":"text-muted"}`}>{t(period===1?"monthly":"yearly")}</button>)}
      </div>
    </Reveal>
    {failed && <div role="status" className="mt-4 rounded-xl border border-line p-4 text-sm text-muted">{t("error")} <button type="button" onClick={retry} className="ml-2 min-h-11 font-semibold text-salon-ink underline">{t("retry")}</button></div>}
    <div className="mt-4 grid grid-cols-2 gap-3 sm:gap-5">
      {["standard","pro"].map((group,index)=>{
        const plan=currency?.plans.find(item=>item.group===group && item.months===months);
        const monthly=currency?.plans.find(item=>item.group===group && item.months===1);
        const saving=plan && months===12 && monthly ? Math.round((1-Number(plan.amount)/(Number(monthly.amount)*12))*100) : 0;
        return <Reveal as="article" key={group} variant="cinema" order={index} className={`verre lisere halo home-card flex min-w-0 flex-col rounded-2xl p-3 sm:p-6 ${group==="pro"?"!border-salon/45":"border-line"}`}>
          <h3 className="text-lg font-semibold text-ink sm:text-xl">{group==="pro"?"Pro":"Standard"}</h3>
          <p className="mt-2 hidden text-xs leading-relaxed text-muted sm:block sm:text-sm">{t(`${group}Intro`)}</p>
          <div className="my-5 min-h-16">
            <p className="text-lg font-semibold tracking-tight text-ink [overflow-wrap:anywhere] sm:text-3xl">{plan?format(plan.amount):t(!data&&!failed?"loading":"unavailable")}</p>
            {plan && <p className="mt-1 text-xs font-semibold text-ink sm:text-sm">{currency?.code}</p>}
            {plan && <p className="mt-1 text-xs text-muted">{t(months===1?"perMonth":"perYear")}</p>}
            {saving>0 && <p className="mt-2 text-xs font-semibold text-success">{t("saving",{percent:saving})}</p>}
          </div>
          <details className="pricing-features flex-1" open={desktop || !!expanded[group]} onToggle={event => {
            if (!desktop) {
              const open=event.currentTarget.open;
              setExpanded(current=>current[group]===open?current:{...current,[group]:open});
            }
          }}>
          <summary className="min-h-11 cursor-pointer py-2 text-xs font-semibold text-salon-ink sm:hidden">{t("details")}</summary>
          <ul className="space-y-2 text-xs leading-relaxed text-ink sm:text-sm">
            {(group==="standard"?["site","booking","clients","export"]:["includes",...(data?.pro_features??[])]).map(key=><li key={key} className="flex gap-1.5"><span aria-hidden className="text-salon-ink">✓</span><span>{t(`features.${key}`)}</span></li>)}
            {plan?.max_staff != null && <li>{t("teamLimit",{count:plan.max_staff})}</li>}
          </ul>
          </details>
          <CreateSalonLink className="mt-5 flex min-h-11 items-center justify-center rounded-xl bg-salon px-2 py-3 text-center text-xs font-semibold text-white sm:text-sm" />
        </Reveal>;
      })}
    </div>
    {data && !country && <p className="mt-2 text-sm text-muted">{t("noCountryPrice")}</p>}
    {currency?.kkiapay && <p className="mt-3 rounded-xl bg-salon-soft p-3 text-sm text-salon-ink">{t("kkiapay")}</p>}
    {currency?.saspay && <p className="mt-3 rounded-xl bg-salon-soft p-3 text-sm text-salon-ink">{t("saspay")}</p>}
  </div>;
}
