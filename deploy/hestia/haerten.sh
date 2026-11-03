#!/bin/bash
# Härtung des Servers mit HestiaCP (Produktionsbetrieb), siehe docs/echtbetrieb.md.
#
# Ohne PUNKT wird nur geprüft und nichts geändert. Mit PUNKT=… wird genau ein Punkt
# umgesetzt; jeder Punkt lässt sich zurücknehmen (steht jeweils dabei).
# ADMIN_USER muss das unprivilegierte SSH-Verwaltungskonto mit sudo-Rechten benennen.
#
# Aufruf vom lokalen Arbeitsrechner (PowerShell), läuft als root auf dem Server:
#   Get-Content -Raw deploy/hestia/haerten.sh | ssh deploy@server.example.org "sudo env ADMIN_USER=deploy bash -s"
#   Get-Content -Raw deploy/hestia/haerten.sh | ssh deploy@server.example.org "sudo env ADMIN_USER=deploy PUNKT=ssh bash -s"
#
# Punkte:
#   ssh          ADMIN_USER nur noch mit Schlüssel, kein root-Login
#   api          Hestia-API nur noch von 127.0.0.1
#   panel        Hestia-Panel (8083) nicht mehr aus dem Internet, nur per SSH-Tunnel:
#                ssh -L 8083:127.0.0.1:8083 deploy@server.example.org, dann
#                https://localhost:8083 im Browser
#   aide         Integritätsprüfung der Systemdateien mit täglicher Mail an root
#
# Gibt keine Passwörter oder Schlüssel aus. Startet keine Web- oder Maildienste neu
# (sshd wird nur neu geladen, bestehende Verbindungen bleiben).
set -euo pipefail

