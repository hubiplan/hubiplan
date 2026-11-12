#!/bin/bash
# Verbindungen vom Server selbst in die Docker-Netze von HUBIplan begrenzen
# (Gesamtaudit 11.11.2026, S-02 Stufe 2), siehe docs/betrieb.md „Firewall für die Docker-Netze“.
#
# Docker-Brückennetze sind vom Wirt aus geroutet: Jeder Prozess auf dem Server, auch der einer
# fremden Website, erreicht die Container direkt (an nginx und Caddy vorbei). Diese Regeln
# lassen in die HUBIplan-Netze nur noch zu:
#   - Antworten auf bestehende Verbindungen,
#   - Verbindungen über die veröffentlichten lokalen Ports (Docker leitet sie um, DNAT),
#   - Prozesse von root (Docker selbst, docker-proxy, Sicherungen, Wartung).
# Alles andere wird abgewiesen und begrenzt protokolliert (Präfix „HUBIPLAN-WIRT“).
#
# Aufruf als root auf dem Server (ohne MODUS wird nur geprüft und nichts geändert):
#   sudo bash deploy/hestia/wirt-firewall.sh                 # prüfen
#   sudo MODUS=einrichten bash deploy/hestia/wirt-firewall.sh
#   sudo MODUS=entfernen bash deploy/hestia/wirt-firewall.sh # Rückweg
#
# „einrichten“ legt /usr/local/sbin/hubiplan-wirt-firewall an und einen systemd-Timer, der
# die Regeln nach jedem Start und alle zwei Minuten anwendet (Docker legt Netze beim
# Neuerstellen mit neuen Namen an). Danach prüft das Skript selbst: Ein gewöhnlicher Benutzer
# muss die veröffentlichten Ports weiter erreichen, einen Container direkt aber nicht mehr.
# Schlägt die erste Prüfung fehl, nimmt es die Regeln sofort wieder heraus.
#
# PROJEKTE: Compose-Projekte, deren Netze geschützt werden (Standard: alle, deren Name mit
# „hubiplan“ beginnt). Gibt keine Passwörter oder Schlüssel aus.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

MODUS=${MODUS:-pruefen}
PROJEKTE=${PROJEKTE:-}
KETTE=HUBIPLAN-WIRT
ZIEL=/usr/local/sbin/hubiplan-wirt-firewall
UNIT=/etc/systemd/system/hubiplan-wirt-firewall
TESTER=nobody

[ "$(id -u)" = 0 ] || { echo "Abbruch: bitte als root starten (sudo)." >&2; exit 1; }
if [ -n "$PROJEKTE" ] && [[ ! "$PROJEKTE" =~ ^[a-z0-9_\ -]+$ ]]; then
    echo "Abbruch: PROJEKTE darf nur Projektnamen (a-z, 0-9, _ und -) enthalten." >&2
    exit 1
fi

ok() { echo "  ok:      $*"; }
offen() { echo "  OFFEN:   $*"; }
info() { echo "  info:    $*"; }

# Container der HUBIplan-Projekte
container() {
    docker ps -q | while read -r id; do
        projekt=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$id")
        if [ -n "$PROJEKTE" ]; then
            for p in $PROJEKTE; do
                if [ "$projekt" = "$p" ]; then echo "$id"; fi
            done
        else
            case "$projekt" in hubiplan*) echo "$id" ;; esac
        fi
    done || true
}

# Schnittstellen der Brückennetze dieser Container (ohne das Standardnetz „bridge“)
bruecken() {
    container | while read -r id; do
        docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{"\n"}}{{end}}' "$id"
    done | sort -u | while read -r netz; do
        if [ -z "$netz" ] || [ "$netz" = bridge ]; then continue; fi
        if [ "$(docker network inspect -f '{{.Driver}}' "$netz")" != bridge ]; then continue; fi
        name=$(docker network inspect -f '{{index .Options "com.docker.network.bridge.name"}}' "$netz")
        if [ -z "$name" ]; then
            name="br-$(docker network inspect -f '{{.Id}}' "$netz" | cut -c1-12)"
        fi
        echo "$name"
    done | sort -u || true
}

