# Lancer Beauty Salon sur votre machine

Ce guide part de zéro : une machine sans rien d'installé, et se termine sur
une plateforme qui tourne, avec votre compte d'administration et votre premier
salon en ligne.

Trois choses tournent en même temps :

| Quoi | Où | Comment on l'arrête |
| --- | --- | --- |
| PostgreSQL, Redis, Mailpit | conteneurs Docker | `docker compose … down` |
| API Django | terminal n° 1 | `Ctrl + C` |
| Frontend Next.js | terminal n° 2 | `Ctrl + C` |

Gardez donc **deux terminaux ouverts** pendant que vous travaillez. Fermer un
terminal arrête le serveur qu'il fait tourner.

---

## 1. Installer les outils

| Outil | Version | Pour quoi |
| --- | --- | --- |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | à jour | base de données, cache, boîte mail de test |
| [Node.js](https://nodejs.org) | 22 ou plus | frontend |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | à jour | Python et dépendances du backend |
| [Git](https://git-scm.com) | à jour | récupérer le code |

`uv` installe Python tout seul : vous n'avez pas besoin d'installer Python
d'abord.

**Windows (PowerShell)**

```powershell
winget install Docker.DockerDesktop OpenJS.NodeJS.LTS Git.Git astral-sh.uv
```

**macOS (Homebrew)**

```bash
brew install --cask docker && brew install node git uv
```

**Linux (Debian / Ubuntu)**

```bash
sudo apt install -y nodejs npm git && curl -LsSf https://astral.sh/uv/install.sh | sh
```

Vérifiez que tout répond :

```bash
docker --version && node --version && uv --version && git --version
```

> **Docker Desktop doit être démarré**, pas seulement installé. Sous Windows et
> macOS, lancez l'application : l'icône baleine doit être fixe dans la barre
> des tâches. Tant qu'elle tourne encore, `docker compose` répondra
> « cannot connect to the Docker daemon ».

---

## 2. Récupérer le projet et le configurer

```bash
git clone <url-du-depot> beauty-salon-saas
cd beauty-salon-saas
```

Le fichier `.env` porte toute la configuration. Copiez le modèle :

**Windows (PowerShell)**

```powershell
Copy-Item .env.example .env
```

**macOS / Linux**

```bash
cp .env.example .env
```

Ouvrez `.env` et changez **une seule ligne** avant de continuer :

```
DJANGO_SECRET_KEY=remplacez-par-une-longue-chaine-aleatoire
```

Les autres valeurs conviennent en local. Les trois qui comptent :

| Variable | Défaut | Ce qu'elle décide |
| --- | --- | --- |
| `PLATFORM_DOMAIN` | `localhost` | le domaine des mini-sites |
| `WEB_PORT` | `3100` | le port du frontend |
| `API_PORT` | `8001` | le port de l'API |

Les ports 3100 et 8001 sont choisis pour ne pas heurter les 3000 et 8000, très
souvent déjà pris.

Si vous gardez ces valeurs, vous n'avez rien d'autre à configurer. Si vous les
changez, reportez-les aussi côté frontend, qui lit son propre fichier :

```bash
cp apps/web/.env.example apps/web/.env.local
```

puis ajustez-y `NEXT_PUBLIC_WEB_PORT` et `NEXT_PUBLIC_API_PORT`.

---

## 3. Démarrer la base de données

```bash
docker compose -f infra/docker-compose.yml up -d
```

Trois conteneurs démarrent : PostgreSQL, Redis et Mailpit (une fausse boîte
mail qui attrape tous les e-mails du développement, consultable sur
<http://localhost:8025>). Aucun e-mail ne part vraiment.

Vérifiez qu'ils sont sains :

```bash
docker compose -f infra/docker-compose.yml ps
```

Les trois lignes doivent afficher `healthy`. Attendez quelques secondes si ce
n'est pas encore le cas — PostgreSQL prend un instant au premier démarrage.

---

## 4. Préparer le backend

```bash
cd apps/api
uv sync
```

`uv sync` télécharge Python et toutes les dépendances dans un environnement
isolé, propre au projet. Cela prend une minute la première fois.

Créez les tables :

```bash
uv run python manage.py migrate --database=admin
```

> `--database=admin` n'est pas décoratif. Le projet utilise deux rôles
> PostgreSQL sur la même base : un rôle applicatif soumis aux politiques
> d'isolation, et un rôle propriétaire qui les contourne. Seul le second peut
> modifier le schéma. Sans cette option, la migration échoue.

Créez le catalogue des offres et votre compte d'administration :

```bash
uv run python manage.py bootstrap_platform --email vous@exemple.com
```

Le mot de passe est demandé en saisie masquée — il ne reste donc pas dans
l'historique du terminal. Il doit faire au moins 10 caractères.

Cette commande ne crée **aucune donnée de démonstration** : quatre offres
commerciales, un compte d'administration, rien d'autre. Tout ce que vous verrez
ensuite dans l'application viendra de vos propres saisies.

---

## 5. Lancer les deux serveurs

### Terminal n° 1 — API Django

```bash
cd apps/api
uv run python manage.py runserver 0.0.0.0:8001
```

Laissez-le tourner. Il se recharge tout seul quand un fichier Python change.
Test : <http://localhost:8001/health> doit répondre `{"status": "ok"}`.

### Terminal n° 2 — Frontend Next.js

```bash
cd apps/web
npm install
npm run dev -- -p 3100
```

`npm install` n'est nécessaire qu'à la première fois. Test :
<http://localhost:3100> doit afficher la page de la plateforme.

---

## 6. Créer votre premier salon

1. Ouvrez <http://app.localhost:3100/inscription>.
2. Renseignez le nom du salon, l'adresse du mini-site, votre pays et votre
   e-mail. Le formulaire vous dit en direct si l'adresse est libre.
3. Vous arrivez dans votre espace, avec un bandeau : **« Votre salon est en
   cours de validation »**.

C'est normal, et c'est voulu. Un salon fraîchement inscrit ne publie pas son
mini-site : sinon n'importe qui mettrait une page en ligne sous le domaine de
la plateforme en s'inscrivant.

Pour le publier :

1. Ouvrez <http://localhost:8001/admin> et connectez-vous avec le compte de
   l'étape 4.
2. La double authentification est demandée à la première connexion. Scannez le
   QR code avec Google Authenticator, Authy ou 1Password, puis saisissez le
   code à six chiffres. **Conservez les huit codes de secours** qui s'affichent
   ensuite : ce sont eux qui vous rendront l'accès si vous perdez le téléphone.
3. La page d'accueil affiche un panneau **« Ce qui attend une décision »** avec
   les salons à valider.
4. Ouvrez **Salons**, cochez le vôtre, choisissez l'action **« Valider et
   publier le mini-site »**, puis **Envoyer**.

Votre mini-site est en ligne sur `http://<votre-adresse>.localhost:3100`.

---

## 7. Les tâches de fond (facultatif en local)

Les e-mails de confirmation et les rappels de la veille passent par Celery.
Sans lui, la plateforme fonctionne : les réservations sont enregistrées, seuls
les envois différés n'ont pas lieu.

Si vous voulez les tester, ouvrez deux terminaux de plus.

**Sous Windows, le `--pool=solo` n'est pas facultatif.** Celery utilise par
défaut un pool de processus (`prefork`) qui repose sur des sémaphores POSIX ;
Windows ne les a pas, et les processus enfants meurent en boucle sur
`PermissionError: [WinError 5] Access is denied` sans jamais traiter une
seule tâche. Celery ne prend officiellement plus Windows en charge depuis
la version 4 — `solo` contourne le problème en exécutant les tâches dans le
processus principal.

```bash
cd apps/api && uv run celery -A config worker --pool=solo -l info
```

```bash
cd apps/api && uv run celery -A config beat -l info
```

Sous Linux et macOS, la commande sans `--pool` fonctionne et traite les
tâches en parallèle.

## Un e-mail n'arrive pas ?

Le chemin compte quatre maillons — configuration, résolution du nom,
connexion au serveur, mot de passe — et chacun échoue différemment. Cette
commande les teste dans l'ordre et s'arrête au premier qui casse :

```bash
cd apps/api && uv run python manage.py tester_emails
```

Puis, pour un envoi réel :

```bash
cd apps/api && uv run python manage.py tester_emails --envoyer vous@exemple.com
```

Les causes les plus fréquentes, dans l'ordre : le worker n'est pas lancé, le
port 465 est bloqué par le fournisseur d'accès, ou un antivirus intercepte la
connexion chiffrée.

---

## Au quotidien

**Démarrer une session de travail** — trois commandes, dans trois terminaux :

```bash
docker compose -f infra/docker-compose.yml up -d
```

```bash
cd apps/api && uv run python manage.py runserver 0.0.0.0:8001
```

```bash
cd apps/web && npm run dev -- -p 3100
```

**Tout arrêter** — `Ctrl + C` dans chaque terminal de serveur, puis :

```bash
docker compose -f infra/docker-compose.yml down
```

Vos données restent dans le volume Docker : elles sont toujours là au
redémarrage suivant. Pour repartir d'une base vide, ajoutez `-v` — mais cela
efface tout, salons compris.

---

## Reprendre la main sur l'administration

### Mot de passe oublié

La porte de secours ne dépend d'aucun envoi d'e-mail, seulement d'un accès à
la machine :

```bash
cd apps/api && uv run python manage.py reset_admin_password --email vous@exemple.com
```

### Téléphone perdu (double authentification)

```bash
cd apps/api && uv run python manage.py reset_admin_password --email vous@exemple.com --reset-mfa
```

L'appareil est supprimé ; un nouvel enrôlement sera demandé à la prochaine
connexion.

### Ajouter un second administrateur

```bash
cd apps/api && uv run python manage.py bootstrap_platform --email collegue@exemple.com --skip-plans
```

---

## Quand ça ne marche pas

**« cannot connect to the Docker daemon »**
Docker Desktop n'est pas démarré. Lancez l'application et attendez que l'icône
se stabilise.

**« port is already allocated » au `docker compose up`**
Un autre PostgreSQL occupe déjà le port 5432. Le plus simple est d'arrêter
l'autre service. Sinon, changez la publication du port dans
`infra/docker-compose.yml` (`"5433:5432"` par exemple) **et** le port des deux
URL `DATABASE_URL` / `DATABASE_ADMIN_URL` dans `.env` — les deux doivent
correspondre.

**« Error: listen EADDRINUSE :::3100 »**
Le port du frontend est pris. Lancez-le ailleurs :
`npm run dev -- -p 3200`, et mettez `WEB_PORT=3200` dans `.env`.

**« permission denied for table … » à la migration**
L'option `--database=admin` manque. Voir l'étape 4.

**Le mini-site répond 404**
Le salon n'est pas encore validé, ou son adresse est mal orthographiée.
Vérifiez son statut dans l'administration : il doit être **Actif**.

**Le mini-site s'affiche mais l'espace professionnel reste vide**
Vérifiez que l'API tourne (<http://localhost:8001/health>) et que le port dans
`.env` correspond à celui du `runserver`.

**Rien ne change après une modification du `.env`**
Les deux serveurs lisent ce fichier au démarrage. Arrêtez-les (`Ctrl + C`) et
relancez-les.

**Une page blanche sur `app.localhost:3100`**
Utilisez bien `app.localhost` et non `127.0.0.1` : la résolution du salon part
du nom d'hôte. Tous les sous-domaines de `.localhost` pointent nativement vers
votre machine, sans configuration.

---

## Vérifier que tout est sain

```bash
cd apps/api && uv run pytest -q
```

```bash
cd apps/web && npx tsc --noEmit && npm run lint && npm run build
```

La suite de tests couvre en particulier l'isolation entre salons et
l'impossibilité de réserver deux fois le même créneau. Si elle passe, le socle
tient.
