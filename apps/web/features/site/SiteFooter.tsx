/**
 * Pied de page du site de la plateforme.
 *
 * Il ne promet rien qui n'existe pas : pas de page tarifs tant que les
 * tarifs ne sont pas validés marché par marché, pas de blog tant qu'aucun
 * article n'est écrit. Un lien mort en pied de page coûte plus de confiance
 * qu'une colonne un peu courte.
 */

import { appUrl } from "@/lib/site";

const COLUMNS = [
  {
    title: "Le produit",
    links: [
      { href: "#fonctionnalites", label: "Fonctionnalités" },
      { href: "#etapes", label: "Comment ça marche" },
      { href: "#questions", label: "Questions fréquentes" },
    ],
  },
  {
    title: "Mon salon",
    links: [
      { href: `${appUrl}/inscription`, label: "Créer mon salon" },
      { href: appUrl, label: "Se connecter" },
      { href: `${appUrl}/mot-de-passe-oublie`, label: "Mot de passe oublié" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-line bg-surface">
      <div className="mx-auto max-w-5xl px-4 py-12">
        <div className="grid gap-10 sm:grid-cols-2 md:grid-cols-4">
          <div className="md:col-span-2">
            <span className="flex items-center gap-2.5">
              <span className="inline-flex size-8 items-center justify-center rounded-xl bg-salon text-sm font-semibold text-white">
                BS
              </span>
              <span className="font-semibold tracking-tight text-ink">Beauty Salon</span>
            </span>

            <p className="mt-4 max-w-xs text-sm leading-relaxed text-muted">
              La plateforme de réservation des professionnels de la beauté au
              Congo-Brazzaville, en RDC et dans la diaspora.
            </p>

            <p className="mt-4 text-sm leading-relaxed text-subtle">
              Vos clientes, vos photos, vos rendez-vous : ces données vous
              appartiennent et restent exportables.
            </p>
          </div>

          {COLUMNS.map((column) => (
            <div key={column.title}>
              <h2 className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">
                {column.title}
              </h2>
              <ul className="mt-3 space-y-2">
                {column.links.map((link) => (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      className="text-sm text-muted underline-offset-4 transition hover:text-ink hover:underline"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-6 text-sm text-subtle">
          <span>© {new Date().getFullYear()} Beauty Salon</span>
          <span>Brazzaville · Kinshasa · Guangzhou</span>
        </div>
      </div>
    </footer>
  );
}
