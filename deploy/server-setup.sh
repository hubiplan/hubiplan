#!/bin/sh
# Läuft auf dem Server (wird von deploy.sh aufgerufen), und zwar im Ordner mit der neuen
# Fassung (ZIEL.neu). Ablauf mit Rückweg (Gesamtaudit 30.10.a, I-R01):
#   1. Images der neuen Fassung bauen; die laufende Fassung bleibt unberührt.
#      Schlägt das fehl, ändert sich am Server nichts.
#   1b. Bisherige Fassung anhalten (Datenbank läuft weiter), Migrationen als eigener
#       Schritt; schlägt das fehl, startet die bisherige Fassung wieder.
#   2. Ordner tauschen: ZIEL -> ZIEL.vorher, ZIEL.neu -> ZIEL; Images der bisherigen
#      Fassung bleiben als „:vorher“ erhalten.
#   3. Starten und auf „healthy“ warten. Klappt das nicht, automatisch zurück zur
#      vorigen Fassung (Ordner und Images).
# Von Hand zurück zur vorigen Fassung: deploy/zurueck.sh (siehe docs/betrieb.md).
# Hinweis: Datenbank-Migrationen der neuen Fassung bleiben beim Rückweg angewendet;
# HUBIplan-Migrationen sind so gebaut, dass die vorige Fassung damit weiterläuft.
set -eu

ZIEL="${ZIEL:-$(pwd)}"
NEU="$(pwd)"
if [ -e "$ZIEL.datenschluesselwechsel/status" ] || [ -d "$ZIEL.datenschluesselwechsel/offen" ]; then
    echo "Schlüsselwechsel-Wartung offen; zuerst mit dem bestehenden Quellstand fortsetzen." >&2
    exit 1
fi
SETUP_SPERRE="$ZIEL.sperre"
DEPLOY_SPERRE_GEHALTEN=0
# Auch ältere deploy.sh-Fassungen halten diese Sperre bereits, ohne ein neues
# Umgebungsflag zu kennen. Nur der passende entpackte Zielstand darf sie übernehmen.
if [ "$NEU" = "$ZIEL.neu" ] && [ -f "$SETUP_SPERRE/lauf" ] && [ -f "$NEU/.fassung" ]; then
    SPERR_FASSUNG=$(cut -d ' ' -f 1 "$SETUP_SPERRE/lauf")
    QUELL_FASSUNG=$(cat "$NEU/.fassung")
    case "$SPERR_FASSUNG" in
        ''|*[!0-9a-f]*) ;;
        *)
            if [ "${#SPERR_FASSUNG}" -ge 7 ]; then
                case "$QUELL_FASSUNG" in "$SPERR_FASSUNG"*) DEPLOY_SPERRE_GEHALTEN=1;; esac
            fi ;;
    esac
fi
if [ "$DEPLOY_SPERRE_GEHALTEN" != 1 ]; then
    mkdir "$SETUP_SPERRE" 2>/dev/null || { echo "Ein anderer Betriebslauf hält die Sperre." >&2; exit 1; }
    trap 'rm -f "$SETUP_SPERRE/lauf"; rmdir "$SETUP_SPERRE"' EXIT
    echo "Manuelles Setup" > "$SETUP_SPERRE/lauf"
fi

# Beim ersten Mal: .env mit zufälligen Geheimnissen anlegen (nur auf dem Server)
if [ ! -f .env ]; then
    echo "Lege .env mit neuen Geheimnissen an …"
    umask 077
    cat > .env <<EOF
SITE_HOST=${SITE_HOST:-$(hostname -f)}
${HUBIPLAN_HINTER_PROXY:+HUBIPLAN_HINTER_PROXY=$HUBIPLAN_HINTER_PROXY}
${WEB_PORT:+WEB_PORT=$WEB_PORT}
DJANGO_SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n/+=')
POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d '\n/+=')
EOF
fi
# Neue Einträge späterer Versionen ergänzen, ohne vorhandene zu ändern
if ! grep -q '^BACKUP_PASSPHRASE=' .env; then
    echo "Erzeuge Passphrase für die Backups …"
    echo "BACKUP_PASSPHRASE=$(openssl rand -base64 48 | tr -d '\n/+=')" >> .env
fi
if ! grep -q '^BACKUP_HMAC_KEY=' .env; then
    echo "Erzeuge Schlüssel für die Backup-Prüfsummen …"
    echo "BACKUP_HMAC_KEY=$(openssl rand -base64 48 | tr -d '\n/+=')" >> .env
