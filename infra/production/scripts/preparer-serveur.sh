#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Prepare une machine Ubuntu ou Debian neuve a recevoir la plateforme.
#
#   curl -fsSL https://raw.githubusercontent.com/EspenQueston/beauty-salon/<branche>/infra/production/scripts/preparer-serveur.sh -o preparer-serveur.sh
#   sudo bash preparer-serveur.sh [branche]
#
# Idempotent : chaque etape verifie d'abord si elle est deja faite.
#
# ---------------------------------------------------------------------------
# Ce qu'il fait
# ---------------------------------------------------------------------------
#
#   1. verifie que les ports 80 et 443 sont libres ;
#   2. installe Docker Engine et Compose depuis le depot officiel de Docker ;
#   3. active les mises a jour de securite automatiques ;
#   4. ajoute 2 Go d'echange si la machine n'en a aucun ;
#   5. recupere le code dans /opt/salon.
#
# ---------------------------------------------------------------------------
# Ce qu'il ne fait pas, volontairement
# ---------------------------------------------------------------------------
#
# Il ne touche pas au pare-feu de la machine. Ce serveur peut deja heberger
# autre chose, et activer `ufw` couperait sans prevenir tout service qui
# ecoute sur un autre port. Docker, de plus, contourne `ufw` pour les ports
# qu'il publie : la regle ecrite ne serait pas la regle appliquee. Le bon
# outil est le pare-feu Hetzner Cloud, applique hors de la machine — voir
# infra/production/README.md.
#
# Il ne prend jamais la place d'un service existant : si les ports 80 ou 443
# sont occupes, il s'arrete et dit par qui.
# ---------------------------------------------------------------------------
set -euo pipefail

BRANCHE="${1:-main}"
DEPOT="https://github.com/EspenQueston/beauty-salon.git"
CIBLE="/opt/salon"

etape() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "A lancer en root : sudo bash $0 $*" >&2
  exit 1
fi

# shellcheck source=/dev/null
. /etc/os-release
case "$ID" in
  ubuntu|debian) ;;
  *) echo "Systeme non pris en charge : $PRETTY_NAME (Ubuntu ou Debian attendu)." >&2; exit 1 ;;
esac

# ---------------------------------------------------------------------------
etape "1. Ports 80 et 443"
# ---------------------------------------------------------------------------
# Un conteneur de cette plateforme qui les occupe deja n'est pas un conflit :
# c'est un redeploiement.
occupants="$(ss -Htlnp '( sport = :80 or sport = :443 )' 2>/dev/null || true)"
if [ -n "$occupants" ] && ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^salon-caddy'; then
  echo "Les ports 80/443 sont deja utilises sur cette machine :"
  echo "$occupants"
  echo
  echo "La plateforme a besoin de ces deux ports pour HTTPS. Rien n'a ete modifie."
  echo "Arretez ou deplacez le service ci-dessus, ou lisez la section"
  echo "« Le serveur heberge deja un site » de infra/production/README.md."
  exit 1
fi
echo "Libres."

# ---------------------------------------------------------------------------
etape "2. Docker"
# ---------------------------------------------------------------------------
if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
  echo "Deja installe : $(docker --version), $(docker compose version --short)"
else
  # La methode du depot apt officiel, et non le script `get.docker.com` :
  # elle est verifiee par signature et suit les mises a jour du systeme.
  apt-get update -q
  apt-get install -y -q ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$ID $VERSION_CODENAME stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
  echo "Installe : $(docker --version)"
fi

# ---------------------------------------------------------------------------
etape "3. Mises a jour de securite automatiques"
# ---------------------------------------------------------------------------
if dpkg -s unattended-upgrades >/dev/null 2>&1; then
  echo "Deja actives."
else
  apt-get install -y -q unattended-upgrades
  dpkg-reconfigure -f noninteractive unattended-upgrades
  echo "Activees."
fi

# ---------------------------------------------------------------------------
etape "4. Memoire d'echange"
# ---------------------------------------------------------------------------
# La construction de l'image Next monte a 2-3 Go. Avec Postgres, Redis et
# Celery a cote, un pic sans echange peut reveiller le tueur de processus du
# noyau au milieu d'un deploiement.
if [ -n "$(swapon --show --noheadings)" ]; then
  echo "Deja presente : $(swapon --show --noheadings | awk '{print $1, $3}')"
else
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "2 Go ajoutes."
fi

# ---------------------------------------------------------------------------
etape "5. Code de la plateforme"
# ---------------------------------------------------------------------------
command -v git >/dev/null || apt-get install -y -q git
if [ -d "$CIBLE/.git" ]; then
  echo "Deja present dans $CIBLE (branche $(git -C "$CIBLE" rev-parse --abbrev-ref HEAD))."
else
  git clone --branch "$BRANCHE" "$DEPOT" "$CIBLE"
  echo "Recupere dans $CIBLE, branche $BRANCHE."
fi

cat <<SUITE

Machine prete. La suite :

  cd $CIBLE/infra/production
  bash scripts/generer-env.sh          # cree .env et ses secrets
  nano .env                            # e-mail et ACME_EMAIL
  bash scripts/generer-env.sh          # complete ce qui en dependait
  bash scripts/deployer.sh $BRANCHE

SUITE
