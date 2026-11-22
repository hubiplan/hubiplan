#!/usr/bin/env bash
# Prüft das Verhalten der Caddy-Konfiguration (Teil von scripts/test.sh), nicht nur die Syntax:
# Caddy aus deploy/web.Dockerfile mit deploy/Caddyfile.proxy (hinter nginx) und deploy/Caddyfile
# (eigenes HTTPS, hier nur über HTTP angesprochen), davor ein Echo-Dienst als Backend und als
# Vereinswebseite, der die ankommenden Kopfzeilen zurückgibt.
#
# Geprüft wird (Gesamtaudit 15.11., OPS-03):
# - hinter nginx: mit richtigem Geheimnis kommt X-Real-IP als genau ein X-Forwarded-For an,
#   ohne oder mit falschem Geheimnis die Adresse der Verbindung; ein mitgeschicktes
#   X-Forwarded-For wird verworfen
# - der geheime Kopfwert X-Hubiplan-Proxy erreicht weder Backend noch Vereinswebseite
# - /api/intern/… antwortet von außen mit 404 und erreicht das Backend nicht
# - die Sicherheits-Kopfzeilen (HSTS usw.) stehen weiter in den Antworten
# - /.well-known/security.txt geht ans Backend; die Oberfläche trägt CSP und
#   Cross-Origin-Opener-Policy (Härtung 22.11.)
#
#   scripts/pruefe-caddy.sh <Ordner mit deploy/> [docker-run-Optionen, z. B. --cpuset-cpus=…]
set -euo pipefail

SRC="$1"
shift || true
IMG=$(grep -m1 -oE '^FROM caddy:[^ ]+' "$SRC/deploy/web.Dockerfile" | cut -d' ' -f2)
ID="pruefe-caddy-$$-$RANDOM"
GEHEIM=00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff
TMP=$(mktemp -d)
aufraeumen() {
    docker rm -f "$ID-echo" "$ID-proxy" "$ID-direkt" > /dev/null 2>&1 || true
    docker network rm "$ID" > /dev/null 2>&1 || true
    rm -rf "$TMP"
}
trap aufraeumen EXIT

# Echo-Dienst: gibt die bei ihm ankommenden Kopfzeilen und den Pfad zurück
cat > "$TMP/Caddyfile" << 'EOF'
{
	auto_https off
	admin off
}
:8000 {
	respond "xff=[{http.request.header.X-Forwarded-For}] geheim=[{http.request.header.X-Hubiplan-Proxy}] pfad={path}" 200
}
EOF
chmod 644 "$TMP/Caddyfile"
# Eine kleine Oberfläche unter /srv: Ohne index.html antwortet Caddy mit 404 und ohne die
# Kopfzeilen der Oberfläche (CSP, Cross-Origin-Opener-Policy), die hier geprüft werden.
mkdir -p "$TMP/srv"
echo '<!doctype html><title>Oberfläche</title>' > "$TMP/srv/index.html"
chmod 755 "$TMP/srv"
chmod 644 "$TMP/srv/index.html"
docker network create "$ID" > /dev/null
docker run -d --name "$ID-echo" --network "$ID" --network-alias backend --network-alias website "$@" \
    -v "$TMP/Caddyfile:/etc/caddy/Caddyfile:ro" "$IMG" > /dev/null
docker run -d --name "$ID-proxy" --network "$ID" "$@" \
    -e HUBIPLAN_PROXY_GEHEIM="$GEHEIM" -v "$SRC/deploy:/etc/caddy:ro" -v "$TMP/srv:/srv:ro" \
    "$IMG" caddy run --config /etc/caddy/Caddyfile.proxy --adapter caddyfile > /dev/null
docker run -d --name "$ID-direkt" --network "$ID" "$@" \
    -e SITE_HOST=http://hubiplan.example.org -v "$SRC/deploy:/etc/caddy:ro" \
    "$IMG" caddy run --config /etc/caddy/Caddyfile --adapter caddyfile > /dev/null

# Anfrage aus einem eigenen Container (eigene Verbindungsadresse); Ausgabe: Kopfzeilen und Inhalt
anfrage() { # Ziel Pfad [Kopfzeile …]
    local ziel=$1 pfad=$2
    shift 2
    local args=()
    for k in "$@"; do args+=(--header "$k"); done
    docker run --rm --network "$ID" --entrypoint wget "$IMG" -q -S -O - \
        --header "Host: hubiplan.example.org" "${args[@]}" "http://$ziel$pfad" 2>&1 || true
}
for _ in $(seq 1 50); do
    if anfrage "$ID-proxy" /api/health/ | grep -q 'pfad=' && anfrage "$ID-direkt" /api/health/ | grep -q 'pfad='; then
        break
    fi
    sleep 0.2
done

fehler=0
erwarte() { # Beschreibung Ausgabe Muster
    if ! grep -qE -- "$3" <<< "$2"; then
        echo "Caddy: FEHLER – $1 (erwartet: $3)" >&2
        sed 's/^/    /' <<< "$2" >&2
        fehler=1
    fi
}
nicht() { # Beschreibung Ausgabe Muster
    if grep -qE -- "$3" <<< "$2"; then
        echo "Caddy: FEHLER – $1 (darf nicht vorkommen: $3)" >&2
        sed 's/^/    /' <<< "$2" >&2
        fehler=1
    fi
}

