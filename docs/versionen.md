# Versionen und Verträglichkeit

HUBIplan, die Webseite (`hubiplan-website`) und die App (`hubiplan-android`) haben eigene
Versionsnummern (siehe [releases.md](releases.md)). Sie sprechen über Schnittstellen mit
**eigener** Version, die sich nicht mit jedem Release ändert:

| Schnittstelle | Version | Selbstauskunft | Wer liest |
| --- | --- | --- | --- |
| `/api/public/site/v1/` | `API_VERSION = 1` (`website/public_views.py`) | `/api/public/site/v1/instance/` | Webseite |
| `/api/app/v1/` | `api_version` 1, `min_app_version` 1 (`devices/views.py`) | `/api/app/v1/instance/` | App |
| Verbund (`peering`) | `API_VERSIONS = [1]` | `/api/peering/…` | andere Instanzen |

Die Selbstauskunft nennt `version` (laufende HUBIplan-Version, nur zur Anzeige),
`api_version` und `features`.

## Regeln

- Innerhalb von `v1` nur **hinzufügen** (Felder, Endpunkte), nie entfernen oder umdeuten.
  Webseite und App ignorieren unbekannte Felder.
- Was Webseite oder App neu nutzen sollen, bekommt einen Namen in `features`
  (`backend/core/features.py`) und eine Zeile in der Tabelle unten. Webseite und App schalten
  danach frei, statt eine HUBIplan-Version vorauszusetzen; fehlt der Name (ältere Instanz eines
  anderen Vereins), blenden sie die Funktion aus.
- `min_app_version` erhöht HUBIplan nur, wenn eine alte App Schaden anrichten würde.
- Reihenfolge beim Ausrollen: erst HUBIplan, dann Webseite
  (`deploy/release-ausrollen.sh <ziel> <tag> --webseite <tag>`).

## Funktionen

| Name | Schnittstelle | Seit | Inhalt |
| --- | --- | --- | --- |
| `rechte-stufen` | App | 2026.11.0 | Rechte je Bereich als „lesen“ (`….view`) und „bearbeiten“ (`….edit`) |
| `app-verwaltung` | App | 2026.11.0 | Verwaltung in der App (`admin/`) |
| `app-senden` | App | 2026.11.0 | Senden aus der App (`send/`) |
| `app-sprache` | App | 2026.11.0 | Sprache je Konto (`me/language/`) |
| `designpakete` | Webseite | 2026.11.0 | Designpakete (`<key>/design/<paket>/`) |
| `chronik-zeitleiste` | Webseite | 2026.11.0 | Chronik als Zeitleiste (`timeline`, `timeline_newest_first`) |
| `bildunterschriften` | Webseite | 2026.11.0 | Bildunterschriften je Text (`show_captions`) |
| `ergebnisse` | Webseite | 2026.11.0 | Wettbewerbsergebnisse (`<key>/results/`) |

„Seit 2026.11.0“ heißt: im ersten Release schon vorhanden. Die Liste `features` selbst gibt es
ab dem Release nach 2026.11.0; fehlt sie ganz, gilt der Stand von 2026.11.0.

## Verträglichkeit

Je Release von Webseite und App die mindestens nötige HUBIplan-Version. Das Release der
Webseite oder App trägt hier eine Zeile ein, wenn es eine neue Funktion braucht.

| Programm | Version | Braucht HUBIplan |
| --- | --- | --- |
| Webseite | 2026.11.0 | 2026.11.0 |
| App | 0.31.0 | 2026.11.0 |
