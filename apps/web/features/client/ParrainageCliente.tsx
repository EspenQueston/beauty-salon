"use client";
import { useCallback, useEffect, useState } from "react";
import { useLocale } from "next-intl";
import { api } from "./api";
interface Reward { id: string; taux: string; plafond: string; devise: string; statut: string; expire_le: string | null; }
interface Programme { actif: boolean; code: string; lien: string; taux?: string; plafond?: string; devise?: string; validite_jours?: number; verification_requise?: boolean; recompenses?: Reward[]; filleuls?: { nom: string; statut: string; date: string }[]; }
const CARD = "min-w-0 rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] p-4 sm:p-5";
export function ParrainageCliente({ host }: { host: string }) {
  const english = useLocale() === "en";
  const [clients, setClients] = useState<Programme | null>(null);
  const [salons, setSalons] = useState<Programme | null>(null);
  const [copie, setCopie] = useState<string | null>(null);
  const [erreur, setErreur] = useState(false);
  const [chargement, setChargement] = useState(true);
  const [copieImpossible, setCopieImpossible] = useState(false);
  const charger = useCallback(async (estActif: () => boolean = () => true) => {
    const resultats = await Promise.allSettled([
      api<Programme>("/api/v1/public/client/parrainage-salon", host),
      api<Programme>("/api/v1/public/client/parrainage", host),
    ]);
    if (!estActif()) return;
    if (resultats[0].status === "fulfilled") setClients(resultats[0].value);
    if (resultats[1].status === "fulfilled") setSalons(resultats[1].value);
    setErreur(resultats.some((r) => r.status === "rejected"));
    setChargement(false);
  }, [host]);
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => charger(() => active));
    return () => { active = false; };
  }, [charger]);
  useEffect(() => {
    if (!copie) return;
    const timer = setTimeout(() => setCopie(null), 2000);
    return () => clearTimeout(timer);
  }, [copie]);
  async function copier(value: string) {
    try { await navigator.clipboard.writeText(value); setCopie(value); setCopieImpossible(false); } catch { setCopie(null); setCopieImpossible(true); }
  }
  const statuts: Record<string, string> = english
    ? { en_attente: "Awaiting confirmation", disponible: "Available", reservee: "Reserved", utilisee: "Used", annulee: "Cancelled", expiree: "Expired", suspendue: "Under review", en_verification: "Under review", admissible: "Confirmed", non_retenu: "Not eligible" }
    : { en_attente: "En attente de confirmation", disponible: "Disponible", reservee: "Réservée", utilisee: "Utilisée", annulee: "Annulée", expiree: "Expirée", suspendue: "À vérifier", en_verification: "En vérification", admissible: "Validé", non_retenu: "Non retenu" };
  function partage(p: Programme) {
    return <div className="mt-3 space-y-3">
      <p className="select-all break-all font-mono text-lg font-semibold tracking-widest">{p.code}</p>
      <p className="select-all break-all text-xs text-[var(--site-muted)]">{p.lien}</p>
      <div className="grid grid-cols-2 gap-2">
        {[p.code, p.lien].map((value, index) => <button key={index} className="rounded-xl border border-[var(--site-line)] px-3 py-2 text-xs" onClick={() => void copier(value)}>
          {copie === value ? (english ? "Copied" : "Copié") : index === 0 ? (english ? "Copy code" : "Copier le code") : (english ? "Copy link" : "Copier le lien")}
        </button>)}
        <a className="col-span-2 rounded-xl border border-[var(--site-line)] px-3 py-2 text-center text-xs" target="_blank" rel="noopener noreferrer" href={`https://wa.me/?text=${encodeURIComponent(p.lien)}`}>WhatsApp</a>
      </div>
    </div>;
  }
  if (!chargement && !erreur && !clients?.actif && !clients?.recompenses?.length && !clients?.verification_requise && !salons?.actif) return null;
  return <section id="parrainage" className="mb-8 scroll-mt-32 lg:scroll-mt-24" aria-labelledby="parrainage-titre">
    <h2 id="parrainage-titre" className="mb-3 text-base font-semibold sm:text-lg">{english ? "Referrals" : "Parrainage"}</h2>
    {chargement && <p role="status" className="mb-3 text-xs text-[var(--site-muted)]">{english ? "Loading your referrals…" : "Chargement de vos parrainages…"}</p>}
    {erreur && <div role="status" className={`${CARD} mb-3 flex flex-wrap items-center justify-between gap-3 text-xs`}><p>{english ? "Some referral information could not be loaded." : "Certaines informations de parrainage n’ont pas pu être chargées."}</p><button className="rounded-xl border border-[var(--site-line)] px-3 py-2" disabled={chargement} onClick={() => { setChargement(true); void charger(); }}>{english ? "Retry" : "Réessayer"}</button></div>}
    {clients?.verification_requise && <p className={`${CARD} mb-3 text-xs`}>{english ? "Verify your email to activate your referral code for this salon." : "Confirmez votre adresse e-mail pour activer votre code de parrainage dans ce salon."}</p>}
    {copieImpossible && <p role="status" className="mb-3 text-xs">{english ? "Select the code or link above and copy it manually." : "Sélectionnez le code ou le lien ci-dessous pour le copier manuellement."}</p>}
    <div className="grid min-w-0 gap-3 md:grid-cols-2">
      {(clients?.actif || !!clients?.recompenses?.length) && clients && <div className={CARD}>
        <h3 className="text-sm font-semibold">{english ? "Recommend this salon" : "Recommander ce salon"}</h3>
        {clients.actif ? <>
          <p className="mt-1 text-xs leading-relaxed text-[var(--site-muted)]">{english ? `When your friend’s first booking here is confirmed, get ${Number(clients.taux)}% off your next booking at this salon.` : `À la première réservation confirmée de votre filleul ici, recevez ${Number(clients.taux)} % de réduction sur votre prochaine réservation dans ce salon.`}</p>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs"><p className="rounded-xl border border-[var(--site-line)] p-2.5">{english ? "Maximum discount" : "Réduction maximale"}<strong className="mt-1 block">{clients.plafond} {clients.devise}</strong></p><p className="rounded-xl border border-[var(--site-line)] p-2.5">{english ? "Valid after confirmation" : "Validité après confirmation"}<strong className="mt-1 block">{clients.validite_jours} {english ? "days" : "jours"}</strong></p></div>
          <details className="mt-3 text-xs leading-relaxed text-[var(--site-muted)]"><summary className="cursor-pointer">{english ? "How it works" : "Comment ça fonctionne"}</summary><p className="mt-2">{english ? "Your friend must never have booked here, including cancelled bookings. One reward is applied automatically per booking, to services and options after promotions; products and travel are excluded. Your reward stays valid if your friend cancels after confirmation. If you cancel the booking using your reward, it is restored if it has not expired." : "Votre filleul ne doit jamais avoir réservé ici, même un rendez-vous annulé. Une seule récompense s’applique automatiquement par réservation, sur la prestation et les options après promotions ; les produits et le déplacement sont exclus. La récompense est conservée si votre filleul annule après confirmation. Si vous annulez le rendez-vous utilisant votre réduction, elle est restituée si elle n’a pas expiré."}</p></details>
          {partage(clients)}
        </> : <p className="mt-2 text-xs text-[var(--site-muted)]">{english ? "New referrals are paused. Your existing rewards remain listed below under their original terms." : "Les nouveaux parrainages sont en pause. Vos récompenses existantes restent consultables ci-dessous, selon leurs conditions d’origine."}</p>}
        <h4 className="mt-4 text-xs font-semibold">{english ? "Your rewards" : "Vos récompenses"}</h4>
        {!clients.recompenses?.length && <p className="mt-2 text-xs text-[var(--site-muted)]">{english ? "No rewards yet. Share your code to invite your first friend." : "Aucune récompense pour le moment. Partagez votre code pour inviter votre premier filleul."}</p>}
        <ul className="mt-4 grid grid-cols-2 gap-2">{clients.recompenses?.map((r) => <li key={r.id} className="min-w-0 rounded-xl border border-[var(--site-line)] p-3 text-xs">
          <p className="text-base font-semibold">−{Number(r.taux)} %</p><p className="mt-1">{statuts[r.statut] ?? r.statut}</p>
          <p className="mt-1 text-[var(--site-muted)]">{english ? "Maximum" : "Plafond"} : {r.plafond} {r.devise}</p>
          {r.expire_le && <p className="mt-1 text-[var(--site-muted)]">{english ? "Expires" : "Expire le"} {new Date(r.expire_le).toLocaleDateString(english ? "en-GB" : "fr-FR")}</p>}
        </li>)}</ul>
      </div>}
      {salons?.actif && <div className={CARD}>
        <h3 className="text-sm font-semibold">{english ? "Invite a new salon" : "Inviter un nouveau salon"}</h3>
        <p className="mt-1 text-xs leading-relaxed text-[var(--site-muted)]">{english ? "Your code gives the new salon a 30-day trial instead of 14 days. Track your invitations below." : "Votre code donne 30 jours d’essai au nouveau salon, au lieu de 14. Suivez vos invitations ci-dessous."}</p>
        {partage(salons)}
        {!salons.filleuls?.length && <p className="mt-4 text-xs text-[var(--site-muted)]">{english ? "No salon invitations recorded yet." : "Aucune invitation de salon enregistrée pour le moment."}</p>}
        <ul className="mt-4 grid grid-cols-2 gap-2">{salons.filleuls?.map((f, i) => <li key={`${f.nom}-${i}`} className="min-w-0 rounded-xl border border-[var(--site-line)] p-3 text-xs">
          <p className="truncate font-medium" title={f.nom}>{f.nom}</p><p className="mt-1 text-[var(--site-muted)]">{statuts[f.statut] ?? f.statut}</p><p className="mt-1 text-[var(--site-muted)]">{new Date(f.date).toLocaleDateString(english ? "en-GB" : "fr-FR")}</p>
        </li>)}</ul>
      </div>}
    </div>
  </section>;
}
