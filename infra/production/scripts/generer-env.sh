#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Cree infra/production/.env et tire chaque secret au hasard.
#
#   bash scripts/generer-env.sh
#
# Ne remplace jamais une valeur deja posee : on peut le relancer sans
# risque, il ne complete que ce qui manque. C'est essentiel pour deux
# d'entre elles :
#
#   - les mots de passe Postgres ne servent qu'a la creation du volume ; les
#     changer ensuite dans ce fichier couperait l'application de sa base ;
#   - la paire VAPID : la regenerer invalide tous les abonnements push.
#
# Toutes les valeurs produites n'utilisent que [A-Za-z0-9_-] : elles se
# placent dans une URL de connexion Postgres et dans ce fichier sans
# echappement.
# ---------------------------------------------------------------------------
set -euo pipefail

ICI="$(cd "$(dirname "$0")/.." && pwd)"
FICHIER="$ICI/.env"

if [ ! -f "$FICHIER" ]; then
  cp "$ICI/env.exemple" "$FICHIER"
  echo "Cree : $FICHIER"
fi
# Lisible par root seul : il contient toutes les cles de la plateforme.
chmod 600 "$FICHIER"

valeur() { grep -E "^$1=" "$FICHIER" | head -n 1 | cut -d= -f2- || true; }

poser() {
  local cle=$1 val=$2
  if ! grep -qE "^$cle=" "$FICHIER"; then
    echo "$cle=$val" >> "$FICHIER"
  elif [ -z "$(valeur "$cle")" ]; then
    sed -i "s|^$cle=.*|$cle=$val|" "$FICHIER"
  else
    return 0
  fi
  echo "  $cle : genere"
}

hex() { openssl rand -hex "$1"; }
base64url() { base64 -w 0 | tr '+/' '-_' | tr -d '='; }

poser DJANGO_SECRET_KEY "$(openssl rand 64 | base64url)"
poser POSTGRES_PASSWORD "$(hex 24)"
poser SALON_ADMIN_PASSWORD "$(hex 24)"
poser SALON_APP_PASSWORD "$(hex 24)"
poser INTERNAL_API_TOKEN "$(hex 32)"
poser ADMIN_PATH "gestion-$(hex 6)/"

# Paire VAPID : cle privee PKCS8 et cle publique en point non compresse,
# toutes deux en base64url — le format que lit pywebpush, et celui que
# produit la commande documentee dans .env.example.
if [ -z "$(valeur VAPID_PUBLIC_KEY)" ] && [ -z "$(valeur VAPID_PRIVATE_KEY)" ]; then
  cle="$(mktemp)"
  openssl ecparam -name prime256v1 -genkey -noout -out "$cle" 2>/dev/null
  poser VAPID_PRIVATE_KEY "$(openssl pkcs8 -topk8 -nocrypt -in "$cle" -outform DER | base64url)"
  # Les 65 derniers octets de la cle publique DER sont le point lui-meme.
  poser VAPID_PUBLIC_KEY "$(openssl ec -in "$cle" -pubout -outform DER 2>/dev/null | tail -c 65 | base64url)"
  rm -f "$cle"
fi

acme="$(valeur ACME_EMAIL)"
if [ -n "$acme" ]; then
  poser VAPID_SUBJECT "mailto:$acme"
fi

# Ce qu'une machine ne peut pas deviner.
manquants=()
for cle in ACME_EMAIL EMAIL_HOST EMAIL_PORT DEFAULT_FROM_EMAIL VAPID_SUBJECT; do
  [ -n "$(valeur "$cle")" ] || manquants+=("$cle")
done

echo
if [ ${#manquants[@]} -gt 0 ]; then
  echo "A completer a la main dans $FICHIER :"
  printf '  - %s\n' "${manquants[@]}"
  echo "(VAPID_SUBJECT se remplit tout seul en relancant ce script une fois ACME_EMAIL pose.)"
  exit 1
fi
echo "Configuration complete."
