"use client";

/**
 * Coquille de l'espace professionnel.
 *
 * Barre latérale plutôt qu'une barre horizontale : à dix rubriques, une
 * rangée de liens devient illisible et se coupe sur mobile. La colonne les
 * garde toutes visibles, groupées par intention — ce qu'on ouvre chaque
 * matin, et ce qu'on règle une fois.
 *
 * Le salon actif est renvoyé au backend dans `X-Tenant-Id`. Cet en-tête
 * n'est jamais une autorisation : le serveur le recoupe avec les memberships
 * réels et répond 403 s'il ne correspond à rien.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  fetchSession,
  logout,
  type Membership,
  type SessionUser,
} from "@/lib/dashboard";
import { ToastProvider, useToast } from "@/features/ui/Toast";
import { ThemeToggle } from "@/features/ui/ThemeToggle";
import { BeautySalonBrand, BeautySalonSymbol } from "@/features/ui/BeautySalonBrand";

import { AccesProvider, AccessBanner, UpgradeButton, useAcces } from "./AccessBanner";
import type { FonctionPro } from "./abonnement";
import { Notifications } from "./Notifications";
import { LoginForm } from "./LoginForm";
import { Icon, type IconName } from "./icons";
import {
  Configurator,
  NAV_SKINS,
  applyAccent,
  setShellPrefs,
  useShellPrefs,
  type NavSkin,
} from "./Configurator";

interface DashboardContextValue {
  user: SessionUser;
  membership: Membership;
  memberships: Membership[];
  selectTenant: (tenantId: string) => void;
  reload: () => void;
}

const DashboardContext = createContext<DashboardContextValue | null>(null);

export function useDashboard(): DashboardContextValue {
  const value = useContext(DashboardContext);
  if (!value)
    throw new Error("useDashboard doit être utilisé dans DashboardShell.");
  return value;
}

interface NavItem {
  href: string;
  label: string;
  icon: IconName;
  /** Fonction Pro : un cadenas quand le salon ne l'a pas (l'écran reste
   *  ouvert, pour montrer ce qu'elle apporte ; le serveur refuse le reste). */
  fonction?: FonctionPro;
  /** Rôles qui voient la rubrique ; tous si absent. */
  roles?: string[];
}

const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Au quotidien",
    items: [
      // Le proxy réécrit `app.localhost/` en `/dashboard` : c'est donc `/`
      // que renvoie `usePathname`, et `/` que doit viser le lien.
      { href: "/", label: "Tableau de bord", icon: "grid" },
      { href: "/agenda", label: "Agenda", icon: "calendar" },
      { href: "/clientes", label: "Clientes", icon: "users" },
      { href: "/liste-attente", label: "Liste d'attente", icon: "clock" },
      { href: "/avis", label: "Avis", icon: "star" },
    ],
  },
  {
    title: "Mon salon",
    items: [
      { href: "/prestations", label: "Prestations", icon: "sparkles" },
      // La boutique suit les prestations : ce qu'elle vend sert a les
      // realiser, elle n'a pas de sens toute seule.
      { href: "/boutique", label: "Boutique", icon: "bag" },
      { href: "/prestataires", label: "Prestataires", icon: "scissors" },
      { href: "/horaires", label: "Horaires", icon: "clock" },
      { href: "/galerie", label: "Galerie", icon: "image" },
      { href: "/equipe", label: "Équipe", icon: "team" },
      { href: "/profil", label: "Profil", icon: "store" },
    ],
  },
  {
    title: "Compte",
    items: [
      { href: "/identite", label: "Identité", icon: "edit" },
      { href: "/comptes", label: "Comptes", icon: "receipt" },
      { href: "/abonnement", label: "Abonnement", icon: "receipt" },
    ],
  },
  {
    title: "Offre Pro",
    items: [
      {
        href: "/assistants",
        label: "Assistants IA",
        icon: "chat",
        fonction: "platform_assistant",
      },
      {
        href: "/apparence",
        label: "Apparence avancée",
        icon: "palette",
        fonction: "customization",
        roles: ["owner", "manager"],
      },
      {
        href: "/domaine",
        label: "Domaine perso",
        icon: "globe",
        fonction: "custom_domain",
        roles: ["owner"],
      },
    ],
  },
];

