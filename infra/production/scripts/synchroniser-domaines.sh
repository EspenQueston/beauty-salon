#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Routes du proxy de Coolify pour les domaines personnalises des salons.
#
#   bash scripts/synchroniser-domaines.sh
#
# En mode `coolify`, Traefik ne transmet a notre Caddy que les noms du
# domaine de la plateforme (voir caddy/traefik-coolify.yaml). Un salon Pro qui
# relie `monsalon.com` a besoin d'une route de plus : ce script la tient a
# jour, a partir de la liste des domaines verifies (et seulement d'eux).
#
# Lance par cron toutes les deux minutes (installe par deployer.sh). Il
# n'ecrit le fichier que si la liste a change : Traefik le recharge alors de
# lui-meme. En mode `direct`, Caddy recoit tout le trafic : rien a faire.
# ---------------------------------------------------------------------------
set -euo pipefail

ICI="$(cd "$(dirname "$0")/.." && pwd)"
valeur() { grep -E "^$1=" "$ICI/.env" | head -n 1 | cut -d= -f2- || true; }

[ "$(valeur ENTREE)" = "coolify" ] || exit 0

DYNAMIQUE=/data/coolify/proxy/dynamic
CIBLE="$DYNAMIQUE/salon-domaines.yaml"
compose() {
  docker compose --file "$ICI/compose.yml" --file "$ICI/compose.coolify.yml" \
    --env-file "$ICI/.env" "$@"
}

# Seuls des noms de domaine bien formes entrent dans la regle Traefik : un
# caractere de plus (` ou ') pourrait sinon en changer le sens.
hotes="$(compose exec -T api python manage.py domaines_personnalises 2>/dev/null \
  | tr -d '\r' | grep -E '^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$' || true)"

if [ -z "$hotes" ]; then
  [ -f "$CIBLE" ] && rm -f "$CIBLE" && echo "$(date -u +%FT%TZ) aucun domaine : route retiree"
  exit 0
fi

sni="$(printf '%s\n' "$hotes" | sed 's/.*/HostSNI(`&`)/' | paste -sd'|' | sed 's/|/ || /g')"
http="$(printf '%s\n' "$hotes" | sed 's/.*/Host(`&`)/' | paste -sd'|' | sed 's/|/ || /g')"

temporaire="$(mktemp)"
cat > "$temporaire" <<YAML
# Genere par synchroniser-domaines.sh — ne pas modifier a la main.
tcp:
  routers:
    salon-domaines-https:
      entryPoints:
        - https
      rule: '$sni'
      service: salon-caddy-https
      tls:
        passthrough: true
http:
  routers:
    salon-domaines-http:
      entryPoints:
        - http
      rule: '$http'
      service: salon-caddy-http
YAML

if [ ! -f "$CIBLE" ] || ! cmp -s "$temporaire" "$CIBLE"; then
  mv "$temporaire" "$CIBLE"
  chmod 644 "$CIBLE"
  echo "$(date -u +%FT%TZ) route mise a jour : $(printf '%s\n' "$hotes" | wc -l) domaine(s)"
else
  rm -f "$temporaire"
fi
