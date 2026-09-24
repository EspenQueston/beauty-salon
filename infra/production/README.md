# Mise en production

Tout tient sur une machine : le serveur Hetzner CX33 (4 vCPU, 8 Go, 40 Go),
`65.21.157.38`. Docker Compose y fait tourner sept conteneurs ; seul Caddy
est expose a Internet.

```
Internet ──> caddy :80 :443 ──┬──> web :3000     Next.js — plateforme, espace pro, mini-sites
             HTTPS automatique│
                              └──> api :8000     Django — API, administration, medias
                                     │
                     worker, beat ───┤           Celery — e-mails, traductions, rappels
                                     ├──> postgres     deux roles RLS
                                     └──> redis        cache, file de taches
```

| Fichier | Role |
| --- | --- |
| `compose.yml` | les sept services, leurs volumes et leurs variables |
| `Caddyfile` | HTTPS, certificats, aiguillage par nom d'hote |
| `api.Dockerfile`, `web.Dockerfile` | les deux images construites |
| `postgres/01-roles.sh` | les roles `salon_app` et `salon_admin`, a la creation de la base |
| `env.exemple` | modele de `.env` — la seule configuration a tenir |
| `scripts/preparer-serveur.sh` | une fois : Docker, mises a jour, echange, code |
| `scripts/generer-env.sh` | cree `.env` et tire tous les secrets |
| `scripts/deployer.sh` | a chaque mise en ligne |
| `scripts/sauvegarder.sh` | chaque nuit, par cron |

---

## Le domaine provisoire : sslip.io, et non Cloudflare Pages

Une adresse `*.pages.dev` ne peut pas servir cette plateforme, pour trois
raisons dont chacune suffit :

1. **Elle ne peut pas pointer vers ce serveur.** `pages.dev` appartient a
   Cloudflare, qui n'y sert que des sites heberges chez lui. On ne peut pas y
   poser d'enregistrement DNS vers `65.21.157.38`.
2. **Un salon = un sous-domaine.** La plateforme donne a chaque salon
   `<salon>.<domaine>`, plus `app.` et `api.`. Un projet Pages recoit un seul
   nom ; ses sous-noms sont reserves aux apercus de deploiement.
3. **La session est partagee entre `app.` et `api.`** par un cookie pose sur
   le domaine parent. `pages.dev` figure sur la liste des suffixes publics :
   les navigateurs refusent tout cookie partage entre ses sous-domaines.

A la place : **`65-21-157-38.sslip.io`**. Ce service gratuit, sans compte,
repond a tout nom qui contient une adresse IP par cette adresse :
`blondrose.65-21-157-38.sslip.io` arrive sur le serveur sans aucune
configuration DNS, et Caddy y obtient un vrai certificat Let's Encrypt.

Ses limites, a connaitre avant d'y inviter de vrais salons :

- **Le quota Let's Encrypt est partage** entre tous les utilisateurs de
  sslip.io (250 000 certificats par semaine). Il est rarement atteint, mais
  s'il l'etait, un nouveau salon attendrait son certificat.
- **Le domaine n'est pas a vous.** sslip.io ne figure pas sur la liste des
  suffixes publics : un autre site en `*.sslip.io` peut deposer des cookies
  que les navigateurs enverront aussi a vos sous-domaines. Django verifie
  l'origine de chaque ecriture, ce qui ferme l'attaque CSRF classique, mais
  ce n'est pas une situation a faire durer.
- **Les e-mails ne peuvent pas partir de ce domaine** : aucun enregistrement
  SPF ni DKIM n'y est possible. `DEFAULT_FROM_EMAIL` doit etre une adresse
  du compte SMTP utilise (Gmail, Zoho, Brevo…), sans quoi les messages
  finissent en indesirables.

Passer a un vrai domaine ne demande qu'une ligne : voir plus bas.

---

## Premiere mise en ligne