# Regeln anwenden (idempotent). Wird auch vom systemd-Timer aufgerufen; ändert nur, was
# fehlt oder nicht mehr passt, damit zwischendurch keine Lücke entsteht.
anwenden() {
    local tool=$1 br soll ist
    if ! "$tool" -w -S "$KETTE" >/dev/null 2>&1 || [ "$("$tool" -w -S "$KETTE" | wc -l)" != 6 ]; then
        "$tool" -w -N "$KETTE" 2>/dev/null || true
        "$tool" -w -F "$KETTE"
        "$tool" -w -A "$KETTE" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
        "$tool" -w -A "$KETTE" -m conntrack --ctstate DNAT -j RETURN
        "$tool" -w -A "$KETTE" -m owner --uid-owner 0 -j RETURN
        "$tool" -w -A "$KETTE" -m limit --limit 6/min -j LOG --log-prefix "HUBIPLAN-WIRT " --log-uid
        "$tool" -w -A "$KETTE" -j REJECT
    fi
    soll=$(bruecken)
    ist=$("$tool" -w -S OUTPUT | grep -- "-j $KETTE\$" | sed -n 's/.* -o \([^ ]*\) .*/\1/p' | sort -u)
    # neue Netze zuerst schützen, dann veraltete Sprünge entfernen
    for br in $soll; do
        grep -qx "$br" <<< "$ist" || "$tool" -w -I OUTPUT -o "$br" -j "$KETTE"
    done
    for br in $ist; do
        grep -qx "$br" <<< "$soll" || "$tool" -w -D OUTPUT -o "$br" -j "$KETTE"
    done
}

entfernen_regeln() {
    local tool=$1
    "$tool" -w -S OUTPUT 2>/dev/null | grep -- "-j $KETTE\$" | sed 's/^-A /-D /' | while read -r regel; do
        # shellcheck disable=SC2086
        "$tool" -w $regel
    done
    "$tool" -w -F "$KETTE" 2>/dev/null || true
    "$tool" -w -X "$KETTE" 2>/dev/null || true
}

# Eine TCP-Verbindung als gewöhnlicher Benutzer versuchen (0 = erreichbar)
erreichbar_als() {
    local benutzer=$1 adresse=$2 port=$3
    runuser -u "$benutzer" -- timeout 3 bash -c "exec 3<>/dev/tcp/$adresse/$port" 2>/dev/null
}

# Veröffentlichte lokale Ports der Container (z. B. 127.0.0.1:8110->80/tcp)
lokale_ports() {
    container | while read -r id; do
        docker port "$id" 2>/dev/null
    done | sed -n 's/.*-> *127\.0\.0\.1:\([0-9]\+\)$/\1/p' | sort -u || true
}

# Ein Container mit Adresse und offenem Port für die Gegenprobe (Datenbank)
probe_ziel() {
    container | while read -r id; do
        if docker inspect -f '{{.Config.Image}}' "$id" | grep -q postgres; then
            docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$id" \
                | awk '{print $1}'
            return
        fi
    done || true
}

selbsttest() {
    local fehler=0 port ziel
    for port in $(lokale_ports); do
        if erreichbar_als "$TESTER" 127.0.0.1 "$port"; then
            ok "Port $port (lokal veröffentlicht) für gewöhnliche Benutzer erreichbar"
        else
            offen "Port $port (lokal veröffentlicht) für gewöhnliche Benutzer NICHT erreichbar"
            fehler=1
        fi
    done
    ziel=$(probe_ziel)
    if [ -n "$ziel" ]; then
        if erreichbar_als "$TESTER" "$ziel" 5432; then
            offen "Datenbank-Container für gewöhnliche Benutzer direkt erreichbar"
            [ "${1:-}" = streng ] && fehler=2
        else
            ok "Datenbank-Container für gewöhnliche Benutzer nicht direkt erreichbar"
        fi
        if timeout 3 bash -c "exec 3<>/dev/tcp/$ziel/5432" 2>/dev/null; then
            ok "root erreicht den Datenbank-Container (Docker, Sicherungen)"
        else
            offen "root erreicht den Datenbank-Container nicht"
            fehler=1
        fi
    fi
    return "$fehler"
}

