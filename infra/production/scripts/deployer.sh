#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Met en ligne la version courante, ou une branche donnee.
#
#   bash scripts/deployer.sh              # la branche deja extraite
#   bash scripts/deployer.sh main         # recupere et deploie `main`
#   bash scripts/deployer.sh --sans-git   # le code tel qu'il est sur le disque
#
# L'ordre compte, et c'est pour lui que ce script existe :
#
#   1. construire les images AVANT de toucher a ce qui tourne : une
#      construction qui echoue laisse le site en ligne tel qu'il etait ;
#   2. migrer AVANT de demarrer le nouveau code : il lit des colonnes que
#      seules les nouvelles migrations creent ;
#   3. collecter les fichiers statiques de l'administration ;
#   4. remplacer les conteneurs.
#
# Les migrations passent par l'alias `admin`, seul role proprietaire des
# tables : `migrate` sur `default` enregistrerait les migrations sans en
# appliquer une seule (la commande le refuse d'ailleurs).
# ---------------------------------------------------------------------------
set -euo pipefail

ICI="$(cd "$(dirname "$0")/.." && pwd)"
RACINE="$(cd "$ICI/../.." && pwd)"
cd "$ICI"

etape() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

if [ ! -f "$ICI/.env" ]; then
  echo "Pas de .env : lancez d'abord bash scripts/generer-env.sh" >&2
  exit 1
fi
valeur() { grep -E "^$1=" "$ICI/.env" | head -n 1 | cut -d= -f2- || true; }

# Seul sur la machine, ou derriere le proxy de Coolify (voir compose.coolify.yml).
ENTREE="$(valeur ENTREE)"
ENTREE="${ENTREE:-direct}"
fichiers=(--file "$ICI/compose.yml")
case "$ENTREE" in
  direct) ;;
  coolify)
    fichiers+=(--file "$ICI/compose.coolify.yml")
    DYNAMIQUE=/data/coolify/proxy/dynamic
    if ! docker network inspect coolify >/dev/null 2>&1 || [ ! -d "$DYNAMIQUE" ]; then
      echo "ENTREE=coolify, mais ni le reseau « coolify » ni $DYNAMIQUE n'existent." >&2
      echo "Coolify tourne-t-il sur cette machine ? Sinon : ENTREE=direct dans .env." >&2
      exit 1
    fi
    ;;
  *) echo "ENTREE doit valoir « direct » ou « coolify », pas « $ENTREE »." >&2; exit 1 ;;
esac
compose() { docker compose "${fichiers[@]}" --env-file "$ICI/.env" "$@"; }
echo "Entree : $ENTREE"

# ---------------------------------------------------------------------------
etape "Code"
# ---------------------------------------------------------------------------
if [ "${1:-}" = "--sans-git" ]; then
  echo "Code du disque, sans mise a jour."
else
  if [ -n "$(git -C "$RACINE" status --porcelain --untracked-files=no)" ]; then
    echo "Des fichiers suivis ont ete modifies sur le serveur :" >&2
    git -C "$RACINE" status --short --untracked-files=no >&2
    echo "Ils seraient ecrases. Rien n'a ete fait (--sans-git pour deployer tel quel)." >&2
    exit 1
  fi
  git -C "$RACINE" fetch --prune origin
  if [ -n "${1:-}" ]; then
    git -C "$RACINE" checkout "$1"
  fi
  git -C "$RACINE" pull --ff-only
fi
echo "Version : $(git -C "$RACINE" log -1 --format='%h %s' 2>/dev/null || echo 'inconnue')"

# Refuser une configuration incomplete avant de construire quoi que ce soit.
compose config --quiet

# ---------------------------------------------------------------------------
etape "Construction des images"
# ---------------------------------------------------------------------------
compose build --pull

# ---------------------------------------------------------------------------
etape "Base de donnees"
# ---------------------------------------------------------------------------
compose up --detach --wait postgres redis
compose run --rm --no-TTY api python manage.py migrate --database=admin --noinput

# ---------------------------------------------------------------------------
etape "Fichiers statiques"
# ---------------------------------------------------------------------------
compose run --rm --no-TTY api python manage.py collectstatic --noinput --verbosity 0

# ---------------------------------------------------------------------------
etape "Demarrage"
# ---------------------------------------------------------------------------
# `--wait` rend la main quand l'API repond a sa sonde de sante, ou echoue.
compose up --detach --remove-orphans --wait

# Le Caddyfile est monte fichier par fichier. `git pull` le remplace par un
# nouveau fichier : le conteneur, lui, garde l'ancien, et `caddy reload` relit
# l'ancien. Seul un redemarrage refait le montage — on ne le fait que si la
# configuration a vraiment change, pour ne pas couper les salons a chaque mise
# a jour. (Constate le 2026-09-25 : les en-tetes de /media/ n'etaient pas
# passes en ligne malgre le rechargement.)
caddyfile_hote="$(sha256sum "$ICI/Caddyfile" | cut -d' ' -f1)"
caddyfile_conteneur="$(compose exec -T caddy sha256sum /etc/caddy/Caddyfile </dev/null 2>/dev/null | cut -d' ' -f1 || true)"
if [ "$caddyfile_hote" != "$caddyfile_conteneur" ]; then
  echo "Caddyfile modifie : redemarrage de Caddy."
  compose restart caddy
fi
compose ps

domaine="$(valeur PLATFORM_DOMAIN)"
admin="$(valeur ADMIN_PATH)"

if [ "$ENTREE" = "coolify" ]; then
  # -------------------------------------------------------------------------
  etape "Route dans le proxy de Coolify"
  # -------------------------------------------------------------------------
  # Posee apres le demarrage : Traefik n'aiguille vers Caddy qu'une fois
  # Caddy la pour repondre. Ecriture atomique (fichier temporaire, puis
  # renommage) : Traefik surveille le dossier et ne doit jamais lire un
  # fichier a moitie ecrit.
  #
  # Les points du domaine sont echappes pour l'expression de Traefik (`\.`),
  # et chaque barre oblique doublee une fois de plus pour `sed`, qui mange
  # la premiere dans un texte de remplacement.
  motif="$(printf '%s' "$domaine" | sed 's/\./\\\\./g')"
  sed "s/DOMAINE_REGEX/$motif/g" "$ICI/caddy/traefik-coolify.yaml" > "$DYNAMIQUE/.salon.yaml.tmp"
  mv "$DYNAMIQUE/.salon.yaml.tmp" "$DYNAMIQUE/salon.yaml"
  echo "Route posee : $DYNAMIQUE/salon.yaml"

  # Domaines personnalises (offre Pro) : une route par domaine verifie,
  # tenue a jour toutes les deux minutes. Voir synchroniser-domaines.sh.
  printf '%s\n' \
    "*/2 * * * * root bash $ICI/scripts/synchroniser-domaines.sh >> /var/log/salon-domaines.log 2>&1" \
    > /etc/cron.d/salon-domaines
  chmod 644 /etc/cron.d/salon-domaines
  bash "$ICI/scripts/synchroniser-domaines.sh" || echo "Synchronisation des domaines : a reessayer."
fi

# Les images remplacees ne servent plus a rien ; sur 40 Go, elles comptent.
# Seulement les notres : la machine peut en heberger d'autres (Coolify garde
# les siennes pour revenir en arriere).
docker image prune --force --filter label=salon.plateforme >/dev/null
cat <<FIN

En ligne :
  plateforme       https://$domaine
  espace pro       https://app.$domaine
  administration   https://api.$domaine/${admin:-admin/}

Le premier chargement de chaque adresse peut prendre quelques secondes :
Caddy y obtient son certificat.
FIN