fi
if ! grep -q '^MFA_ENCRYPTION_KEY=' .env; then
    echo "Erzeuge Schlüssel für die 2FA-Geheimnisse …"
    # Fernet-Schlüssel: 32 Byte, URL-sicheres Base64
    echo "MFA_ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '+/' '-_')" >> .env
fi
if ! grep -q '^REDIS_PASSWORD=' .env; then
    echo "Erzeuge Passwort für Redis …"
    echo "REDIS_PASSWORD=$(openssl rand -base64 32 | tr -d '\n/+=')" >> .env
fi
if ! grep -q '^APP_DB_PASSWORD=' .env; then
    echo "Erzeuge Passwort für die Datenbankrolle der Anwendung …"
    echo "APP_DB_PASSWORD=$(openssl rand -base64 32 | tr -d '\n/+=')" >> .env
fi
# Öffentlicher Backup-Schlüssel (age1…), mitgegeben von deploy.sh
if [ -n "${BACKUP_PUBLIC_KEY:-}" ]; then
    case "$BACKUP_PUBLIC_KEY" in
        age1*) ;;
        *) echo "Abbruch: BACKUP_PUBLIC_KEY ist kein age-Schlüssel (age1…)." >&2; exit 1 ;;
    esac
    umask 077
    grep -v '^BACKUP_PUBLIC_KEY=' .env > .env.neu || true
    echo "BACKUP_PUBLIC_KEY=$BACKUP_PUBLIC_KEY" >> .env.neu
    mv .env.neu .env
    echo "Öffentlicher Backup-Schlüssel gesetzt."
fi
chmod 600 .env
if ! grep -q '^BACKUP_PUBLIC_KEY=age1' .env; then
    echo "HINWEIS: Kein öffentlicher Backup-Schlüssel. Backups nutzen noch die Passphrase"
    echo "         aus der .env, die auch ein Angreifer auf dem Server lesen könnte."
    echo "         Einrichten: siehe docs/betrieb.md, Abschnitt Backups."
fi

# Compose-Projekt wie bisher nach dem Zielordner benennen (Volumes hubiplan_…)
PROJEKT=$(grep '^COMPOSE_PROJECT_NAME=' .env | cut -d= -f2 || true)
PROJEKT=${PROJEKT:-$(basename "$ZIEL")}
DATEIEN="-f docker-compose.server.yml"
# Hinter einem vorhandenen Webserver (Echtserver mit HestiaCP): Caddy nur auf
# 127.0.0.1:WEB_PORT, HTTPS macht der vorgeschaltete Webserver.
if grep -q '^HUBIPLAN_HINTER_PROXY=1' .env; then
    DATEIEN="$DATEIEN -f docker-compose.proxy.yml"
fi
# Virenprüfung mit dem clamd des Rechners (Socket-Ordner in der .env, z. B. /run/clamav)
if grep -q '^CLAMD_SOCKET_DIR=.' .env; then
    DATEIEN="$DATEIEN -f docker-compose.clamav.yml"
fi
# Selbstupdate (konzepte/selbstupdate.md): Backend darf Aufträge in einen eigenen Ordner legen
SELBSTUPDATE=""
if grep -q '^HUBIPLAN_SELBSTUPDATE=1' .env; then
    SELBSTUPDATE=1
    DATEIEN="$DATEIEN -f docker-compose.selbstupdate.yml"
    AKTUALISIERUNG_DIR=$(grep '^AKTUALISIERUNG_DIR=' .env | cut -d= -f2 || true)
    AKTUALISIERUNG_DIR=${AKTUALISIERUNG_DIR:-/opt/hubiplan-aktualisierung}
    mkdir -p "$AKTUALISIERUNG_DIR"
    chown 1000:1000 "$AKTUALISIERUNG_DIR"
    chmod 750 "$AKTUALISIERUNG_DIR"
fi
# Schnellere Gesundheitsprüfung beim Start (healthcheck.start_interval braucht Docker
# Engine 25, API 1.44; ältere lehnen die Angabe ab)
API=$(docker version --format '{{.Server.APIVersion}}' 2> /dev/null || echo 0)
if [ "${API%%.*}" -gt 1 ] 2> /dev/null || { [ "${API%%.*}" = 1 ] && [ "${API#*.}" -ge 44 ] 2> /dev/null; }; then
    DATEIEN="$DATEIEN -f docker-compose.schnellstart.yml"
