import { browserApi } from "@/lib/api";

/** Compteur anonyme : aucune saisie, adresse, session ou identité envoyée. */
export function trackSignupStarted() {
  if (navigator.doNotTrack === "1") return;
  const language = window.location.pathname.startsWith("/en") ? "en" : "fr";
  void fetch(`${browserApi()}/api/v1/account/home/metrics`, {
    method:"POST", credentials:"omit", keepalive:true,
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({event:"signup_started",language}),
  }).catch(()=>{});
}