### 0. Pare-feu Hetzner

Dans la console Hetzner, onglet **Firewalls** du serveur : creer une regle
entrante pour **22/TCP** (SSH), **80/TCP**, **443/TCP** et **443/UDP**
(HTTP/3). Tout le reste est ferme.

Ce pare-feu s'applique hors de la machine, et c'est pourquoi on le prefere a
`ufw` : Docker contourne `ufw` pour les ports qu'il publie, si bien que la
regle ecrite n'est pas la regle appliquee. **Si le serveur heberge deja un
autre service** (il s'appelle « WhatsApp »), ajoutez aussi ses ports, sinon
il sera coupe.

### 1. Preparer la machine

```bash
ssh root@65.21.157.38
curl -fsSL https://raw.githubusercontent.com/EspenQueston/beauty-salon/main/infra/production/scripts/preparer-serveur.sh -o preparer-serveur.sh
bash preparer-serveur.sh main
```

Le script **s'arrete sans rien modifier** si les ports 80 ou 443 sont deja
occupes, et dit par quel programme. Voir « Le serveur heberge deja un site ».

### 2. Configurer

```bash
cd /opt/salon/infra/production
bash scripts/generer-env.sh      # cree .env, tire les secrets au hasard
nano .env                        # ACME_EMAIL, et les lignes EMAIL_*
bash scripts/generer-env.sh      # complete ce qui en dependait
```

Les valeurs a saisir soi-meme :

| Variable | Exemple |
| --- | --- |
| `ACME_EMAIL` | votre adresse — Let's Encrypt y previent en cas de souci |
| `EMAIL_HOST`, `EMAIL_PORT` | `smtp.gmail.com`, `587` |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | le compte et son mot de passe d'application |
| `DEFAULT_FROM_EMAIL` | `Beauty Salon <le-compte@gmail.com>` |
| `OPENAI_API_KEY` | facultatif : traduction du contenu des salons |
| `CURRENCY_API_KEY` | facultatif : changement de devise d'un catalogue |

`.env` est lisible par root seul, et n'est jamais versionne.

### 3. Deployer

```bash
bash scripts/deployer.sh
```

Construction des images (5 a 10 minutes la premiere fois), migrations,
fichiers statiques, demarrage. Le script ne rend la main que quand l'API
repond a sa sonde de sante.

### 4. Creer le compte d'administration

```bash
docker compose exec api python manage.py bootstrap_platform --email vous@exemple.com
```

Le mot de passe est demande a l'ecran, jamais passe en argument.
L'administration est a l'adresse qu'affiche `deployer.sh` —
`https://api.65-21-157-38.sslip.io/<ADMIN_PATH>` — et exige la double
authentification des la premiere connexion.

### 5. Programmer les sauvegardes

```bash
crontab -e
# puis ajouter :
30 2 * * * bash /opt/salon/infra/production/scripts/sauvegarder.sh >> /var/log/salon-sauvegarde.log 2>&1
```

La base et les medias, chaque nuit, dans `/var/backups/salon`, gardes 14
jours. Ces archives restent sur la machine : elles protegent d'une erreur,
pas de la perte du serveur. Activez aussi l'onglet **Backups** de Hetzner
(20 % du prix du serveur).

### 6. Verifier

```bash
docker compose ps                               # sept services, api « healthy »
curl -sI https://65-21-157-38.sslip.io | head -1
docker compose logs --tail 50 caddy             # certificats obtenus
```

Puis, dans un navigateur : la plateforme, l'inscription d'un salon (l'e-mail
de bienvenue doit arriver), son mini-site `https://<salon>.65-21-157-38.sslip.io`.
Un salon inscrit reste « en preparation » tant qu'il n'est pas publie depuis
l'administration.

---

## Mettre a jour

```bash
cd /opt/salon/infra/production
bash scripts/deployer.sh         # la branche courante
bash scripts/deployer.sh main    # une autre branche
```

Si la construction echoue, rien n'a ete remplace : le site reste en ligne
dans sa version precedente.

---

## Passer a un vrai domaine

Une fois le domaine achete et gere par Cloudflare (ou tout autre DNS) :

1. Deux enregistrements **A** vers `65.21.157.38` : `@` et `*`. Chez
   Cloudflare, en mode **DNS only** (nuage gris) : Caddy obtient alors ses
   certificats exactement comme avec sslip.io. Le mode proxy (nuage orange)
   demande une configuration de certificats d'origine qui n'est pas decrite
   ici.
2. Dans `.env` : `PLATFORM_DOMAIN=votre-domaine.com`.
3. `bash scripts/deployer.sh` — l'image Next est reconstruite, le domaine y est
   grave.
4. Dans l'administration, **Salons** : tout selectionner, action « Creer le
   sous-domaine plateforme manquant ». Chaque salon recoit son adresse sur le
   nouveau domaine ; les anciennes restent en base, inoffensives.

Les sessions ouvertes sont perdues (le cookie etait lie a l'ancien domaine) :
chacun se reconnecte une fois.

---

## Le serveur heberge deja un site

Si `preparer-serveur.sh` s'arrete sur les ports 80/443, un autre programme
les tient. Deux voies :

- **Il peut s'arreter ou changer de port** : faites-le, puis relancez.
- **Il doit rester sur ces ports** : Caddy devient alors le seul point
  d'entree, et sert aussi l'autre site. Ajoutez un bloc au `Caddyfile` —

  ```
  whatsapp.65-21-157-38.sslip.io {
  	reverse_proxy host.docker.internal:<port-du-service>
  }
  ```

  — avec `extra_hosts: ["host.docker.internal:host-gateway"]` sous le service
  `caddy` de `compose.yml`, et deplacez l'autre service sur un port interne.

---

## Au quotidien

Toutes les commandes se lancent depuis `/opt/salon/infra/production`.

```bash
docker compose logs -f --tail 100 api worker     # journaux
docker compose restart worker                    # redemarrer un service
docker compose exec api python manage.py shell   # console Django
docker compose exec api python manage.py reset_admin_password --email vous@exemple.com
docker compose exec api python manage.py traduire_le_contenu   # apres avoir pose OPENAI_API_KEY
```

### Restaurer une sauvegarde

```bash
docker compose stop api worker beat web
docker compose exec -T postgres pg_restore --username postgres --dbname salon \
  --clean --if-exists < /var/backups/salon/base-AAAAMMJJ-HHMMSS.dump
docker compose exec -T api sh -c 'rm -rf /app/media/* && tar -xzf - -C /app/media' \
  < /var/backups/salon/medias-AAAAMMJJ-HHMMSS.tar.gz
docker compose up -d
```

---

## Ce qui a ete adapte dans le code pour la production

Trois defauts n'existaient qu'en production, et ont ete corriges avec des
tests (`apps/api/tests/test_production_interne.py`,
`test_securite_deploiement.py`) :

- **Les photos des mini-sites.** Le serveur Next rend les pages en appelant
  l'API sur le reseau interne ; les adresses d'images sortaient en
  `http://api:8000/media/…`, injoignables pour un navigateur. `MEDIA_URL` est
  desormais absolue en production.
- **La limite de debit.** Tous les rendus de mini-site partaient de la meme
  adresse — celle du serveur Next — et partageaient un seul compteur de 120
  requetes par minute pour toute la plateforme. Le serveur de rendu se
  presente maintenant avec un jeton partage (`INTERNAL_API_TOKEN`) et n'est
  plus compte ; chaque visiteur garde sa propre limite.
- **Les certificats a la demande.** Caddy demande a l'API, avant chaque
  certificat, si le nom appartient a un salon (`/interne/certificat`) : un
  nom invente ne consomme pas le quota Let's Encrypt.
