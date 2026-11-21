# Entwicklungs-Container: Vite-Dev-Server mit Weiterleitung ans Backend.
# Für den Produktivbetrieb kommt später ein eigener Build (statische Dateien) dazu.
FROM node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5

WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
