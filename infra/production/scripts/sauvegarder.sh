#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Sauvegarde la base et les fichiers televerses.
#
#   bash scripts/sauvegarder.sh
#
# Chaque nuit, par cron (voir infra/production/README.md) :
#
#   30 2 * * * bash /opt/salon/infra/production/scripts/sauvegarder.sh >> /var/log/salon-sauvegarde.log 2>&1
#
# ---------------------------------------------------------------------------
# Ce qui est sauvegarde, et pourquoi les deux
# ---------------------------------------------------------------------------
#
# La base seule ne suffit pas : elle reference des photos de galerie, des
# logos et des preuves de versement qui vivent sur le disque. Restaurer l'une
# sans les autres rendrait un catalogue d'images cassees.
#
# `pg_dump` et non une copie du dossier de Postgres : une copie prise pendant
# une ecriture n'est pas coherente, un dump l'est toujours.
#
# ---------------------------------------------------------------------------
# Ce qui ne l'est pas
# ---------------------------------------------------------------------------
#
# Ces archives restent sur la meme machine : elles protegent d'une erreur
# (une suppression, une migration ratee), pas de la perte du serveur. Pour
# cela, activer les sauvegardes Hetzner du serveur, ou copier ce dossier
# ailleurs.
# ---------------------------------------------------------------------------
set -euo pipefail

ICI="$(cd "$(dirname "$0")/.." && pwd)"
DESTINATION="${SAUVEGARDES:-/var/backups/salon}"
GARDER_JOURS="${GARDER_JOURS:-14}"
HORODATAGE="$(date -u +%Y%m%d-%H%M%S)"

compose() { docker compose --file "$ICI/compose.yml" --env-file "$ICI/.env" "$@"; }

mkdir -p "$DESTINATION"
chmod 700 "$DESTINATION"

# Format personnalise : compresse, et restaurable table par table.
compose exec -T postgres pg_dump --username postgres --format custom salon \
  > "$DESTINATION/base-$HORODATAGE.dump"

# Le volume des medias, lu depuis le conteneur de l'API qui le monte.
compose exec -T api tar --create --gzip --directory /app/media . \
  > "$DESTINATION/medias-$HORODATAGE.tar.gz"

find "$DESTINATION" -type f \( -name 'base-*.dump' -o -name 'medias-*.tar.gz' \) \
  -mtime "+$GARDER_JOURS" -delete

echo "$(date -u +%FT%TZ) sauvegarde $HORODATAGE : $(du -sh "$DESTINATION" | cut -f1) au total"
