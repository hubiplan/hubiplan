#!/bin/bash
# Geheimer Kopfwert zwischen HestiaCP-nginx und Caddy (Gesamtaudit 08.11. GA8-03, Fachfrage F-05).
#
# Caddy lauscht auf 127.0.0.1:WEB_PORT. Auf einem geteilten Server erreicht diesen Port jeder
# Prozess, auch Nachbar-Websites. Ohne Schutz könnte so jemand per X-Real-IP beliebige
# Besucheradressen vorgeben (Ratenbegrenzung umgehen, fremde Adressen sperren lassen).
# Dieses Skript erzeugt einen zufälligen Kopfwert, den nur nginx kennt und mitschickt; Caddy
# übernimmt X-Real-IP nur noch mit diesem Wert (deploy/caddy/proxy-ip.caddy).
#
# Reihenfolge ohne Unterbrechung: erst nginx (schickt den Wert mit, Caddy ignoriert ihn noch),
# dann .env und Neustart von Caddy.
#
# Aufruf vom lokalen Arbeitsrechner (PowerShell), läuft als root auf dem Server:
#   Get-Content -Raw deploy\hestia\proxy-geheim.sh | ssh deploy@server.example.org "sudo bash -s"
# NEU=1 erzeugt einen neuen Wert. Gibt den Wert nie aus.
set -euo pipefail
export PATH=/usr/local/hestia/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

APP=${APP:-/opt/hubiplan}
ENV="$APP/.env"
INC_DIR=/etc/nginx/hubiplan
INC="$INC_DIR/proxy-geheim.inc"

echo "### Start $(TZ=Europe/Berlin date '+%d.%m.%Y %H:%M')"
[ -f "$ENV" ] || { echo "Abbruch: $ENV fehlt."; exit 1; }
grep -q '^HUBIPLAN_HINTER_PROXY=1' "$ENV" || { echo "Abbruch: HUBIPLAN_HINTER_PROXY=1 fehlt in $ENV."; exit 1; }

GEHEIM=$(sed -n 's/^HUBIPLAN_PROXY_GEHEIM=//p' "$ENV" | tail -1)
if [ -z "$GEHEIM" ] || [ -n "${NEU:-}" ]; then
    GEHEIM=$(openssl rand -hex 32)
    NEU_GESETZT=1
fi
case "$GEHEIM" in
    *[!0-9a-f]*) echo "Abbruch: HUBIPLAN_PROXY_GEHEIM in $ENV ist kein Hexwert."; exit 1 ;;
esac

echo "--- 1) nginx schickt den Kopfwert mit"
umask 077
install -d -m 700 -o root -g root "$INC_DIR"
ALT=""
[ -f "$INC" ] && ALT=$(cat "$INC")
printf 'proxy_set_header X-Hubiplan-Proxy "%s";\n' "$GEHEIM" > "$INC.neu"
chmod 600 "$INC.neu"
mv "$INC.neu" "$INC"
if nginx -t 2> /dev/null; then
    systemctl reload nginx
    echo "nginx neu geladen"
else
    echo "FEHLER: nginx -t schlägt fehl, vorige Datei kommt zurück." >&2
    if [ -n "$ALT" ]; then printf '%s\n' "$ALT" > "$INC"; else rm -f "$INC"; fi
    nginx -t
    exit 1
fi
grep -rqs "hubiplan/proxy-geheim" /home/*/conf/web/*/nginx.ssl.conf \
    || echo "Hinweis: Die nginx-Vorlage app-8110 ist noch alt; erst deploy/hestia/vorlagen-erneuern.sh ausführen."

echo "--- 2) Caddy prüft den Kopfwert"
if [ -n "${NEU_GESETZT:-}" ]; then
    sed -i '/^HUBIPLAN_PROXY_GEHEIM=/d' "$ENV"
    echo "HUBIPLAN_PROXY_GEHEIM=$GEHEIM" >> "$ENV"
    chmod 600 "$ENV"
fi
unset GEHEIM ALT
cd "$APP" && sh deploy/server-setup.sh > /dev/null && echo "Docker-Verbund läuft"

echo "--- 3) Prüfung"
sleep 3
PORT=$(sed -n 's/^WEB_PORT=//p' "$ENV" | tail -1)
curl -fsS -o /dev/null "http://127.0.0.1:${PORT:-8110}/api/health/" && echo "Caddy antwortet" || echo "WARNUNG: Caddy antwortet nicht"
echo "### Ende $(TZ=Europe/Berlin date '+%d.%m.%Y %H:%M')"