fi
COMPOSE="docker compose -p $PROJEKT $DATEIEN"
. ./deploy/daten-rueckweg.sh

# Backup-Verzeichnis außerhalb der Docker-Volumes (gehört dem postgres-Benutzer, UID 70)
BACKUP_DIR=$(grep '^BACKUP_DIR=' .env | cut -d= -f2)
BACKUP_DIR=${BACKUP_DIR:-/opt/hubiplan-backups}
mkdir -p "$BACKUP_DIR"
chown 70:70 "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# Hauptschlüssel für die Verschlüsselung der Daten (core/crypto.py): eigene Datei außerhalb
# des Programmordners (der beim Ausrollen getauscht wird) und nicht in der .env. Lesbar nur
# für die App (UID 1000) und das Backup (Gruppe 70, legt eine mit dem öffentlichen
# Backup-Schlüssel verschlüsselte Kopie neben die Backups). Wird nie überschrieben.
DATA_KEY_FILE=$(grep '^DATA_KEY_FILE=' .env | cut -d= -f2 || true)
if [ -z "$DATA_KEY_FILE" ]; then
    DATA_KEY_FILE="$ZIEL-geheim/datenschluessel"
    echo "DATA_KEY_FILE=$DATA_KEY_FILE" >> .env
fi
if [ ! -s "$DATA_KEY_FILE" ]; then
    echo "Erzeuge Hauptschlüssel für die Datenverschlüsselung ($DATA_KEY_FILE) …"
    echo "WICHTIG: Ohne diesen Schlüssel sind Daten und Backups nicht lesbar. Kopie sichern"
    echo "         (docs/betrieb.md, Abschnitt Verschlüsselung)."
    mkdir -p "$(dirname "$DATA_KEY_FILE")"
    chmod 711 "$(dirname "$DATA_KEY_FILE")"
    (umask 077 && openssl rand -base64 32 | tr '+/' '-_' > "$DATA_KEY_FILE.neu")
    mv "$DATA_KEY_FILE.neu" "$DATA_KEY_FILE"
fi
chown 1000:70 "$DATA_KEY_FILE"
chmod 440 "$DATA_KEY_FILE"

# Selbst gebaute Images (nicht die per Digest festgelegten Postgres/Redis)
EIGENE=$($COMPOSE config --images | grep -v '@sha256:' | sort -u)

ALTE_IDS=""
images_sichern() {
    # Laufende Fassung als „:vorher“ merken (vor dem Bauen, das die Namen neu vergibt)
    for img in $EIGENE; do
        # Die bisherige „:vorher“-Fassung wird gleich namenlos: am Ende gezielt löschen
        alt=$(docker image inspect -f '{{.Id}}' "${img%%:*}:vorher" 2>/dev/null || true)
        [ -n "$alt" ] && ALTE_IDS="$ALTE_IDS $alt"
        if docker image inspect "$img" > /dev/null 2>&1; then
            docker tag "$img" "${img%%:*}:vorher"
        fi
    done
}

images_zurueck() {
    for img in $EIGENE; do
        if docker image inspect "${img%%:*}:vorher" > /dev/null 2>&1; then
            docker tag "${img%%:*}:vorher" "$img"
        fi
    done
}

starten() {
    $COMPOSE up -d --remove-orphans --wait --wait-timeout 300 || return 1
    # Compose ersetzt einen Container nicht immer, obwohl sein Image neu gebaut wurde
    # (auf dem Echtserver beobachtet). Container, die noch ein älteres Image nutzen als
    # ihr Tag, gezielt neu erstellen. Sonst käme z. B. ein neues Frontend nicht an.
    VERALTET=""
    for service in $($COMPOSE config --services); do
        container=$($COMPOSE ps -q "$service" | head -n1)
        [ -n "$container" ] || continue
        name=$(docker inspect -f '{{.Config.Image}}' "$container")
        laeuft=$(docker inspect -f '{{.Image}}' "$container")
        aktuell=$(docker image inspect -f '{{.Id}}' "$name" 2>/dev/null || true)
        if [ -n "$aktuell" ] && [ "$laeuft" != "$aktuell" ]; then
            VERALTET="$VERALTET $service"
        fi
    done
    if [ -n "$VERALTET" ]; then
        echo "Neu erstellen (altes Image):$VERALTET"
        # shellcheck disable=SC2086
        $COMPOSE up -d --no-deps --force-recreate --wait --wait-timeout 300 $VERALTET || return 1
    fi
}