pruefen() {
    set +o pipefail
    echo "### Prüfung $(TZ=Europe/Berlin date '+%d.%m.%Y %H:%M') – es wird nichts geändert"
    echo "--- Werkzeuge"
    info "$(iptables -V 2>/dev/null || echo 'iptables fehlt')"
    if iptables -w -S DOCKER >/dev/null 2>&1; then
        ok "iptables sieht die Regeln von Docker (gleiches Verfahren)"
    else
        offen "iptables sieht keine Kette DOCKER (Docker nutzt ein anderes Verfahren?)"
    fi
    if grep -qs '"userland-proxy" *: *false' /etc/docker/daemon.json; then
        info "docker-proxy aus (veröffentlichte Ports laufen über DNAT)"
    else
        info "docker-proxy an (Standard; veröffentlichte Ports laufen über root)"
    fi
    echo "--- HUBIplan-Netze"
    local anzahl
    anzahl=$(container | wc -l)
    info "$anzahl laufende Container in den Projekten ${PROJEKTE:-hubiplan*}"
    for br in $(bruecken); do
        info "Brücke $br"
    done
    if container | while read -r id; do
        docker inspect -f '{{range .NetworkSettings.Networks}}{{.GlobalIPv6Address}}{{end}}' "$id"
    done | grep -q .; then
        offen "Container mit IPv6-Adresse: Regeln gelten nur für IPv4"
    else
        ok "keine IPv6-Adressen in den Netzen"
    fi
    for port in $(lokale_ports); do
        info "lokal veröffentlicht: 127.0.0.1:$port"
    done
    echo "--- Regeln"
    if iptables -w -S "$KETTE" >/dev/null 2>&1; then
        ok "Kette $KETTE vorhanden, $(iptables -w -S OUTPUT | grep -c -- "-j $KETTE\$") Sprünge aus OUTPUT"
    else
        offen "keine Kette $KETTE (noch nicht eingerichtet)"
    fi
    if systemctl is-enabled --quiet hubiplan-wirt-firewall.timer 2>/dev/null; then
        ok "Timer hubiplan-wirt-firewall.timer aktiv"
    else
        info "Timer hubiplan-wirt-firewall.timer nicht eingerichtet"
    fi
    echo "--- Erreichbarkeit als $TESTER"
    selbsttest || true
    echo "--- Virenprüfung (Fachfrage 4)"
    if systemctl is-active --quiet clamav-daemon 2>/dev/null; then
        ok "clamav-daemon läuft, Socket: $(find /run/clamav -maxdepth 1 -name '*.ctl' 2>/dev/null | tr '\n' ' ')"
    else
        info "clamav-daemon läuft nicht"
    fi
    if [ -f /opt/hubiplan/.env ]; then
        info "CLAMD_SOCKET_DIR in .env: $(grep -c '^CLAMD_SOCKET_DIR=.' /opt/hubiplan/.env) Eintrag"
    fi
    info "freier Arbeitsspeicher: $(free -m | awk '/^Mem:/{print $7}') MB verfügbar"
}

einrichten() {
    echo "### Einrichten $(TZ=Europe/Berlin date '+%d.%m.%Y %H:%M')"
    local quelle
    quelle=$(readlink -f "${BASH_SOURCE[0]}")
    if [ ! -f "$quelle" ]; then
        echo "Abbruch: zum Einrichten das Skript als Datei starten (nicht über bash -s)." >&2
        exit 1
    fi
    [ "$quelle" = "$ZIEL" ] || install -m 0755 "$quelle" "$ZIEL"
    cat > "$UNIT.service" <<EOF
[Unit]
Description=HUBIplan: Zugriffe vom Server in die Docker-Netze begrenzen
After=docker.service
Wants=docker.service

[Service]
Type=oneshot
Environment=MODUS=anwenden
Environment=PROJEKTE=$PROJEKTE
ExecStart=$ZIEL
EOF
    cat > "$UNIT.timer" <<'EOF'
[Unit]
Description=HUBIplan: Firewall für die Docker-Netze regelmäßig anwenden

[Timer]
OnBootSec=30s
OnUnitActiveSec=2min

[Install]
WantedBy=timers.target
EOF
    systemctl daemon-reload
    anwenden iptables
    echo "--- Selbsttest"
    if ! selbsttest streng; then
        echo "Selbsttest fehlgeschlagen: nehme die Regeln wieder heraus." >&2
        entfernen
        exit 1
    fi
    systemctl enable --now hubiplan-wirt-firewall.timer >/dev/null
    ok "eingerichtet; Rückweg: MODUS=entfernen"
}

entfernen() {
    echo "### Entfernen $(TZ=Europe/Berlin date '+%d.%m.%Y %H:%M')"
    systemctl disable --now hubiplan-wirt-firewall.timer >/dev/null 2>&1 || true
    entfernen_regeln iptables
    rm -f "$UNIT.service" "$UNIT.timer" "$ZIEL"
    systemctl daemon-reload
    ok "Regeln, Timer und Programm entfernt"
}

case "$MODUS" in
    pruefen) pruefen ;;
    anwenden) anwenden iptables ;;
    einrichten) einrichten ;;
    entfernen) entfernen ;;
    *)
        echo "Unbekannter MODUS: $MODUS (pruefen, einrichten, entfernen)" >&2
        exit 1
        ;;
esac
