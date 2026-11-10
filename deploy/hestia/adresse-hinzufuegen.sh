#!/bin/bash
# Richtet eine weitere Adresse für HUBIplan hinter HestiaCP ein („Adressen je Einheit“,
# White Label W7), z. B. mitglieder.sv-musterstadt.example für einen weiteren Verein.
# Voraussetzung: HUBIplan läuft schon hinter Hestia (deploy/hestia/einrichten.sh).
#
# Aufruf vom lokalen Arbeitsrechner (PowerShell), läuft als root auf dem Server:
#   Get-Content -Raw deploy\hestia\adresse-hinzufuegen.sh | ssh deploy@server.example.org "sudo env HUSER=hosting-user DOMAIN=mitglieder.sv-musterstadt.example ZONE=sv-musterstadt.example bash -s"
#
# Was es tut:
#   1. eigene Web-Domain DOMAIN mit der Vorlage app-8110 (kein www-Alias, kein Postfach,
#      keine neue DNS-Zone), damit sie ein eigenes Zertifikat bekommt
#   2. A-Eintrag in der vorhandenen Hestia-Zone ZONE (entfällt mit ZONE=extern, wenn die DNS
#      woanders liegt; dann den Eintrag dort selbst setzen)
#   3. Let's-Encrypt-Zertifikat, sobald öffentliche Nameserver den Eintrag kennen
#   4. HUBIPLAN_ADRESSEN_AUS_LISTE=1 in /opt/hubiplan/.env, falls noch nicht gesetzt
#      (wirkt ab dem nächsten Ausrollen)
#
# Die Adresse muss außerdem in HUBIplan unter Plattform › Einstellungen › „Adressen je
# Einheit“ eingetragen sein, sonst antwortet HUBIplan dort mit „Unbekannte Adresse“.
# Wiederholbar: Was schon da ist, bleibt. Hestia lädt nginx nur neu (reload), andere
# Websites laufen weiter. HUBIplan selbst wird nicht neu gestartet.
set -euo pipefail
export PATH=/usr/local/hestia/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

HUSER=${HUSER:?HUSER fehlt, z. B. HUSER=hosting-user}
DOMAIN=${DOMAIN:?DOMAIN fehlt, z. B. DOMAIN=mitglieder.sv-musterstadt.example}
ZONE=${ZONE:?ZONE fehlt, z. B. ZONE=sv-musterstadt.example (oder ZONE=extern)}
ZONE_USER=${ZONE_USER:-$HUSER}
VORLAGE=app-8110
APP=/opt/hubiplan
# Hestia ohne Apache (nur nginx, wie bei einem eigenen Mailserver empfohlen): nginx ist dann
# selbst der Webserver, nicht der vorgeschaltete Proxy. Die Vorlage gehört dann nach
# nginx/php-fpm, ihre Ports heißen %web_port% statt %proxy_port%, und Hestia setzt sie mit
# v-change-web-domain-tpl statt v-change-web-domain-proxy-tpl.
if grep -q "^PROXY_SYSTEM='nginx'" /usr/local/hestia/conf/hestia.conf; then
    NUR_NGINX=""
    TPL=/usr/local/hestia/data/templates/web/nginx
else
    NUR_NGINX=1
    TPL=/usr/local/hestia/data/templates/web/nginx/php-fpm
fi
# vorlage_einspielen QUELLORDNER VORLAGE: .tpl und .stpl nach $TPL
vorlage_einspielen() {
    local endung
    for endung in tpl stpl; do
        if [ -n "$NUR_NGINX" ]; then
            sed -e 's/%proxy_port%/%web_port%/g' -e 's/%proxy_ssl_port%/%web_ssl_port%/g' \
                "$1/$2.$endung" > "$TPL/$2.$endung"
            chown root:root "$TPL/$2.$endung"
            chmod 644 "$TPL/$2.$endung"
        else
            install -m 644 -o root -g root "$1/$2.$endung" "$TPL/"
        fi
    done
}
# vorlage_setzen DOMAIN VORLAGE: Domain neu mit der Vorlage aufbauen (nginx nur reload)
vorlage_setzen() {
    if [ -n "$NUR_NGINX" ]; then
        v-change-web-domain-tpl "$HUSER" "$1" "$2" yes
    else
        v-change-web-domain-proxy-tpl "$HUSER" "$1" "$2" '' yes
    fi
}
ENV="$APP/.env"

DOMAIN=$(printf '%s' "$DOMAIN" | tr '[:upper:]' '[:lower:]')
ZONE=$(printf '%s' "$ZONE" | tr '[:upper:]' '[:lower:]')

echo "### Start $(TZ=Europe/Berlin date '+%d.%m.%Y %H:%M')"
[ -f "$ENV" ] || { echo "Abbruch: $ENV fehlt, erst deploy/deploy.sh und einrichten.sh ausführen."; exit 1; }
[ -f "$TPL/$VORLAGE.stpl" ] || { echo "Abbruch: Vorlage $VORLAGE fehlt, erst deploy/hestia/einrichten.sh ausführen."; exit 1; }
curl -fsS -o /dev/null http://127.0.0.1:8110/ || { echo "Abbruch: HUBIplan antwortet nicht auf 127.0.0.1:8110."; exit 1; }
if [ "$ZONE" != extern ]; then
    case "$DOMAIN" in
        *."$ZONE") ;;
        *) echo "Abbruch: $DOMAIN liegt nicht in der Zone $ZONE."; exit 1 ;;
    esac
    v-list-dns-domain "$ZONE_USER" "$ZONE" >/dev/null 2>&1 \
        || { echo "Abbruch: Hestia-Benutzer $ZONE_USER hat keine DNS-Zone $ZONE (sonst ZONE=extern)."; exit 1; }
