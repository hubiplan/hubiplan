#!/bin/sh
# Gemeinsamer Daten-Rückweg für manuelles Zurücksetzen und fehlgeschlagenen Start.
# COMPOSE verweist noch auf die aktuelle/neue Fassung mit deren Entschlüsselungscode.
daten_rueckweg() {
    ziel_backend="$1/backend"
    if [ ! -f "$ziel_backend/manage.py" ]; then
        echo "FEHLER: Backend-Quellstand der Zielfassung fehlt." >&2
        return 1
    fi
    echo "Halte Schreiber an und prüfe den gezielten Daten-Rückweg …"
    $COMPOSE stop -t 60 backend worker beat backup || return 1
    # Kein Entrypoint mit Migrationen; vor dem Image-/Ordnertausch mit neuem Code.
    # Der Zielquellcode wird nur gelesen, weder importiert noch ausgeführt.
    $COMPOSE run -T --rm --no-deps --entrypoint python \
        -v "$ziel_backend:/rueckweg-backend:ro" backend manage.py \
        daten_verschluesseln --rueckweg-zu /rueckweg-backend || return 1
}