# Commit der Fassung für den Quellcode-Link auf /lizenz (AGPL § 13), aus deploy.sh
if [ -f .fassung ]; then
    mkdir -p frontend/public/lizenzen
    cp .fassung frontend/public/lizenzen/fassung.txt
fi
# Versionsnummer aus deploy.sh (docs/releases.md) für Oberfläche und Backend
if [ -f .version ]; then
    mkdir -p frontend/public/lizenzen
    cp .version frontend/public/lizenzen/version.txt
    cp .version backend/hubiplan_version.txt
fi

# 1. Bauen, während die bisherige Fassung weiterläuft
images_sichern
if ! $COMPOSE build; then
    echo "FEHLER: Bauen fehlgeschlagen. Die laufende Fassung bleibt unverändert." >&2
    images_zurueck
    exit 1
fi

# 1b. Migrationen als eigener Schritt, bevor die neue Fassung startet. Vorher halten
#     Backend, Worker, Beat und Backup der bisherigen Fassung an: Laufende Abfragen (z. B. der
#     minütliche Mailabruf im Worker) halten sonst Tabellensperren, und ALTER TABLE wartet
#     endlos (Produktionsserver 31.10.2026). Caddy (web) läuft weiter: Oberfläche und Bilder
#     (auch die der Vereinswebseite) bleiben erreichbar, API-Aufrufe bekommen die Seite
#     „Wird gerade aktualisiert“, die die Oberfläche von selbst wiederholt
#     (konzepte/ausfallzeiten-ausrollen.md). Datenbank und Redis laufen weiter.
#     Stehen keine Migrationen an, entfällt das Anhalten.
#     Schlägt das Migrieren fehl, startet die bisherige Fassung wieder (Migrationen sind
#     so geschrieben, dass sie mit schon angewendeten weiterläuft, siehe docs/betrieb.md).
#     Jede Migration wartet höchstens MIGRATE_LOCK_TIMEOUT auf eine Sperre und wird dann
#     (bis zu dreimal) neu versucht, statt bis zum Gesamt-Timeout zu hängen.
MIGRATE_TIMEOUT=$(grep '^MIGRATE_TIMEOUT=' .env | cut -d= -f2 || true)
MIGRATE_TIMEOUT=${MIGRATE_TIMEOUT:-3600}
MIGRATE_LOCK_TIMEOUT=$(grep '^MIGRATE_LOCK_TIMEOUT=' .env | cut -d= -f2 || true)
MIGRATE_LOCK_TIMEOUT=${MIGRATE_LOCK_TIMEOUT:-30s}
case "$MIGRATE_LOCK_TIMEOUT" in
    *[!0-9a-z]*|'') echo "Abbruch: MIGRATE_LOCK_TIMEOUT ungültig." >&2; exit 1 ;;
esac
ANHALTEN="backend worker beat backup"
# Laufen Datenbank und Redis schon, nicht anfassen (--no-deps)
OHNE_ABH=""
if [ -n "$($COMPOSE ps -q --status running postgres)" ] \
    && [ -n "$($COMPOSE ps -q --status running redis)" ]; then
    OHNE_ABH="--no-deps"
fi
# Stehen keine Migrationen an, läuft die bisherige Fassung bis zum Austausch weiter
# (die Prüfung liest nur). Im Zweifel (Fehler bei der Prüfung) wird angehalten.
# shellcheck disable=SC2086,SC2016
if [ -n "$OHNE_ABH" ] && $COMPOSE run -T --rm --no-deps --entrypoint sh backend -c \
    'DATABASE_URL="${MIGRATE_DATABASE_URL:-$DATABASE_URL}" DATABASE_APP_ROLE= python manage.py migrate --check --noinput > /dev/null 2>&1'; then
    echo "Keine offenen Migrationen, die bisherige Fassung läuft bis zum Austausch weiter."
    ANHALTEN=""
fi
ANGEHALTEN=""
for service in $ANHALTEN; do
    ANGEHALTEN="$ANGEHALTEN $($COMPOSE ps -q --status running "$service" 2> /dev/null || true)"
done
ANGEHALTEN=$(echo $ANGEHALTEN)

