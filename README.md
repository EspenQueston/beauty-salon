# Beauty Salon

Plateforme SaaS multi-tenant de réservation pour les professionnels de la beauté.
Chaque salon dispose d'un mini-site public sur son propre sous-domaine, d'un
système de réservation en ligne et d'un espace de gestion.

Ce dépôt couvre les **phases 1 et 2** en entier, l'essentiel de la **phase 3**,
et deux points de la phase 4. Ce qui manque est listé sans détour plus bas, à
[Où en est le produit](#où-en-est-le-produit) — un README qui promet plus que
le code ne fait perdre plus de temps qu'il n'en économise.

```
localhost:3100                page de la plateforme
app.localhost:3100            espace professionnel des salons
<slug>.localhost:3100         mini-site public d'un salon
localhost:8001                API Django
localhost:8001/admin          administration plateforme (chemin réglable)
```

Les navigateurs résolvent nativement n'importe quel sous-domaine de
`.localhost` vers la boucle locale (RFC 6761) : aucun DNS à configurer, aucun
fichier `hosts` à modifier, et le trafic ne traverse pas un éventuel proxy
local. Les ports sont paramétrables (`WEB_PORT`, `API_PORT`) pour cohabiter
avec vos autres projets.

---

## Démarrage rapide

Prérequis : Docker Desktop **démarré**, Node 22+, [uv](https://docs.astral.sh/uv/), git.

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d
```

```bash
cd apps/api && uv sync && uv run python manage.py migrate --database=admin
```

```bash
cd apps/api && uv run python manage.py bootstrap_platform --email vous@exemple.com
```

```bash
cd apps/api && uv run python manage.py runserver 0.0.0.0:8001
```

```bash
cd apps/web && npm install && npm run dev -- -p 3100
```

Ouvrez <http://localhost:3100>, créez votre salon depuis
<http://app.localhost:3100/inscription>, puis validez-le depuis
<http://localhost:8001/admin> (action **« Valider et publier le mini-site »**).

La base ne contient **aucune donnée de démonstration** :
`bootstrap_platform` crée les quatre offres commerciales et un compte
d'administration, rien d'autre. Tout ce que vous verrez ensuite dans
l'application vient de vos propres saisies.

Le guide pas à pas — Windows, macOS, Linux — est dans
[DEMARRAGE.md](DEMARRAGE.md).

Le jour où vous avez un vrai domaine, changez `PLATFORM_DOMAIN` — rien d'autre.

### Ports

`WEB_PORT` et `API_PORT` (dans `.env`) fixent les ports. Ils valent 3100 et
8001 par défaut, choisis pour ne pas heurter les 3000/8000 souvent occupés par
d'autres projets. Le frontend déduit l'URL de l'API de l'hôte de la page :
seul le port change, ce qui garde le cookie de session limité à l'hôte et
évite les comportements erratiques de `Domain=.localhost`.

---

## Architecture

Monolithe modulaire multi-tenant. Une application Next.js, une application
Django, une base PostgreSQL partagée.

```
Visiteuse / Cliente / Salon
        |
        v
   Next.js 16          proxy.ts : hostname -> tenant -> réécriture
   mini-sites + dashboard
        |
        v
   Django 5.2 + DRF    TenantContextMiddleware : résolution + contexte
        |
   +----+----+
   |         |
   v         v
PostgreSQL  Redis      RLS + contrainte d'exclusion | cache, verrous, Celery
```

```
apps/api/    Django : logique métier, API, administration
apps/web/    Next.js : mini-sites, parcours de réservation, dashboard
infra/       docker-compose (Postgres, Redis, Mailpit) + rôles SQL
```

### Isolation des salons

Deux couches, redondantes par construction.

**Applicative.** Tout modèle appartenant à un salon hérite de
`TenantOwnedModel` (`apps/common/models.py`). Son manager par défaut filtre sur
le tenant du contexte courant et renvoie un queryset **vide** hors contexte : un
oubli produit une page vide, jamais une fuite.

**PostgreSQL (RLS).** Deux rôles sur la même base :

| Rôle | Alias Django | Usage |
| --- | --- | --- |
| `salon_app` (NOBYPASSRLS) | `default` | tout le trafic applicatif |
| `salon_admin` (BYPASSRLS, propriétaire) | `admin` | migrations, admin plateforme, tâches inter-tenants |

Chaque table métier porte une politique comparant `tenant_id` à la variable de
session `app.tenant_id`, posée par `tenant_context()` au début de chaque requête.
`FORCE ROW LEVEL SECURITY` empêche le propriétaire de la table d'y échapper.

> Les migrations s'appliquent **uniquement** via le rôle propriétaire :
> `manage.py migrate --database=admin`. Un routeur bloque les autres alias.

Les tables de routage et d'identité (`tenants`, `domains`, `users`,
`memberships`) n'ont volontairement pas de politique : elles doivent être
lisibles *avant* qu'un tenant soit résolu.

Un test parcourt tous les modèles héritant de `TenantOwnedModel` et échoue si
l'un d'eux n'a pas sa politique RLS — impossible d'ajouter un module sans
isolation par distraction.

### D'où vient le tenant

La règle tient en une phrase : **la source dépend de la route, jamais de ce que
le client affirme.**

| Route | Source du tenant |
| --- | --- |
| `/api/v1/public/…` | hostname, ou en-tête `X-Tenant-Host` posé par le serveur Next |
| `/api/v1/account/…` | aucun — inscription, mot de passe et invitation n'appartiennent à aucun salon |
| tout le reste | memberships de l'utilisateur connecté, `X-Tenant-Id` validé contre eux |

Un `X-Tenant-Host` falsifié n'a donc aucun effet sur les routes authentifiées, et
un `X-Tenant-Id` sans membership correspondant donne un 403 journalisé.

### Anti double-réservation

Une contrainte d'exclusion PostgreSQL, seule garantie fiable sous concurrence :

```sql
EXCLUDE USING gist (
  tenant_id WITH =, staff_member_id WITH =,
  tstzrange(starts_at, ends_at) WITH &&
) WHERE (status IN ('pending_payment','requested','confirmed','checked_in'))
```

Le service de réservation revalide la disponibilité dans la transaction, attrape
l'`IntegrityError` et répond 409 avec des créneaux alternatifs. Un en-tête
`Idempotency-Key` protège des double-soumissions.

### Comptes et accès

Un salon s'inscrit seul depuis `/inscription`. Il naît en statut **« en
préparation »** : son sous-domaine est réservé, mais son mini-site répond 404
tant que l'équipe plateforme ne l'a pas passé en `active` depuis l'admin. Ouvrir
les inscriptions n'ouvre donc pas la publication.

Le propriétaire invite ensuite son équipe par e-mail. Le jeton d'invitation
n'est **jamais stocké en clair** — seule son empreinte SHA-256 l'est, si bien
qu'une fuite de la base ne donne accès à aucun compte. Une personne déjà
inscrite rejoint un second salon sans créer de mot de passe : le lien reçu vaut
preuve d'identité.

La réinitialisation de mot de passe s'appuie sur le générateur de jetons de
Django : le jeton dérive du hash du mot de passe, donc changer ce dernier
invalide le lien. Le formulaire répond la même chose que l'adresse existe ou
non, pour ne pas servir d'annuaire des salons inscrits.

Un salon garde toujours au moins un propriétaire : l'API refuse de rétrograder
ou de supprimer le dernier.

### Double authentification des administrateurs

Un compte d'administration ouvre l'alias de base qui contourne les politiques
RLS : un mot de passe volé y donnerait accès aux données de **tous** les
salons. La MFA (TOTP) est donc obligatoire — un middleware ferme l'intégralité
de `/admin/` tant que la session n'est pas vérifiée, pas seulement la page
d'accueil.

Le contrôle porte sur la **session**, pas sur l'existence d'un appareil :
chaque nouvelle connexion redemande le code. Huit codes de secours à usage
unique sont remis à l'enrôlement. `PLATFORM_ADMIN_MFA_REQUIRED=False` lève
l'exigence en développement local.

### Abonnements et acomptes

Deux flux d'argent distincts : l'**abonnement** que le salon paie à la
plateforme, et l'**acompte** que la cliente verse au salon.

Aucune passerelle de paiement n'est branchée, et ce n'est pas seulement un
retard de planning : les marchés visés sont le Congo, la RDC et la Chine, et
**Stripe n'en sert aucun des trois**. Les salons paient déjà leurs
fournisseurs en Mobile Money, WeChat Pay ou Alipay. Le document de cadrage
conditionne donc l'intégration à la validation d'un partenaire par pays.

Ce qui est implémenté est l'étape 1 qu'il décrit : suivre ce qui est dû, faire
avancer les périodes, et constater les règlements encaissés hors ligne
(espèces, Mobile Money, virement).

Pour l'acompte d'une cliente, ce circuit fonctionne déjà de bout en bout — QR
du salon, capture envoyée, vérification humaine. La voie la plus courte pour
faire payer l'abonnement est de transposer ce même mécanisme à la facture,
plutôt que d'intégrer une API qui ne couvre pas les pays où le produit est
utilisé.

Une tâche quotidienne idempotente convertit les essais échus, émet les
factures des périodes écoulées et bascule en impayé les abonnements en retard.
Les numéros de facture sortent d'une séquence PostgreSQL : sous RLS, compter
les lignes existantes ne verrait pas les factures des autres salons.

### Temps et fuseaux

Tout est stocké en `timestamptz` UTC. Chaque salon porte son fuseau ; les
horaires récurrents sont saisis en heure locale et convertis via `zoneinfo`. Un
salon de Kinshasa et un de Guangzhou cohabitent dans la même base.

C'est la source de bug la plus coûteuse du produit, et la plus discrète : une
recette datée avec l'horloge du serveur tombe sur la veille pendant huit heures
par jour, et personne ne le voit avant de comparer une caisse. Toute date
métier passe donc par le fuseau **du salon**, jamais par celui de la machine
qui calcule ou qui affiche.

### Le parcours complet d'un rendez-vous

```
réserver → acompte → le salon accepte → rappel J-1 → arrivée (QR) → terminé → avis
                ↓                                ↓
        preuve de versement            annulation / déplacement
```

Chaque étape existe des deux côtés — ce que la cliente voit, ce que le salon
fait :

| Étape | Cliente | Salon |
| --- | --- | --- |
| Réserver | tunnel du mini-site, options, articles à prévoir | arrive dans l'agenda |
| Acompte | QR du salon, envoi d'une capture | vérifie et accepte, ou refuse avec un motif |
| Rappel | e-mail J-1 automatique | rien à faire |
| Arrivée | QR ou code à six caractères | scanne, ou saisit le code |
| Terminé | e-mail d'invitation à noter | marque la prestation faite |
| Avis | 5 critères + texte libre, 30 jours | les lit, ne peut ni les modifier ni les supprimer |
| Changement | annule dans la fenêtre annoncée | annule ou **déplace** vers un créneau réel |

L'acompte n'est **jamais** encaissé par la plateforme : la cliente paie le
salon directement, et le salon constate. Voir [Abonnements et
acomptes](#abonnements-et-acomptes).

### Sécurité

[SECURITY.md](SECURITY.md) dit ce qui protège aujourd'hui, la liste à cocher
avant une mise en ligne, et ce qui reste ouvert. Trois points qui ne se
devinent pas en lisant le code :

- **`config.settings.production` refuse de démarrer** si `DJANGO_SECRET_KEY`
  est absente, trop courte, ou restée à la valeur de développement. Cette clé
  ne signe pas que les sessions : les liens de réinitialisation, les jetons de
  paiement, les codes d'arrivée et les invitations à noter en dérivent tous.
- **Les médias privés ne sont pas servis par le serveur de fichiers.** Une
  preuve de versement vit sous `MEDIA_ROOT/prive/` et ne sort que par
  `/api/v1/media/<id>/fichier`, qui vérifie l'appartenance au salon. Côté
  déploiement, le `Caddyfile` de `infra/production/` répond 404 sous
  `/media/prive/`, variantes encodées comprises.
- **Les réglages sont vérifiés par des tests**, pas par une consigne :
  `tests/test_securite_deploiement.py` charge le module de production comme le
  ferait un déploiement. Un drapeau qui repasse à `False` échoue avant la mise
  en ligne.

---

## Commandes

```bash
cd apps/api && uv run pytest -q
```

```bash
cd apps/api && uv run ruff check --fix .
```

```bash
cd apps/api && uv run python manage.py migrate --database=admin
```

```bash
cd apps/api && uv run celery -A config worker --pool=solo -l info
```

```bash
cd apps/api && uv run celery -A config beat -l info
```

```bash
cd apps/web && npm run dev -- -p 3100
```

```bash
cd apps/web && npx tsc --noEmit && npm run lint && npm run build
```

Mailpit capture tous les e-mails de développement : <http://localhost:8025>.

### Avant une mise en ligne

```bash
cd apps/api && DJANGO_SETTINGS_MODULE=config.settings.production uv run python manage.py check --deploy
```

**À lancer avec l'environnement de production.** Avec le `.env` de
développement, la commande s'arrête sur `ImproperlyConfigured: DJANGO_SECRET_KEY
porte encore la valeur de developpement` — c'est le comportement voulu, et la
preuve que le garde-fou fonctionne.

Une fois les bonnes variables posées, aucun avertissement `security.*` ne doit
rester, sauf `W021` — l'inscription HSTS preload, volontairement laissée au
choix parce qu'elle est irréversible plusieurs mois.

```bash
cd apps/api && uv run pytest tests/test_securite_deploiement.py -v
```

---

## Vérifier que l'isolation tient

```bash
cd apps/api && uv run pytest tests/test_rls.py tests/test_tenant_isolation.py -v
```

Couvre : une requête SQL brute hors contexte renvoie zéro ligne ; une écriture
hors contexte est rejetée ; un salon reçoit 404 sur la réservation d'un autre ;
un `X-Tenant-Id` forgé donne 403 ; un `X-Tenant-Host` forgé est sans effet sur le
dashboard ; les notes clientes sensibles restent invisibles aux rôles non
autorisés.

```bash
cd apps/api && uv run pytest tests/test_booking_concurrency.py -v
```

Deux threads, deux connexions, le même créneau : un seul gagne.

```bash
cd apps/api && uv run pytest tests/test_media_prive.py -v
```

Une preuve de versement ne sort que par la route authentifiée : l'inconnu
n'entre pas, le salon voisin reçoit 404, et le chemin direct du fichier n'est
plus servi.

**À la main.** Inscrivez deux salons depuis `app.localhost:3100/inscription`,
validez-les dans l'administration, puis réservez sur le mini-site du premier.
Le rendez-vous doit apparaître dans son agenda — et nulle part sur le
mini-site ni dans l'espace du second.

La suite compte **570 tests**. Ils ne mesurent pas une couverture : chacun
décrit une règle du métier ou un défaut déjà rencontré, et son nom dit
laquelle.

---

## Où en est le produit

### Fait

| Phase | | |
| --- | --- | --- |
| 1–2 | Socle multi-tenant, RLS, mini-sites | catalogue, agenda, réservation publique, liste d'attente |
| 3 | Équipe et permissions | 4 rôles, invitations par e-mail, rôle vérifié sur chaque vue |
| 3 | Annulation et reprogrammation | le salon déplace vers un créneau réel ; la cliente annule dans la fenêtre qu'il publie |
| 3 | Rappels automatisés | rappel J-1, demandes d'avis, libération des créneaux impayés, cycle de facturation |
| 3 | Abonnements et factures | offres, périodes, factures numérotées, cycle quotidien idempotent |
| 3 | Acompte manuel | QR par canal, preuve, vérification humaine, fenêtre de 30 minutes |
| 3 | Rapports essentiels | accueil à douze chiffres, recettes/dépenses par catégorie, export CSV |
| 4 | Prestations à domicile | forfait par quartier, choisi par la cliente au moment de réserver |
| 4 | Avis contrôlés | rattachés à un rendez-vous honoré, 5 critères, fenêtre de 30 jours |

S'y ajoutent, hors feuille de route : la boutique du salon (articles et
fournitures à prévoir), l'arrivée par QR ou par code, et l'espace cliente
multi-salons.

### Pas fait

| | Ce qui manque exactement |
| --- | --- |
| **Paiement de l'abonnement SaaS** | Le salon ne peut pas régler sa facture. Tout le reste de la facturation existe ; il manque le geste de paiement. **C'est le seul point qui bloque le livrable de la phase 3.** |
| Passerelle de paiement | Aucune, et c'est un choix : Stripe ne sert ni le Congo, ni la RDC, ni la Chine. Voir [Abonnements et acomptes](#abonnements-et-acomptes). |
| WhatsApp Business API | Seulement des liens `wa.me`. Ni gabarits, ni webhooks. |
| Domaines personnalisés | Le modèle `Domain` porte `kind` et `verified_at`, le routage par hostname fonctionne. Manquent l'écran, la preuve de propriété et le certificat. |
| Internationalisation | Tout passe par `gettext`, mais un seul catalogue (`fr`). |
| SMS | Aucun. |
| Application mobile, marketplace | Non commencés, et conditionnés dans la feuille de route elle-même. |
| Déploiement | Sur une machine, par Docker Compose et Caddy (HTTPS automatique) : voir [`infra/production/`](infra/production/README.md). Manuel — un script à lancer sur le serveur — et non déclenché par la CI. |

### Dettes assumées

- **Notes clientes non chiffrées au repos.** `Customer.private_notes` est en
  clair ; la protection repose sur le chiffrement disque de l'hôte et le
  filtrage par rôle. Le chiffrement applicatif viendra avec la phase paiements,
  où une gestion de clés devient de toute façon nécessaire.
- **Médias en stockage local.** `django-storages` n'est pas encore branché sur
  R2/S3 ; l'abstraction est en place, seul le backend reste à configurer. Le
  jour où il le sera, les médias privés passeront par des URL signées à durée
  limitée plutôt que par la route authentifiée actuelle.
- **Une seule langue.** Tout passe par `gettext` côté Django, mais un seul
  catalogue (`fr`) existe. Ajouter une langue ne demande aucune réécriture.
- **Aucune passerelle de paiement.** Abonnements et acomptes sont suivis, les
  règlements se constatent à la main. L'intégration attend la validation d'un
  partenaire Mobile Money par pays, comme le prévoit le document.
- **Facturation sans export comptable.** Les factures existent en base et à
  l'écran, mais ne sont ni exportées en PDF ni transmises à un logiciel
  comptable.
- **Le type d'un fichier téléversé est déclaré par le navigateur.** Le contenu
  réel n'est ouvert qu'ensuite, à la génération des dérivées. La conséquence
  est bornée par `X-Content-Type-Options: nosniff`, mais une vérification par
  signature au moment du téléversement serait plus juste. Détail dans
  [SECURITY.md](SECURITY.md).