const ROLES: Record<string, string> = {
  owner: "Propriétaire",
  manager: "Gérante",
  receptionist: "Réception",
  staff: "Prestataire",
};

export function DashboardShell({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <ShellContent>{children}</ShellContent>
    </ToastProvider>
  );
}

function ShellContent({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  /*
   * Colonne repliée, sur grand écran seulement.
   *
   * Ce n'est pas un réglage de confort : sur un portable 13 pouces, l'agenda
   * en vue mois a besoin de toute la largeur, et 272 px de navigation
   * comprimeraient sept colonnes de jours en sept bandes. Repliée, la
   * colonne garde ses icônes — on continue de changer de rubrique d'un clic,
   * sans les libellés.
   *
   * Le choix ne persiste pas d'une session à l'autre : il dépend de l'écran
   * du moment et de la tâche en cours, pas d'une préférence durable.
   */
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const toast = useToast();

  /*
   * L'apparence choisie dans le panneau de réglages.
   *
   * Elle est lue ici, au sommet, parce qu'elle concerne trois choses à la
   * fois : le fond de la colonne, sa présence même, et la façon dont la
   * barre du haut se comporte au défilement. Les distribuer depuis un seul
   * endroit évite qu'une rubrique se retrouve avec une navigation claire et
   * une barre sombre.
   */
  const prefs = useShellPrefs();
  const skin = NAV_SKINS[prefs.navType];

  /*
    L'accent est posé sur `<html>`, et retiré en quittant l'espace.

    Dans un effet et non pendant le rendu : écrire dans le DOM pendant qu'on
    calcule ce qu'il doit contenir est le genre de chose qui marche jusqu'au
    jour où React rejoue le rendu.

    Le nettoyage compte autant que la pose. Sans lui, un accent choisi ici
    resterait accroché à la racine du document après une navigation vers une
    page qui n'est pas l'espace professionnel.
  */
  useEffect(() => {
    applyAccent(prefs.accent);
    return () => applyAccent("salon");
  }, [prefs.accent]);

  const reload = useCallback(() => setReloadToken((value) => value + 1), []);

  /*
    La coquille verrouille le défilement du document.

    Elle fait exactement la hauteur de la fenêtre et ne défile pas — ce sont
    la colonne et le contenu qui défilent chacun de leur côté. Mais rien
    n'empêchait le *document* de défiler par-dessus : il suffit qu'un nœud
    s'ajoute à <body>, typiquement une extension du navigateur, pour que la
    page devienne plus haute que la fenêtre. On voyait alors la colonne de
    navigation s'arrêter en plein milieu, suivie d'une large bande vide.

    L'attribut n'est posé que lorsque la coquille est réellement à l'écran :
    l'écran de connexion, lui, doit rester défilable — sur un téléphone en
    paysage, clavier ouvert, ses champs passent sous la ligne de flottaison.
  */
  const shellVisible = !loading && !!user && user.memberships.length > 0;

  useEffect(() => {
    if (!shellVisible) return;
    const root = document.documentElement;
    root.dataset.appShell = "1";
    return () => {
      delete root.dataset.appShell;
    };
  }, [shellVisible]);

  useEffect(() => {
    let cancelled = false;

    fetchSession().then((session) => {
      if (cancelled) return;
      setUser(session);
      if (session && session.memberships.length > 0) {
        setTenantId((current) => current ?? session.memberships[0].tenant.id);
      }
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  if (loading) {
    return (
      <div className="flex min-h-full items-center justify-center">
        <span className="text-sm text-muted">Chargement…</span>
      </div>
    );
  }

  if (!user) return <LoginForm onSuccess={reload} />;

  const membership =
    user.memberships.find((item) => item.tenant.id === tenantId) ??
    user.memberships[0];

  if (!membership) {
    return (
      <div className="flex min-h-full items-center justify-center p-8">
        <div className="max-w-md text-center">
          <h1 className="text-lg font-semibold text-ink">
            Aucun salon rattaché
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Votre compte existe, mais n&apos;est rattaché à aucun salon.
            Contactez l&apos;équipe Beauty Salon, ou créez le vôtre.
          </p>
          <Link
            href="/inscription"
            className="mt-5 inline-flex rounded-lg bg-salon px-4 py-2.5 text-sm font-medium text-white"
          >
            Créer mon salon
          </Link>
        </div>
      </div>
    );
  }

  /*
    La barre est construite une fois et posée à l'un ou l'autre endroit.

    Une seule instance, et non deux rendus conditionnels : la cloche qu'elle
    porte interroge le serveur au montage. Deux barres alternées la
    remonteraient à chaque bascule du réglage, et le compteur repartirait de
    zéro sous les yeux de la gérante.
  */
  const bar = (
    <TopBar
      user={user}
      membership={membership}
      collapsed={collapsed}
      sidebarHidden={prefs.sidebarHidden}
      onToggleSidebar={() => {
        // Masquée, le bouton la fait revenir plutôt que de la replier : une
        // commande qui ne fait rien de visible passe pour cassée.
        if (prefs.sidebarHidden) setShellPrefs({ sidebarHidden: false });
        else setCollapsed((value) => !value);
      }}
      onMenu={() => setMenuOpen(true)}
      onLogout={async () => {
        await logout();
        toast.info("Vous êtes déconnectée.");
        setUser(null);
      }}
    />
  );

  return (
    <DashboardContext.Provider
      value={{
        user,
        membership,
        memberships: user.memberships,
        selectTenant: setTenantId,
        reload,
      }}
    >
      {/*
        Deux zones de défilement, indépendantes.

        ---------------------------------------------------------------------
        Pourquoi ce n'est pas un détail
        ---------------------------------------------------------------------

        Avec un seul défilement, la barre latérale remonte avec la page :
        descendre dans l'agenda fait disparaître la navigation, et changer de
        rubrique demande alors de remonter d'abord. Sur un écran de portable —
        13 pouces, treize rubriques — ce trajet se fait vingt fois par jour.

        La coquille prend donc exactement la hauteur de la fenêtre et ne
        défile pas ; ce sont la colonne et le contenu qui défilent chacun de
        leur côté. La barre du haut sort du flux défilant : elle est fixe par
        construction, et non par `sticky`.

        `h-dvh` et non `h-screen` : sur mobile, `100vh` inclut la barre
        d'adresse qui se replie, ce qui coupe le bas de la page tant qu'elle
        est déployée.
      */}
      {/*
        L'accent choisi est posé ici, sur la coquille entière.

        Il ne peignait que la colonne : « Émeraude » donnait une navigation
        verte à côté d'un contenu resté rose, deux couleurs franches qui ne se
        répondaient pas. Posé à la racine de l'espace, il descend par héritage
        sur tout ce qui lit `--salon-primary` — boutons, onglets, états
        actifs — et la cohérence n'a plus à être maintenue écran par écran.

        Sur la coquille et non sur `:root` : la feuille de style garde la
        main quand le réglage vaut « Couleur du salon », et rien de ce qui
        vit hors de l'espace professionnel n'est touché.
      */}
      {/* L'accès de l'abonnement, lu une fois pour le bandeau, le bouton de
          la barre du haut et la page Abonnement. */}
      <AccesProvider tenantId={membership.tenant.id}>
        <div className="flex h-dvh overflow-hidden">
          <Sidebar
            membership={membership}
            memberships={user.memberships}
            onSelect={setTenantId}
            pathname={pathname}
            open={menuOpen}
            collapsed={collapsed}
            hidden={prefs.sidebarHidden}
            skin={skin}
            onClose={() => setMenuOpen(false)}
          />

          <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
            {/*
              La barre du haut change de place selon le réglage, et c'est bien
              un changement de place — pas une classe `sticky` qu'on ajoute.

              Fixe : elle est posée *hors* de la zone qui défile, donc elle ne
              bouge pas, sans superposition ni décalage à compenser sous elle.

              Libre : elle est le premier enfant de la zone qui défile, donc
              elle remonte avec la page et rend sa hauteur au contenu. Sur un
              portable 13 pouces en vue mois, ces 60 pixels sont une ligne de
              créneaux de plus.
            */}
            {prefs.navbarFixed && bar}

            <div className="flex-1 overflow-y-auto">
              {!prefs.navbarFixed && bar}

              {membership.tenant.status === "pending" && <PendingBanner />}
              <AccessBanner pathname={pathname} />

              <main className="mx-auto w-full max-w-6xl px-4 py-5 sm:px-6 sm:py-8 lg:px-8">
                {children}
              </main>
            </div>
          </div>
        </div>
      </AccesProvider>

      <Configurator />
    </DashboardContext.Provider>
  );
}

/**
 * Barre latérale.
 *
 * ---------------------------------------------------------------------------
 * Sombre par défaut, et pourquoi
 * ---------------------------------------------------------------------------
 *
 * Une colonne claire sur un fond de page clair oblige à chercher où finit la
 * navigation et où commence le contenu — on la borde alors d'un trait, qui
 * est l'aveu que la séparation ne se voit pas. Un fond sombre la pose d'un
 * coup d'œil, à hauteur périphérique, sans rien border. C'est donc le
 * réglage d'origine.
 *
 * Les deux autres existent parce que le choix est légitime : sur un écran
 * déjà sombre, une colonne encore plus sombre creuse un trou ; et qui gère
 * deux salons dans deux onglets a besoin de les distinguer sans lire.
 * L'habillage arrive tout fait dans `skin` — voir `NAV_SKINS`.
 *
 * ---------------------------------------------------------------------------
 * L'accent, lui, n'est pas décoratif
 * ---------------------------------------------------------------------------
 *
 * Il marque la rubrique ouverte, et rien d'autre. Un accent qui colorerait
 * aussi les rubriques inactives ne dirait plus où l'on est.
 */
function Sidebar({
  membership,
  memberships,
  onSelect,
  pathname,
  open,
  collapsed,
  hidden,
  skin,
  onClose,
}: {
  membership: Membership;
  memberships: Membership[];
  onSelect: (id: string) => void;
  pathname: string | null;
  open: boolean;
  /** Repliée aux icônes seules. Sans effet sur le tiroir mobile. */
  collapsed: boolean;
  /** Retirée de l'écran, sur grand écran seulement : sur téléphone elle
   *  reste joignable par le bouton menu, sans quoi le réglage enfermerait
   *  la gérante sur la page où elle l'a activé. */
  hidden: boolean;
  skin: NavSkin;
  onClose: () => void;
}) {
  const domain = process.env.NEXT_PUBLIC_PLATFORM_DOMAIN ?? "localhost";
  const port = process.env.NEXT_PUBLIC_WEB_PORT ?? "3100";
  const { acces } = useAcces();

  // Le repli ne concerne que la colonne fixe. Sur téléphone, la même barre
  // est un tiroir qu'on ouvre pour lire des libellés : la replier aux icônes
  // la rendrait inutile au moment précis où on la consulte.
  const tight = collapsed && !open;

  return (
    <>
      {open && (
        <button
          type="button"
          aria-label="Fermer le menu"
          onClick={onClose}
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
        />
      )}

      <aside
        // `lg:h-full` : dans la coquille à hauteur fixe, la colonne occupe
        // toute la hauteur et c'est sa zone `nav` qui défile — la marque en
        // haut et le salon actif en bas restent en place.
        //
        // Masquée, elle disparaît en `lg:` seulement : le tiroir mobile
        // continue de s'ouvrir, sinon le réglage couperait la navigation à
        // qui travaille sur téléphone.
        className={`fixed inset-y-0 left-0 z-40 flex shrink-0 flex-col transition-[transform,width] duration-300 lg:static lg:h-full lg:translate-x-0 ${
          skin.aside
        } ${tight ? "w-[17rem] lg:w-[4.75rem]" : "w-[17rem]"} ${
          open ? "translate-x-0" : "-translate-x-full"
        } ${hidden ? "lg:hidden" : ""}`}
      >
        {/* ----- L'identité du produit ----------------------------------- */}
        <div
          className={`flex items-center gap-3 py-6 ${tight ? "justify-center px-3" : "px-6"}`}
        >
          {tight ? <span role="img" aria-label="Beauty Salon"><BeautySalonSymbol className="size-10" /></span> : <BeautySalonBrand />}
        </div>

        <nav className="flex-1 overflow-y-auto px-3 pb-4">
          {NAV_GROUPS.map((group) => (
            <div key={group.title} className="mb-5 last:mb-0">
              {tight ? (
                // Un filet a la place du titre : replie, il n'y a pas la
                // place de l'ecrire, mais la coupure entre groupes reste une
                // information - elle dit que ce qui suit change de nature.
                <span
                  aria-hidden
                  className={`mx-auto mb-2 block h-px w-6 ${skin.rule}`}
                />
              ) : (
                <p className="px-4 pb-2 text-[0.66rem] font-semibold uppercase tracking-[0.12em] text-salon">
                  {group.title}
                </p>
              )}
              <ul className="space-y-0.5">
                {group.items
                  .filter((item) => !item.roles || item.roles.includes(membership.role))
                  .map((item) => {
                  const active = pathname === item.href;
                  const verrouille = Boolean(
                    item.fonction && acces && !acces.fonctions?.[item.fonction],
                  );
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        // Le tiroir mobile se referme au clic plutôt que dans
                        // un effet sur le chemin : la fermeture est un effet
                        // du geste, pas de la navigation.
                        onClick={onClose}
                        aria-current={active ? "page" : undefined}
                        // Repliée, l'infobulle native rend le libellé perdu.
                        // Ce n'est pas l'accessibilité — assurée par le texte
                        // lu par les lecteurs d'écran — mais le confort de
                        // qui hésite sur une icône.
                        title={tight ? item.label : undefined}
                        // La rubrique ouverte porte l'accent en pastille
                        // pleine : c'est le seul endroit de la colonne où la
                        // couleur veut dire quelque chose, et le blanc sur
                        // fond coloré reste lisible dans les trois
                        // habillages.
                        className={`flex items-center gap-3 rounded-xl py-2.5 text-[0.9rem] transition ${
                          tight ? "justify-center px-0" : "px-4"
                        } ${
                          active
                            ? "salon-gradient font-medium text-white shadow-sm"
                            : skin.item
                        }`}
                      >
                        <Icon
                          name={item.icon}
                          className="size-[1.15rem] shrink-0"
                        />
                        {/* Le libellé reste dans le DOM, masqué : un lecteur
                            d'écran annonce « Agenda », pas « lien ». */}
                        <span
                          className={tight ? "sr-only" : "whitespace-nowrap"}
                        >
                          {item.label}
                        </span>
                        {verrouille && !tight && (
                          <span
                            title="Offre Pro"
                            className="ml-auto inline-flex items-center gap-0.5 rounded-full border border-current/25 px-1.5 py-px text-[0.6rem] font-bold uppercase tracking-wide opacity-70"
                          >
                            <Icon name="lock" className="size-2.5" />
                            Pro
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* ----- Le salon actif, en bas ---------------------------------- */}
        <div className={`border-t ${skin.edge} ${tight ? "p-3" : "p-4"}`}>
          {tight ? (
            // Repliée, l'initiale du salon suffit : c'est le seul repère
            // dont on a besoin, et il ouvre la colonne d'un clic.
            <span
              title={membership.tenant.name}
              className={`mx-auto flex size-9 items-center justify-center rounded-xl text-sm font-semibold ${skin.chip}`}
            >
              {membership.tenant.name[0]?.toUpperCase()}
            </span>
          ) : (
            <>
              <SalonSwitcher
                membership={membership}
                memberships={memberships}
                onSelect={onSelect}
                onNavigate={onClose}
                skin={skin}
              />
              <a
                href={`http://${membership.tenant.slug}.${domain}:${port}`}
                target="_blank"
                rel="noreferrer"
                className={`mt-3 flex items-center gap-2 rounded-lg px-1 py-1 text-sm transition ${skin.link}`}
              >
                <Icon name="external" className="size-4" />
                Voir mon mini-site
              </a>
            </>
          )}
        </div>
      </aside>
    </>
  );
}

/**
 * Le salon actif, en bas de colonne.
 *
 * ---------------------------------------------------------------------------
 * Deux choses distinctes, et deux rangées
 * ---------------------------------------------------------------------------
 *
 * « Chez quel salon suis-je » et « modifier ce salon » sont deux questions
 * différentes. Les empiler dans une seule rangée cliquable obligeait à
 * choisir : soit la liste déroulante de changement de salon avalait le clic,
 * soit le lien avalait la liste.
 *
 * Le changement de salon n'apparaît donc que quand il y a plusieurs salons —
 * sur un compte qui n'en gère qu'un, ce serait une liste à un seul choix —
 * et la fiche du salon est toujours un lien.
 *
 * ---------------------------------------------------------------------------
 * Où mène le lien
 * ---------------------------------------------------------------------------
 *
 * Vers « Profil du salon » : présentation, adresse, téléphone, WhatsApp,
 * réseaux. C'est ce qu'on vient modifier neuf fois sur dix en cliquant sur
 * son propre nom, et c'est ce que voient les clientes sur le mini-site.
 */
function SalonSwitcher({
  membership,
  memberships,
  onSelect,
  onNavigate,
  skin,
}: {
  membership: Membership;
  memberships: Membership[];
  onSelect: (id: string) => void;
  /** Referme le tiroir mobile après la navigation. */
  onNavigate: () => void;
  skin: NavSkin;
}) {
  const initials = membership.tenant.name
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0] ?? "")
    .join("")
    .toUpperCase();

  return (
    <div className="space-y-2">
      {memberships.length > 1 && (
        <select
          value={membership.tenant.id}
          onChange={(event) => onSelect(event.target.value)}
          aria-label="Salon actif"
          // `text-black` sur les options : sous Windows, la liste déroulante
          // est peinte par le système sur fond clair, et un texte blanc y
          // devient invisible.
          className={`w-full cursor-pointer truncate rounded-lg border px-2.5 py-1.5 text-sm font-medium ${skin.select}`}
        >
          {memberships.map((item) => (
            <option
              key={item.tenant.id}
              value={item.tenant.id}
              className="text-black"
            >
              {item.tenant.name}
            </option>
          ))}
        </select>
      )}

      <Link
        href="/identite"
        onClick={onNavigate}
        title={`Modifier le nom et les coordonnées de ${membership.tenant.name}`}
        className={`group flex w-full items-center gap-3 rounded-xl px-1.5 py-1.5 transition ${skin.hover}`}
      >
        <span
          className={`flex size-9 shrink-0 items-center justify-center rounded-xl text-sm font-semibold ${skin.chip}`}
        >
          {initials}
        </span>

        <span className="min-w-0 flex-1 text-left">
          <span
            className={`block truncate text-sm font-semibold ${skin.strong}`}
          >
            {membership.tenant.name}
          </span>
          <span className={`block truncate text-xs ${skin.faint}`}>
            {ROLES[membership.role] ?? membership.role}
          </span>
        </span>

        {/* Le crayon n'apparaît qu'au survol : en permanence, il ferait
            concurrence au nom du salon, qui est ce qu'on vient lire. Sur
            écran tactile il n'y a pas de survol, mais la rangée entière est
            cliquable — l'icône n'est pas la cible, elle l'annonce. */}
        <Icon
          name="edit"
          className={`size-4 shrink-0 opacity-0 transition group-hover:opacity-100 ${skin.faint}`}
        />
      </Link>
    </div>
  );
}

/**
 * Barre du haut : où l'on est, ce qui attend, et qui est connectée.
 *
 * La cloche et son panneau vivent dans `features/dashboard/Notifications.tsx`.
 * Ils ont leur propre fichier parce qu'ils ont leur propre horloge — un
 * rafraîchissement suspendu dès que l'onglet passe en arrière-plan, et un
 * canal ouvert avec le service worker — et que rien de cela ne regarde la
 * coquille qui les héberge.
 */
function TopBar({
  user,
  membership,
  collapsed,
  sidebarHidden,
  onToggleSidebar,
  onMenu,
  onLogout,
}: {
  user: SessionUser;
  membership: Membership;
  collapsed: boolean;
  sidebarHidden: boolean;
  onToggleSidebar: () => void;
  onMenu: () => void;
  onLogout: () => void;
}) {
  const name = user.display_name || user.email.split("@")[0];
  const initial = (name[0] ?? "?").toUpperCase();

  return (
    // Ni `sticky` ni `fixed`, dans les deux cas : c'est la **place** de cette
    // balise dans la coquille qui décide si elle suit le défilement — hors
    // de la zone qui défile, ou dedans. Voir `ShellContent`. Une barre
    // collante aurait demandé de compenser sa hauteur sous elle, et se
    // serait superposée au bandeau de validation.
    <header className="shrink-0 border-b border-line bg-surface">
      <div className="flex items-center gap-3 px-4 py-3 sm:px-6 lg:px-8">
        {/* Téléphone : ouvre le tiroir. */}
        <button
          type="button"
          onClick={onMenu}
          aria-label="Ouvrir le menu"
          className="rounded-lg p-2 text-muted transition hover:bg-surface-hover hover:text-ink lg:hidden"
        >
          <Icon name="menu" className="size-5" />
        </button>

        {/*
          Grand écran : replie ou déplie la colonne.

          Au même endroit que le bouton du tiroir mobile — le coin haut
          gauche, contre la navigation — parce que c'est le même geste : agir
          sur la colonne. Deux boutons à deux endroits pour la même colonne
          obligeraient à retenir lequel fait quoi.
        */}
        <button
          type="button"
          onClick={onToggleSidebar}
          aria-pressed={collapsed && !sidebarHidden}
          aria-label={
            sidebarHidden
              ? "Afficher la navigation"
              : collapsed
                ? "Déplier la navigation"
                : "Replier la navigation"
          }
          title={
            sidebarHidden
              ? "Afficher la navigation"
              : collapsed
                ? "Déplier la navigation"
                : "Replier la navigation"
          }
          className="hidden rounded-lg p-2 text-muted transition hover:bg-surface-hover hover:text-ink lg:inline-flex"
        >
          {/* Masquée, l'icône change : un œil dit « la revoir », un panneau
              dit « la replier ». La même icône pour deux gestes obligerait à
              se souvenir de l'état pour deviner ce que fait le clic. */}
          <Icon
            name={sidebarHidden ? "eye" : "panel"}
            className={`size-5 transition-transform ${
              collapsed && !sidebarHidden ? "rotate-180" : ""
            }`}
          />
        </button>

        <span className="truncate text-sm font-medium text-ink lg:hidden">
          {membership.tenant.name}
        </span>

        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          {/* L'action d'abonnement du moment — choisir, passer à l'annuel,
              régler — à portée de clic depuis n'importe quel écran. */}
          <UpgradeButton />

          <ThemeToggle />

          <Notifications tenantId={membership.tenant.id} />

          {/* Le nom et le rôle ensemble : dans un salon, plusieurs personnes
              partagent le même poste, et savoir sous quel rôle on agit change
              ce qu'on a le droit de faire. */}
          <div className="flex items-center gap-2.5 rounded-xl py-1 pl-1 pr-1 sm:pl-2">
            <span
              aria-hidden
              className="salon-gradient flex size-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white"
            >
              {initial}
            </span>
            <span className="hidden min-w-0 leading-tight sm:block">
              <span className="block truncate text-sm font-medium text-ink">
                {name}
              </span>
              <span className="block truncate text-xs text-subtle">
                {ROLES[membership.role] ?? membership.role}
              </span>
            </span>
          </div>

          <button
            type="button"
            onClick={onLogout}
            aria-label="Se déconnecter"
            title="Se déconnecter"
            className="rounded-lg p-2 text-muted transition hover:bg-surface-hover hover:text-ink"
          >
            <Icon name="logout" className="size-5" />
          </button>
        </div>
      </div>
    </header>
  );
}

/**
 * Un salon en attente de validation ne publie pas son mini-site. Le dire en
 * permanence évite qu'on croie à une panne en le trouvant en 404.
 */
function PendingBanner() {
  return (
    <div className="border-b border-line bg-warning-bg px-4 py-2.5 sm:px-6 lg:px-8">
      <p className="mx-auto flex max-w-6xl items-center gap-2 text-sm text-warning">
        <Icon name="clock" className="size-4 shrink-0" />
        Votre salon est en cours de validation. Votre mini-site sera public une
        fois cette étape terminée — vous pouvez déjà tout préparer.
      </p>
    </div>
  );
}