wieder_starten() {
    if [ -n "$ANGEHALTEN" ]; then
        echo "Starte die bisherige Fassung wieder …" >&2
        # shellcheck disable=SC2086
        docker start $ANGEHALTEN > /dev/null || true
    fi
}

if [ -n "$ANGEHALTEN" ]; then
    echo "Halte die bisherige Fassung an ($ANHALTEN) …"
    # Der Worker darf laufende Aufträge beenden
    # shellcheck disable=SC2086
    if ! docker stop -t 60 $ANGEHALTEN > /dev/null; then
        echo "FEHLER: Anhalten fehlgeschlagen." >&2
        images_zurueck
        wieder_starten
        exit 1
    fi
fi
echo "Migrationen (höchstens $MIGRATE_TIMEOUT s, Sperren höchstens $MIGRATE_LOCK_TIMEOUT) …"
migrieren() {
    # shellcheck disable=SC2086
    timeout "$MIGRATE_TIMEOUT" $COMPOSE run -T --rm $OHNE_ABH --name "$PROJEKT-migration" \
        -e MIGRATE_VERBOSITY=2 -e "MIGRATE_PGOPTIONS=-c lock_timeout=$MIGRATE_LOCK_TIMEOUT" \
        backend true < /dev/null
}
VERSUCH=1
until migrieren; do
    rc=$?
    docker rm -f "$PROJEKT-migration" > /dev/null 2>&1 || true
    # Gesamt-Timeout (124) nicht wiederholen
    if [ "$VERSUCH" -ge 3 ] || [ "$rc" = 124 ]; then
        echo "FEHLER: Migrationen fehlgeschlagen. Die bisherige Fassung läuft weiter." >&2
        images_zurueck
        wieder_starten
        exit 1
    fi
    VERSUCH=$((VERSUCH + 1))
    echo "Migrationen: neuer Versuch ($VERSUCH von 3) in 5 s …" >&2
    sleep 5
done

# 2. Ordner tauschen (bei einem Ausrollen in denselben Ordner entfällt das)
if [ "$NEU" != "$ZIEL" ]; then
    rm -rf "$ZIEL.vorher"
    if [ -d "$ZIEL" ]; then
        mv "$ZIEL" "$ZIEL.vorher"
    fi
    mv "$NEU" "$ZIEL"
    cd "$ZIEL"
fi

# 2b. Ohne Migrationen läuft das bisherige Backend noch: Neues Backend daneben starten, auf
#     „healthy“ warten und erst dann das alte sanft stoppen (laufende Anfragen werden fertig).
#     Caddy und die Vereinswebseite finden beide unter „backend“ (Docker-DNS), es gibt also
#     keine Lücke. Klappt das nicht, bleibt das alte Backend, und starten() unten ersetzt es
#     wie bisher (mit Rückweg bei Fehler). Container heißen danach abwechselnd …-backend-1
#     und …-backend-2; Befehle daher immer mit „docker compose exec backend“.
ueberlappend_tauschen() {
    [ -z "$ANGEHALTEN" ] || return 0
    alt=$($COMPOSE ps -q --status running backend)
    [ "$(echo "$alt" | wc -w)" = 1 ] || return 0
    echo "Starte das neue Backend neben dem bisherigen …"
    $COMPOSE up -d --no-deps --no-recreate --scale backend=2 backend < /dev/null || return 1
    neu=$($COMPOSE ps -q backend | grep -v "^$alt" | head -n1)
    [ -n "$neu" ] || return 1
    i=0
    while [ "$i" -lt 300 ]; do
        zustand=$(docker inspect -f '{{.State.Health.Status}}' "$neu" 2> /dev/null || echo weg)
        case "$zustand" in
            healthy) break ;;
            unhealthy|weg) i=300; break ;;
        esac
        i=$((i + 1))
        sleep 1
    done
    if [ "$zustand" != healthy ]; then
        echo "Neues Backend wird nicht gesund ($zustand); weiter wie bisher." >&2
        docker logs --tail 40 "$neu" >&2 2>&1 || true
        docker rm -f "$neu" > /dev/null 2>&1 || true
        return 1
    fi
    echo "Neues Backend gesund, stoppe das bisherige …"
    docker stop -t 35 "$alt" > /dev/null || true
    docker rm "$alt" > /dev/null || true
}
if ! ueberlappend_tauschen; then
    echo "Überlappender Tausch nicht möglich, Backend wird neu gestartet." >&2
