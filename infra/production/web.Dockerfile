# syntax=docker/dockerfile:1.7
#
# Image du site Next.js : plateforme, espace professionnel et mini-sites.
#
# Contexte de construction : apps/web (voir compose.yml).
#
# Les variables `NEXT_PUBLIC_*` sont **gravees a la construction** : Next les
# recopie dans le JavaScript envoye au navigateur. Changer de domaine demande
# donc de reconstruire cette image, pas seulement de la redemarrer —
# `deployer.sh` le fait a chaque passage.

FROM node:22-bookworm-slim AS dependances
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci


FROM node:22-bookworm-slim AS construction
WORKDIR /app
COPY --from=dependances /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_PLATFORM_DOMAIN
ARG NEXT_PUBLIC_API_URL
# Le port disparait des liens quand il vaut 443 (lib/site.ts).
ARG NEXT_PUBLIC_WEB_PORT=443

ENV NEXT_PUBLIC_PLATFORM_DOMAIN=$NEXT_PUBLIC_PLATFORM_DOMAIN \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_WEB_PORT=$NEXT_PUBLIC_WEB_PORT \
    NEXT_TELEMETRY_DISABLED=1 \
    NEXT_OUTPUT_STANDALONE=1

# Refuser de construire sans domaine : l'image partirait avec `localhost`
# grave dedans, et chaque lien de chaque page pointerait vers la machine du
# visiteur.
RUN test -n "$NEXT_PUBLIC_PLATFORM_DOMAIN" && test -n "$NEXT_PUBLIC_API_URL" \
    || (echo "NEXT_PUBLIC_PLATFORM_DOMAIN et NEXT_PUBLIC_API_URL sont obligatoires" && exit 1)

RUN npm run build


FROM node:22-bookworm-slim
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# La sortie autonome ne contient ni `public/` ni `.next/static` : on les
# pose a cote du serveur, qui les sert alors lui-meme.
COPY --from=construction --chown=node:node /app/.next/standalone ./
COPY --from=construction --chown=node:node /app/.next/static ./.next/static
COPY --from=construction --chown=node:node /app/public ./public

# L'utilisateur `node` de l'image officielle, jamais root. Il possede
# `.next/` : le cache des pages regenerees s'y ecrit.
USER node
EXPOSE 3000
CMD ["node", "server.js"]
