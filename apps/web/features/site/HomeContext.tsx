"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import { browserApi } from "@/lib/api";
import { professionalUrl } from "@/lib/site";
import type { SessionUser } from "@/lib/dashboard";

export interface HomeCatalogue {
  trial_days: number;
  referred_trial_days: number;
  supported_countries: {code: string; name: string}[];
  countries: {code: string; name: string; currencies: {code: string; kkiapay: boolean; plans: {code: string; group: string; months: number; amount: string; max_staff: number | null}[]}[]}[];
  pro_features: string[];
  references: {salon: string; slug: string; country: string; author: string; quote: string; portrait: string; showcase: boolean}[];
  support: {email: string; whatsapp: string};
}

const HomeContext = createContext<{
  data: HomeCatalogue | null; failed: boolean; retry: () => void;
  action: {href: string; label: string; creating: boolean};
  referral: string; track: (event: string) => void;
}>({data:null,failed:false,retry:()=>{},action:{href:professionalUrl("fr","/inscription"),label:"",creating:true},referral:"",track:()=>{}});

export function HomeProvider({children}: {children: ReactNode}) {
  const locale = useLocale();
  const t = useTranslations("conversion");
  const [data, setData] = useState<HomeCatalogue | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [user, setUser] = useState<SessionUser | null>(null);
  const [referral, setReferral] = useState("");
  const recorded = useRef(new Set<string>());
  const app = professionalUrl(locale);

  function track(event: string) {
    if (navigator.doNotTrack === "1" || recorded.current.has(event)) return;
    recorded.current.add(event);
    void fetch(`${browserApi()}/api/v1/account/home/metrics`, {method:"POST",credentials:"omit",keepalive:true,
      headers:{"Content-Type":"application/json"},body:JSON.stringify({event,language:locale})}).catch(()=>{});
  }

  useEffect(() => {
    const controller = new AbortController();
    const timeout=setTimeout(()=>{setFailed(true);controller.abort()},10000);
    void fetch(`${browserApi()}/api/v1/account/home?lang=${locale}`, {credentials:"omit",signal:controller.signal})
      .then(response=>{if(!response.ok) throw new Error();return response.json() as Promise<HomeCatalogue>})
      .then(result=>{if(!controller.signal.aborted){setData(result);setFailed(false)}})
      .catch(()=>{if(!controller.signal.aborted) setFailed(true)})
      .finally(()=>clearTimeout(timeout));
    return ()=>{clearTimeout(timeout);controller.abort()};
  },[locale,attempt]);

  useEffect(() => {
    const controller = new AbortController();
    void fetch(`${browserApi()}/api/v1/account/home/session`,{credentials:"include",cache:"no-store",signal:controller.signal})
      .then(response=>response.ok?response.json():null).then(value=>{if(!controller.signal.aborted) setUser(value)}).catch(()=>{});
    const code = new URLSearchParams(window.location.search).get("parrain") ?? "";
    if (/^[A-Za-z0-9 -]{1,32}$/.test(code)) Promise.resolve().then(()=>setReferral(code));
    return ()=>controller.abort();
  },[]);

  const membership = user?.memberships.find(item=>item.role==="owner") ?? user?.memberships[0];
  const action = membership
    ? {href:app,label:t(membership.tenant.status==="pending"?"complete":"dashboard"),creating:false}
    : user?.is_platform_admin
      ? {href:app,label:t("dashboard"),creating:false}
      : {href:`${app}/inscription${referral?`?parrain=${encodeURIComponent(referral)}`:""}`,label:t("create"),creating:true};

  // Délégation : une seule mesure par action et visite, aucune saisie envoyée.
  useEffect(() => {
    const send = (event: string) => {
      if(navigator.doNotTrack==="1" || recorded.current.has(event)) return;
      recorded.current.add(event);
      void fetch(`${browserApi()}/api/v1/account/home/metrics`,{method:"POST",credentials:"omit",keepalive:true,
        headers:{"Content-Type":"application/json"},body:JSON.stringify({event,language:locale})}).catch(()=>{});
    };
    send("home_view");
    const onClick=(event: MouseEvent)=>{const element=(event.target as Element).closest<HTMLElement>("[data-home-event]");if(element?.dataset.homeEvent)send(element.dataset.homeEvent)};
    document.addEventListener("click",onClick);
    const pricing=document.getElementById("tarifs");
    const observer=typeof IntersectionObserver!=="undefined"?new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting))send("pricing_view")},{threshold:0.2}):null;
    if(pricing)observer?.observe(pricing);
    return ()=>{document.removeEventListener("click",onClick);observer?.disconnect()};
  },[locale]);

  return <HomeContext.Provider value={{data,failed,retry:()=>setAttempt(value=>value+1),action,referral,track}}>{children}</HomeContext.Provider>;
}

export const useHome = () => useContext(HomeContext);

export function CreateSalonLink({className,children,href}: {className?:string;children?:ReactNode;href?:string}) {
  const {action} = useHome();
  const t = useTranslations("conversion");
  return <a href={action.creating && href ? href : action.href} data-home-event={action.creating?"create_click":undefined} className={className}>
    {action.label || t("create")}{children}
  </a>;
}

export function TrialNote({className}: {className?:string}) {
  const t = useTranslations("conversion");
  const {data} = useHome();
  return <p className={className}>{t("trial",{days:data?.trial_days??14})}</p>;
}