fi

# 2c. Caddy (web) für sich allein tauschen. Im gemeinsamen „up“ unten erstellte Compose ihn
#     zwar sofort neu, startete ihn aber erst mit Worker, Beat und Backup zusammen: Auf dem
#     Testserver war so 13 s lang kein Caddy da (Messung 08.11.2026). Allein sind es 1–3 s.
#     Schlägt es fehl, versucht starten() es erneut (mit Rückweg).
echo "Tausche Caddy (web) …"
$COMPOSE up -d --no-deps web < /dev/null || echo "Caddy-Tausch fehlgeschlagen; weiter mit starten()." >&2

# 3. Starten; bei Fehler zurück zur vorigen Fassung
if ! starten; then
    echo "FEHLER: Die neue Fassung startet nicht. Zurück zur vorigen Fassung …" >&2
    $COMPOSE logs --tail 40 backend >&2 || true
    if [ -d "$ZIEL.vorher" ]; then
        # Auch gestartete Worker können vor dem fehlgeschlagenen Healthcheck bereits
        # Namen verschlüsselt haben. Mit der neuen Fassung gezielt zurückführen.
        if ! daten_rueckweg "$ZIEL.vorher"; then
            echo "FEHLER: Daten-Rückweg fehlgeschlagen. Alte Fassung bleibt angehalten." >&2
            exit 1
        fi
        rm -rf "$ZIEL.fehler"
        mv "$ZIEL" "$ZIEL.fehler"
        mv "$ZIEL.vorher" "$ZIEL"
        # .env der neuen Fassung behalten: sie enthält höchstens neue Einträge
        cp -p "$ZIEL.fehler/.env" "$ZIEL/.env"
        cd "$ZIEL"
        images_zurueck
        if starten; then
            echo "Vorige Fassung läuft wieder. Die fehlerhafte liegt in $ZIEL.fehler." >&2
        else
            echo "FEHLER: Auch die vorige Fassung startet nicht – bitte von Hand prüfen." >&2
        fi
    fi
    exit 1
fi

# Nur eigene alte Images löschen, die jetzt keinen Namen mehr haben; die „:vorher“-Fassung
# bleibt für den Rückweg. Kein „docker image prune“: Der Docker-Dienst kann mit anderen
# Projekten geteilt sein (Gesamtaudit 01.11., GA-I03).
for id in $ALTE_IDS; do
    if [ -z "$(docker image inspect -f '{{join .RepoTags ""}}' "$id" 2>/dev/null)" ]; then
        docker image rm "$id" > /dev/null 2>&1 || true
    fi
done
rm -rf "$ZIEL.fehler"

# Aktualisierer für das Selbstupdate ein- oder ausschalten (systemd-Timer je Programmordner).
# Das Skript wird als neue Datei angelegt (install), damit ein gerade laufender Aktualisierer,
# der dieses Ausrollen selbst angestoßen hat, ungestört zu Ende läuft.
INSTANZ="hubiplan-aktualisierer@$(basename "$ZIEL").timer"
if command -v systemctl > /dev/null 2>&1 && [ "$(dirname "$ZIEL")" = /opt ]; then
    if [ -n "$SELBSTUPDATE" ]; then
        for prog in git ssh-keygen; do
            command -v "$prog" > /dev/null 2>&1 ||
                echo "WARNUNG: Für das Selbstupdate fehlt $prog auf dem Server." >&2
        done
        install -d -m 755 /usr/local/lib/hubiplan
        install -m 755 deploy/aktualisierer/aktualisierer.sh /usr/local/lib/hubiplan/aktualisierer.sh
        install -m 644 deploy/aktualisierer/hubiplan-aktualisierer@.service \
            deploy/aktualisierer/hubiplan-aktualisierer@.timer /etc/systemd/system/
        systemctl daemon-reload
        systemctl enable --now "$INSTANZ" > /dev/null 2>&1 &&
            echo "Selbstupdate eingeschaltet ($INSTANZ)." ||
            echo "WARNUNG: Selbstupdate-Timer $INSTANZ ließ sich nicht einschalten." >&2
    elif systemctl is-enabled "$INSTANZ" > /dev/null 2>&1; then
        systemctl disable --now "$INSTANZ" > /dev/null 2>&1 || true
        echo "Selbstupdate ausgeschaltet ($INSTANZ)."
    fi
fi
$COMPOSE ps