# --- Hinter nginx (Caddyfile.proxy)
a=$(anfrage "$ID-proxy" /api/health/ "X-Hubiplan-Proxy: $GEHEIM" "X-Real-IP: 203.0.113.7" \
    "X-Forwarded-For: 198.51.100.9")
erwarte "Proxy: X-Real-IP mit Geheimnis als einziges X-Forwarded-For" "$a" 'xff=\[203\.0\.113\.7\]'
erwarte "Proxy: Geheimnis nicht ans Backend" "$a" 'geheim=\[\]'
erwarte "Proxy: HSTS" "$a" 'Strict-Transport-Security: max-age=31536000'
erwarte "Proxy: nosniff" "$a" 'X-Content-Type-Options: nosniff'
nicht "Proxy: Server-Kopfzeile" "$a" '^ *Server:'

a=$(anfrage "$ID-proxy" /api/health/ "X-Real-IP: 203.0.113.7" "X-Forwarded-For: 198.51.100.9")
erwarte "Proxy: ohne Geheimnis Verbindungsadresse" "$a" 'xff=\[[0-9a-f.:]+\]'
nicht "Proxy: ohne Geheimnis kein X-Real-IP/X-Forwarded-For vom Aufrufer" "$a" '203\.0\.113\.7|198\.51\.100\.9'

a=$(anfrage "$ID-proxy" /api/health/ "X-Hubiplan-Proxy: falsch" "X-Real-IP: 203.0.113.7")
nicht "Proxy: falsches Geheimnis gilt nicht" "$a" '203\.0\.113\.7'
erwarte "Proxy: falsches Geheimnis nicht ans Backend" "$a" 'geheim=\[\]'

a=$(anfrage "$ID-proxy" /vereinsseite/ "X-Hubiplan-Proxy: $GEHEIM" "X-Real-IP: 203.0.113.7")
erwarte "Proxy: Webseite bekommt die Besucheradresse" "$a" 'xff=\[203\.0\.113\.7\]'
erwarte "Proxy: Geheimnis nicht an die Webseite" "$a" 'geheim=\[\]'

for pfad in "/api/intern/tls/?domain=x.example" /api/intern; do
    a=$(anfrage "$ID-proxy" "$pfad" "X-Hubiplan-Proxy: $GEHEIM" "X-Real-IP: 203.0.113.7")
    erwarte "Proxy: $pfad von außen 404" "$a" 'HTTP/1\.1 404'
    nicht "Proxy: $pfad erreicht das Backend nicht" "$a" 'pfad='
done

# Meldestelle (RFC 9116) kommt vom Backend, nicht aus der Oberfläche
a=$(anfrage "$ID-proxy" /.well-known/security.txt "X-Hubiplan-Proxy: $GEHEIM" "X-Real-IP: 203.0.113.7")
erwarte "Proxy: security.txt erreicht das Backend" "$a" 'pfad=/\.well-known/security\.txt'

# Oberfläche: fremde Fenster vom eigenen getrennt, CSP bleibt
a=$(anfrage "$ID-proxy" /mitglieder "X-Hubiplan-Proxy: $GEHEIM" "X-Real-IP: 203.0.113.7")
erwarte "Proxy: Oberfläche wird ausgeliefert" "$a" 'HTTP/1\.1 200'
erwarte "Proxy: Oberfläche mit Cross-Origin-Opener-Policy" "$a" 'Cross-Origin-Opener-Policy: same-origin-allow-popups'
erwarte "Proxy: Oberfläche mit CSP" "$a" "Content-Security-Policy: default-src 'self'"

# --- Eigenes HTTPS (Caddyfile), hier über HTTP angesprochen
a=$(anfrage "$ID-direkt" /api/health/ "X-Forwarded-For: 198.51.100.9" "X-Hubiplan-Proxy: $GEHEIM")
erwarte "Direkt: Verbindungsadresse als X-Forwarded-For" "$a" 'xff=\[[0-9a-f.:]+\]'
nicht "Direkt: mitgeschicktes X-Forwarded-For verworfen" "$a" '198\.51\.100\.9'
erwarte "Direkt: Kopfwert nicht ans Backend" "$a" 'geheim=\[\]'
erwarte "Direkt: HSTS" "$a" 'Strict-Transport-Security: max-age=31536000'
a=$(anfrage "$ID-direkt" "/api/intern/tls/?domain=x.example")
erwarte "Direkt: /api/intern/ von außen 404" "$a" 'HTTP/1\.1 404'
nicht "Direkt: /api/intern/ erreicht das Backend nicht" "$a" 'pfad='

if [ "$fehler" -ne 0 ]; then
    echo "Caddy: Verhalten der Konfiguration fehlerhaft (siehe oben)" >&2
    docker logs "$ID-proxy" 2>&1 | tail -5 >&2
    exit 1
fi
echo "Proxy: Caddy-Verhalten ok (Besucheradresse, Geheimnis, /api/intern/, Kopfzeilen)"
