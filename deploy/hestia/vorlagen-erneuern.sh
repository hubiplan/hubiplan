#!/bin/bash
# Spielt die nginx-Vorlagen von HUBIplan (app-8110) und der Vereinswebseite
# (webseite-8111) nach einer Änderung neu ein, z. B. die Seite „Wird gerade
# aktualisiert“ statt „502 Bad Gateway“ beim Ausrollen. Erst HUBIplan und die
# Webseite ausrollen (die Vorlagen kommen aus /opt/hubiplan und /opt/hubiplan-website).
#
# Aufruf vom lokalen Arbeitsrechner (PowerShell), läuft als root auf dem Server:
#   Get-Content -Raw deploy\hestia\vorlagen-erneuern.sh | ssh deploy@server.example.org "sudo env HUSER=hosting-user bash -s"
#
# Nur Domains, die die Vorlage schon nutzen, werden neu aufgebaut. Hestia lädt nginx
# nur neu (reload), andere Websites laufen weiter. Besteht die neue Konfiguration
# „nginx -t“ nicht, kommen die vorigen Vorlagen zurück.
set -euo pipefail
export PATH=/usr/local/hestia/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

HUSER=${HUSER:?HUSER fehlt, z. B. HUSER=hosting-user}
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
SICHERUNG=/root/sicherung-nginx-vorlagen/$(date +%Y-%m-%d_%H%M)

echo "### Start $(TZ=Europe/Berlin date '+%d.%m.%Y %H:%M')"
umask 077
mkdir -p "$SICHERUNG"

# Vorlage → Quelle
declare -A QUELLE=(
    [app-8110]=/opt/hubiplan/deploy/hestia
    [webseite-8111]=/opt/hubiplan-website/deploy/hestia
)

DOMAINS=()
for vorlage in "${!QUELLE[@]}"; do
    quelle=${QUELLE[$vorlage]}
    if [ ! -f "$quelle/$vorlage.stpl" ]; then
        echo "$vorlage: keine Vorlage in $quelle, übersprungen"
        continue
    fi
    for endung in tpl stpl; do
        [ -f "$TPL/$vorlage.$endung" ] && cp -p "$TPL/$vorlage.$endung" "$SICHERUNG/"
    done
    vorlage_einspielen "$quelle" "$vorlage"
    echo "$vorlage: eingespielt"
    for domain in $(v-list-web-domains "$HUSER" plain | cut -f1); do
        # Ohne Apache steht die Vorlage im Feld TPL, sonst im Feld PROXY
        feld=PROXY
        [ -n "$NUR_NGINX" ] && feld=TPL
        aktuell=$(v-list-web-domain "$HUSER" "$domain" json | sed -n "s/.*\"$feld\": *\"\([^\"]*\)\".*/\\1/p" | head -1)
        [ "$aktuell" = "$vorlage" ] && DOMAINS+=("$domain:$vorlage")
    done
done

neu_aufbauen() {
    for eintrag in "${DOMAINS[@]}"; do
        vorlage_setzen "${eintrag%%:*}" "${eintrag##*:}"
    done
}

if [ "${#DOMAINS[@]}" -eq 0 ]; then
    echo "Keine Domain nutzt die Vorlagen, nichts neu aufgebaut."
    exit 0
fi
echo "Neu aufbauen: ${DOMAINS[*]}"
if neu_aufbauen && nginx -t 2> /dev/null; then
    echo "Fertig. Sicherung der vorigen Vorlagen: $SICHERUNG"
else
    echo "FEHLER: nginx-Konfiguration ungültig, vorige Vorlagen kommen zurück." >&2
    install -m 644 -o root -g root "$SICHERUNG"/* "$TPL/"
    neu_aufbauen || true
    nginx -t
    exit 1
fi
