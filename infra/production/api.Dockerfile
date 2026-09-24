# syntax=docker/dockerfile:1.7
#
# Image de l'API Django. Une seule image sert trois roles — l'API (Gunicorn),
# le worker Celery et le planificateur Celery beat — et c'est `compose.yml`
# qui choisit la commande. Une image par role ferait diverger leurs
# dependances au premier ajout.
#
# Contexte de construction : apps/api (voir compose.yml).

FROM python:3.13-slim-bookworm

# Permet a `deployer.sh` de ne nettoyer que nos anciennes images, jamais
# celles des autres services de la machine.
LABEL salon.plateforme="api"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# uv a la meme version que sur le poste de developpement : un `uv.lock`
# ecrit par une version et lu par une autre est la premiere cause de
# « ca marche chez moi ».
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /usr/local/bin/uv

WORKDIR /app

# Les dependances d'abord, le code ensuite : modifier une ligne de Python ne
# refait pas l'installation, qui est l'etape lente.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY . .

# Jamais root a l'execution. Les deux dossiers inscriptibles recoivent des
# volumes (compose.yml) ; les creer ici leur donne le bon proprietaire des
# la premiere montee.
RUN useradd --system --uid 10001 --home-dir /app salon \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R salon:salon /app/media /app/staticfiles

USER salon
EXPOSE 8000

# Trois processus de quatre fils : de quoi occuper quatre coeurs sans
# affamer Next, Postgres et Celery, qui vivent sur la meme machine.
# `GUNICORN_CMD_ARGS` permet d'ajuster sans reconstruire l'image.
#
# `--forwarded-allow-ips "*"` : seul Caddy et les autres conteneurs
# joignent ce port, jamais Internet. Voir compose.yml, qui ne le publie pas.
#
# `--no-control-socket` : Gunicorn 26 ouvre par defaut une prise de pilotage
# dans son dossier de travail, que l'utilisateur non privilegie ne peut pas
# ecrire — d'ou une erreur a chaque demarrage, sans effet mais trompeuse
# quand on lit les journaux un jour de panne. Rien ici ne s'en sert.
CMD ["gunicorn", "config.wsgi", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", "--threads", "4", \
     "--timeout", "60", "--graceful-timeout", "30", \
     "--forwarded-allow-ips", "*", \
     "--no-control-socket", \
     "--access-logfile", "-"]