# Vor jedem Systemaufruf prüfen: keine SSH-Muster, Pfade oder Zeilenumbrüche zulassen.
ADMIN_USER=${ADMIN_USER:?ADMIN_USER fehlt, z. B. ADMIN_USER=deploy}
if [[ ! "$ADMIN_USER" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || (( ${#ADMIN_USER} > 32 )) || [[ "$ADMIN_USER" = root ]]; then
    echo "Abbruch: ADMIN_USER muss ein gültiger Linux-Benutzername (höchstens 32 Zeichen) sein und darf nicht root sein." >&2
    exit 1
fi
export PATH=/usr/local/hestia/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Den tatsächlichen Konto- und Home-Eintrag verwenden, auch bei abweichendem Home-Pfad.
ADMIN_ENTRY=$(getent passwd "$ADMIN_USER") || { echo "Abbruch: ADMIN_USER ist kein vorhandenes Benutzerkonto." >&2; exit 1; }
IFS=: read -r ADMIN_ACCOUNT ADMIN_PASSWORD ADMIN_UID ADMIN_GID ADMIN_GECOS ADMIN_HOME ADMIN_SHELL <<< "$ADMIN_ENTRY"
if [[ "$ADMIN_ACCOUNT" != "$ADMIN_USER" || ! "$ADMIN_UID" =~ ^[0-9]+$ || "$ADMIN_UID" = 0 || "$ADMIN_HOME" != /* ]]; then
    echo "Abbruch: ADMIN_USER muss ein Konto ohne UID 0 mit absolutem Heimverzeichnis sein." >&2
    exit 1
fi

PUNKT=${PUNKT:-}
SSHCONF=/etc/ssh/sshd_config.d/10-hubiplan-haertung.conf
ok() { echo "  ok:      $*"; }
offen() { echo "  OFFEN:   $*"; }

pruefen() {
    # grep -q beendet Pipes vorzeitig; das darf hier nicht als Fehler zählen
    set +o pipefail
    echo "### Prüfung $(TZ=Europe/Berlin date '+%d.%m.%Y %H:%M') – es wird nichts geändert"

    echo "--- SSH"
    local admin_pw root_login
    admin_pw=$(sshd -T -C "user=$ADMIN_USER,host=x,addr=203.0.113.1" | awk '$1=="passwordauthentication"{print $2}')
    root_login=$(sshd -T | awk '$1=="permitrootlogin"{print $2}')
    [ "$admin_pw" = no ] && ok "$ADMIN_USER nur mit Schlüssel" \
        || offen "$ADMIN_USER darf sich mit Passwort anmelden (sudo ohne Passwort = root)"
    [ "$root_login" = no ] && ok "kein root-Login" || offen "root-Login: $root_login"

    echo "--- Hestia"
    local api_ip twofa
    api_ip=$(v-list-sys-config json | grep -o '"API_ALLOWED_IP": *"[^"]*"' | cut -d'"' -f4)
    [ -n "$api_ip" ] && ok "API nur von: $api_ip" || offen "API ohne IP-Beschränkung"
    for u in $(v-list-users plain | cut -f1); do
        twofa=$(v-list-user "$u" json | grep -o '"TWOFA": *"[^"]*"' | cut -d'"' -f4)
        [ -n "$twofa" ] && ok "Panel-Konto $u mit 2FA" \
            || offen "Panel-Konto $u ohne 2FA (im Panel: Benutzer bearbeiten → 2FA)"
    done
    if iptables -S INPUT | grep -q -- '--dport 8083 -j ACCEPT'; then
        offen "Panel 8083 aus dem Internet erreichbar"
    else
        ok "Panel 8083 nur lokal/Tunnel"
    fi

    echo "--- Docker"
    local mit_socket=""
    for c in $(docker ps --format '{{.Names}}'); do
        case "$(docker inspect -f '{{range .Mounts}}{{.Source}} {{end}}' "$c")" in
            *docker.sock*) mit_socket="$mit_socket $c" ;;
        esac
    done
    if [ -n "$mit_socket" ]; then
        offen "Container mit Docker-Socket (= root):$mit_socket"
    else
        ok "kein Container mit Docker-Socket"
    fi
    [ -z "$(getent group docker | cut -d: -f4)" ] && ok "Gruppe docker leer" \
        || offen "Gruppe docker: $(getent group docker | cut -d: -f4)"

    echo "--- FTP"
    if systemctl is-active -q vsftpd 2>/dev/null; then
        grep -Eq '^\s*force_local_logins_ssl\s*=\s*YES' /etc/vsftpd.conf \
            && ok "FTP nur verschlüsselt" \
            || offen "FTP erlaubt unverschlüsselte Anmeldung (vor Änderungen die verwendeten Clients prüfen)"
    fi

    echo "--- PHP"
    for f in /etc/php/*/fpm/pool.d/*.conf; do
        grep -q open_basedir "$f" || offen "ohne open_basedir: $f"
    done

    echo "--- Überwachung"
    command -v aide > /dev/null && ok "AIDE installiert" || offen "keine Integritätsprüfung (AIDE)"
    systemctl is-active -q fail2ban && ok "fail2ban läuft" || offen "fail2ban läuft nicht"
}

punkt_ssh() {
    if ! grep -qE '^[[:space:]]*[^#[:space:]]' "$ADMIN_HOME/.ssh/authorized_keys" 2> /dev/null; then
        echo "Abbruch: $ADMIN_USER hat keinen SSH-Schlüssel, sonst sperrst du dich aus."
        exit 1
    fi
    # Hestia-Benutzer (SFTP mit Passwort) bleiben unberührt. Die Datei beginnt mit 10-,
    # damit sie vor 50-cloud-init.conf gelesen wird (bei sshd gilt der erste Wert).
    cat > "$SSHCONF" << EOF
# HUBIplan-Härtung (deploy/hestia/haerten.sh). Zurück: Datei löschen, systemctl reload ssh
PermitRootLogin no
Match User $ADMIN_USER,root
    PasswordAuthentication no
    KbdInteractiveAuthentication no
EOF
    chmod 644 "$SSHCONF"
    if ! sshd -t; then
        rm -f "$SSHCONF"
        echo "Abbruch: sshd-Konfiguration fehlerhaft, Änderung zurückgenommen."
        exit 1
    fi
    systemctl reload ssh
    echo "SSH gehärtet. Bitte JETZT in einem zweiten Fenster testen: ssh $ADMIN_USER@server.example.org"
    echo "Zurück: rm $SSHCONF && systemctl reload ssh"
}

punkt_api() {
    v-change-sys-config-value API_ALLOWED_IP 127.0.0.1
    echo "Hestia-API nur noch von 127.0.0.1. Zurück: v-change-sys-config-value API_ALLOWED_IP ''"
}

punkt_panel() {
    local ids
    ids=$(v-list-firewall plain | awk -F'\t' '$4=="8083" && $2=="ACCEPT" && $7!="yes" {print $1}')
    if [ -z "$ids" ]; then
        echo "Keine aktive Freigabe für 8083 gefunden, nichts zu tun."
        return
    fi
    for id in $ids; do
        v-suspend-firewall-rule "$id"
        echo "Firewall-Regel $id (8083) ausgesetzt. Zurück: v-unsuspend-firewall-rule $id"
    done
    echo "Panel jetzt über: ssh -L 8083:127.0.0.1:8083 $ADMIN_USER@server.example.org"
}

punkt_aide() {
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q aide > /dev/null
    if [ ! -f /var/lib/aide/aide.db ]; then
        echo "Erstelle die Ausgangsdatenbank (dauert einige Minuten) …"
        aideinit -y -f > /dev/null
    fi
    echo "AIDE eingerichtet; Debian prüft täglich und mailt Abweichungen an root"
    echo "(root-Mails per /etc/aliases an die zuständige Alarmadresse weiterleiten lassen)."
    echo "Zurück: apt-get remove aide"
}

case "$PUNKT" in
    "") pruefen ;;
    ssh) punkt_ssh ;;
    api) punkt_api ;;
    panel) punkt_panel ;;
    aide) punkt_aide ;;
    *)
        echo "Unbekannter Punkt: $PUNKT (ssh, api, panel, aide)"
        exit 1
        ;;
esac
