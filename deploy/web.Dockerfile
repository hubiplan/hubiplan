# Baut das Frontend und liefert es zusammen mit Caddy aus.
# Build-Kontext ist das Wurzelverzeichnis des Repos.
FROM node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5 AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
# Quellcode-Adresse für /lizenz (AGPL § 13). Wer eine veränderte Fassung betreibt, setzt hier
# sein eigenes öffentliches Repository (docker compose build --build-arg …).
ARG HUBIPLAN_SOURCE_URL=https://github.com/hubiplan/hubiplan
ENV VITE_HUBIPLAN_SOURCE_URL=$HUBIPLAN_SOURCE_URL
RUN npm run build
# Brotli- und gzip-Fassungen für Caddys „precompressed“ (deploy/caddy/site.caddy)
RUN node scripts/vorkomprimieren.mjs dist

FROM caddy:2-alpine@sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0
COPY deploy/Caddyfile deploy/Caddyfile.proxy /etc/caddy/
COPY deploy/caddy/ /etc/caddy/caddy/
COPY --from=build /app/dist /srv
COPY LICENSE /srv/lizenzen/LICENSE.txt
# Änderungshinweise für die Seite „Neuigkeiten“ (frontend/src/news/)
COPY CHANGELOG.md CHANGELOG.en.md /srv/lizenzen/
