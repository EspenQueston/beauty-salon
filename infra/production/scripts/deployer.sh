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
compose() { docker compose --file "$ICI/compose.yml" --env-file "$ICI/.env" "$@"; }

if [ ! -f "$ICI/.env" ]; then
  echo "Pas de .env : lancez d'abord bash scripts/generer-env.sh" >&2
  exit 1
fi

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
compose ps

# Les images remplacees ne servent plus a rien ; sur 40 Go, elles comptent.
docker image prune --force >/dev/null

domaine="$(grep -E '^PLATFORM_DOMAIN=' "$ICI/.env" | cut -d= -f2-)"
admin="$(grep -E '^ADMIN_PATH=' "$ICI/.env" | cut -d= -f2-)"
cat <<FIN

En ligne :
  plateforme       https://$domaine
  espace pro       https://app.$domaine
  administration   https://api.$domaine/${admin:-admin/}

Le premier chargement de chaque adresse peut prendre quelques secondes :
Caddy y obtient son certificat.
FIN