fi

echo "--- 1) Web-Domain $DOMAIN mit Vorlage $VORLAGE"
if v-list-web-domain "$HUSER" "$DOMAIN" >/dev/null 2>&1; then
    echo "gibt es schon"
else
    v-add-web-domain "$HUSER" "$DOMAIN" '' yes none
fi
vorlage_setzen "$DOMAIN" "$VORLAGE"
IP=$(v-list-web-domain "$HUSER" "$DOMAIN" json | sed -n 's/.*"IP": *"\([0-9.]*\)".*/\1/p' | head -1)
[ -n "$IP" ] || { echo "Abbruch: IP der Web-Domain nicht gefunden."; exit 1; }
echo "Web-Domain zeigt auf $IP"

echo "--- 2) DNS-A-Eintrag"
if [ "$ZONE" = extern ]; then
    echo "DNS liegt nicht in Hestia: A-Eintrag $DOMAIN -> $IP beim DNS-Anbieter selbst setzen"
else
    SUB=${DOMAIN%."$ZONE"}
    if v-list-dns-records "$ZONE_USER" "$ZONE" plain | awk -F'\t' -v s="$SUB" '$2==s && $3=="A" {f=1} END {exit !f}'; then
        echo "A-Eintrag $SUB in $ZONE gibt es schon"
    else
        v-add-dns-record "$ZONE_USER" "$ZONE" "$SUB" A "$IP" '' '' yes
        echo "A-Eintrag $SUB.$ZONE -> $IP angelegt"
    fi
fi

echo "--- 3) Zertifikat (Let's Encrypt)"
# Fehlversuche zählen bei Let's Encrypt gegen ein Limit: erst holen, wenn ein öffentlicher
# Resolver die Adresse schon auf diesen Server auflöst (lokale Zone zählt nicht).
OEFFENTLICH=""
if command -v dig >/dev/null 2>&1; then
    OEFFENTLICH=$(dig +short A "$DOMAIN" @1.1.1.1 2>/dev/null | grep -E '^[0-9.]+$' | head -1 || true)
fi
# Hestia prüft vor Let's Encrypt mit dem Resolver des Servers. Der kann ein „gibt es nicht“
# vom ersten Lauf noch zwischengespeichert haben, auch wenn der Eintrag öffentlich schon da ist.
LOKAL=$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1; exit}' || true)
if [ -n "${OHNE_ZERTIFIKAT:-}" ]; then
    echo "übersprungen (OHNE_ZERTIFIKAT)"
elif v-list-web-domain "$HUSER" "$DOMAIN" json | grep -q '"SSL": *"yes"'; then
    echo "SSL ist schon eingerichtet"
elif command -v dig >/dev/null 2>&1 && [ "$OEFFENTLICH" != "$IP" ]; then
    echo "noch nicht: öffentlich löst $DOMAIN auf '${OEFFENTLICH:-nichts}' auf, erwartet $IP."
    echo "Später einfach dieses Skript noch einmal starten."
elif [ "$LOKAL" != "$IP" ]; then
    echo "noch nicht: öffentlich stimmt der Eintrag, aber der Server selbst löst $DOMAIN noch auf"
    echo "'${LOKAL:-nichts}' auf (alte Antwort zwischengespeichert, meist bis zu einer Stunde)."
    echo "Später einfach dieses Skript noch einmal starten."
else
    sleep 5   # DNS-Reload abwarten
    v-add-letsencrypt-domain "$HUSER" "$DOMAIN"
    v-add-web-domain-ssl-force "$HUSER" "$DOMAIN" yes 2>/dev/null || true
fi

echo "--- 4) Adressen aus der Liste annehmen (HUBIPLAN_ADRESSEN_AUS_LISTE)"
if grep -q '^HUBIPLAN_ADRESSEN_AUS_LISTE=1' "$ENV"; then
    echo "steht schon in der .env"
elif grep -E '^DJANGO_ALLOWED_HOSTS=' "$ENV" | tr ',=' '\n' | grep -qxF "$DOMAIN"; then
    echo "nicht nötig: $DOMAIN steht in DJANGO_ALLOWED_HOSTS"
else
    cp -p "$ENV" "$ENV.vor-adressen-$(date +%Y%m%d%H%M)"
    sed -i '/^HUBIPLAN_ADRESSEN_AUS_LISTE=/d' "$ENV"
    echo "HUBIPLAN_ADRESSEN_AUS_LISTE=1" >> "$ENV"
    chmod 600 "$ENV"
    echo "in die .env geschrieben (Sicherung daneben); wirkt ab dem nächsten Ausrollen"
fi

echo "--- 5) Prüfung von außen"
curl -sS -o /dev/null -w "http  -> %{http_code} %{redirect_url}\n" --resolve "$DOMAIN:80:$IP" "http://$DOMAIN/" || true
if v-list-web-domain "$HUSER" "$DOMAIN" json | grep -q '"SSL": *"yes"'; then
    curl -sS -o /dev/null -w "https -> %{http_code}\n" --resolve "$DOMAIN:443:$IP" "https://$DOMAIN/" || true
    curl -sS --resolve "$DOMAIN:443:$IP" "https://$DOMAIN/api/health/" || true; echo
fi
echo "### Ende $(TZ=Europe/Berlin date '+%d.%m.%Y %H:%M')"
