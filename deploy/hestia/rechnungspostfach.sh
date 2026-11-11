#!/bin/bash
# Rechnungspostfach auf dem Hestia-Server einrichten (#374): ein Postfach, z. B.
# rechnung@example.org, an das Lieferanten E-Rechnungen schicken. Jeder Verein bekommt in
# HUBIplan eine eigene Plus-Adresse (rechnung+<kennung>@example.org, Finanzen ›
# Rechnungseingang). HUBIplan holt das Postfach jede Minute per IMAP ab
# (billing/incoming_mail.py) und legt übernommene Mails im Ordner „Verarbeitet“ ab.
#
# Aufruf vom lokalen Arbeitsrechner (PowerShell), läuft als root auf dem Server:
#   Get-Content -Raw deploy\hestia\rechnungspostfach.sh | ssh deploy@server.example.org "sudo env HUSER=hosting-user DOMAIN=example.org bash -s"
#
# Die Mail-Domain muss es schon geben (z. B. aus einrichten.sh oder verteiler.sh).
# Wiederholbar: Was schon da ist, bleibt. Gibt keine Passwörter aus; das Passwort des
# Postfachs steht nur in /opt/hubiplan/.env.
set -euo pipefail
export PATH=/usr/local/hestia/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

HUSER=${HUSER:?HUSER fehlt, z. B. HUSER=hosting-user}
DOMAIN=${DOMAIN:?DOMAIN fehlt, z. B. DOMAIN=example.org}
KONTO=${KONTO:-rechnung}
APP=/opt/hubiplan
ENV="$APP/.env"
# Mailserver: wie beim Verteiler (INBOUND_IMAP_HOST), sonst mail.<Domain>. Bei einer
# Unterdomain wie verein.example.org heißt er meist mail.example.org: dann MAILSERVER= setzen.
if [ -z "${MAILSERVER:-}" ] && [ -f "$ENV" ]; then
    MAILSERVER=$(grep '^INBOUND_IMAP_HOST=' "$ENV" | cut -d= -f2 || true)
fi
MAILSERVER=${MAILSERVER:-mail.$DOMAIN}

echo "### Start $(TZ=Europe/Berlin date '+%d.%m.%Y %H:%M')"
[ -f "$ENV" ] || { echo "Abbruch: $ENV fehlt."; exit 1; }
v-list-mail-domain "$HUSER" "$DOMAIN" > /dev/null 2>&1 || {
    echo "Abbruch: Mail-Domain $DOMAIN gibt es nicht."
    exit 1
}

echo "Mailserver: $MAILSERVER"
getent hosts "$MAILSERVER" > /dev/null || {
    echo "Abbruch: $MAILSERVER ist nicht auflösbar, bitte MAILSERVER=… angeben."
    exit 1
}

echo "--- 1) Postfach $KONTO@$DOMAIN"
if grep -q '^EINVOICE_IMAP_HOST=' "$ENV"; then
    echo "Rechnungspostfach steht schon in der .env"
else
    PW=$(openssl rand -base64 30 | tr -d '\n/+=')
    if v-list-mail-account "$HUSER" "$DOMAIN" "$KONTO" > /dev/null 2>&1; then
        v-change-mail-account-password "$HUSER" "$DOMAIN" "$KONTO" "$PW"
    else
        v-add-mail-account "$HUSER" "$DOMAIN" "$KONTO" "$PW"
    fi
    umask 077
    {
        echo "EINVOICE_IMAP_HOST=$MAILSERVER"
        echo "EINVOICE_IMAP_PORT=993"
        echo "EINVOICE_IMAP_USER=$KONTO@$DOMAIN"
        echo "EINVOICE_IMAP_PASSWORD=$PW"
    } >> "$ENV"
    unset PW
    echo "Postfach angelegt, Zugangsdaten nur in $ENV"
fi
chmod 600 "$ENV"

echo "--- 2) Dienste mit neuer .env starten"
cd "$APP" && sh deploy/server-setup.sh > /dev/null && echo "Docker-Verbund läuft"
echo "Probe: eine Mail mit E-Rechnung an die Adresse aus Finanzen › Rechnungseingang schicken."
echo "### Ende $(TZ=Europe/Berlin date '+%d.%m.%Y %H:%M')"
