# API für andere Programme

Über diese Schnittstelle lesen Programme Dritter Daten einer Einheit: die Software eines
Dachverbands, eine eigene Webseite, eine Anzeigetafel, ein Skript. Umgesetzt sind **Stufe 0**
(die Schnittstelle der Vereinswebseite als offene Daten beschrieben, siehe unten) und **Stufe 1**
(API-Zugänge mit Schlüssel, Lesen ohne Personendaten). Schreiben, Mitgliederdaten für Verbände,
Benachrichtigungen und die Anmeldung im Namen einer Person sind spätere Stufen.

## Kurz

| | |
| --- | --- |
| Adresse | `https://<Instanz>/api/partner/v1/` |
| Beschreibung | `https://<Instanz>/api/partner/v1/openapi.json` (OpenAPI 3, ohne Anmeldung), Kopie im Repo: [api-openapi.json](api-openapi.json) |
| Anmeldung | Kopfzeile `Authorization: Bearer hpk_…` |
| Wer vergibt | Vorstand der Einheit unter Einstellungen › API-Zugänge (`/einstellungen/api`) |
| Voraussetzung | Modul `api` („API für andere Programme“, anfangs aus) und Zusatzrecht `api.manage` |
| Abschalten | Betreiber: `HUBIPLAN_API=false` (dann 404 für alles unter `/api/partner/` und die Verwaltung) |

Code: App `backend/partnerapi/` (`models.py` Zugang, `auth.py` Schlüsselprüfung, `scopes.py`
Bereiche, `views.py` Aufrufe für Dritte, `manage_views.py` Verwaltung, `openapi.py` Beschreibung).
Oberfläche: `frontend/src/pages/settings/ApiAccessPage.tsx`.

## Zugang und Schlüssel

Ein API-Zugang (`ApiAccess`) gehört zu genau einer Einheit (Verband oder Verein) und kann auf
eine Untereinheit begrenzt sein; dann sieht er nur diese und die Einheiten darunter. Die Einheit
steht nie in der Adresse, sie ergibt sich aus dem Schlüssel.

- **Schlüssel** `hpk_` + 43 Zeichen. Gespeichert wird nur die SHA-256-Prüfsumme und die letzten
  vier Zeichen zur Anzeige. Der Schlüssel steht genau einmal in der Antwort: beim Anlegen und
  bei „Neuen Schlüssel erzeugen“.
- **Wechsel:** Nach „Neuen Schlüssel erzeugen“ gilt der bisherige noch sieben Tage.
- **Ablauf:** Pflicht, höchstens 366 Tage. 30 Tage vorher bekommen alle Konten mit `api.manage`
  einmal eine Mail (Aufgabe `partnerapi.tasks.remind_expiring`, täglich). Verlängern setzt die
  Erinnerung zurück.
- **Ruhen:** 90 Tage ohne Abruf schalten den Zugang ab (`access_idle`); „Wieder einschalten“
  nimmt ihn wieder in Betrieb.
- **Erlaubte Adressen:** wahlweise bis zu 20 IP-Adressen oder Netze. Geprüft wird die echte
  Adresse des Aufrufers hinter dem eigenen Proxy.
- **Aus fremden Webseiten aufrufbar** (CORS): nur ohne `termine.mitglieder` und
  `statistik.lesen`, weil der Schlüssel dann im Quelltext der fremden Webseite steht.
- **Grenzen:** 600 Abrufe je Stunde und Zugang, 300 je Minute und Adresse; darüber 429 mit
  `Retry-After`. Höchstens 50 Zugänge je Einheit.
- **Frischer zweiter Faktor** (`accounts/step_up.py`) für Anlegen, Schlüsselwechsel und
  Wiedereinschalten. `api.manage` setzt „Einstellungen“ voraus und wird nie automatisch
  vergeben, auch nicht an neue Vorstandsrollen (`NOT_AUTOMATIC`).
- **Protokoll:** Anlegen, Ändern, Schlüsselwechsel, Wiedereinschalten und Löschen stehen im
  Änderungsprotokoll; zu Anlegen und Schlüsselwechsel geht eine Mail an alle mit `api.manage`.
  Am Zugang stehen letzter Abruf, dessen Adresse und die Zahl der Abrufe.
- Der Schlüssel gilt nur unter `/api/partner/`, nirgends sonst in HUBIplan.

Die Tabelle ist je Einheit zeilengesichert (`partnerapi/migrations/0002_rls.py`). Zugänge gehen
bewusst nicht in die Datenübernahme: Nach einem Umzug vergibt die Einheit neue Schlüssel.

## Bereiche

Ein Zugang darf nur, was einzeln angekreuzt ist. Ein Bereich steht nur zur Wahl, wenn das Modul
dazu eingeschaltet ist; wird das Modul später ausgeschaltet, antwortet der Aufruf mit
`missing_scope`.

| Bereich | Aufruf | Inhalt | Modul |
| --- | --- | --- | --- |
| (immer) | `GET /` | Selbstauskunft: Einheit, Bereiche, Ablauf, Grenzen | – |
| `einheit.lesen` | `GET unit/`, `unit/logo`, `units/` | Name, Anschrift, Kontakt, Logo; Untereinheiten als Baum | – |
| `termine.lesen` | `GET events/` | Termine „nach außen öffentlich“ als Einzeltermine, Serien aufgelöst (`from`, `to`, `unit`, `changed_since`, `limit`, `cursor`) | `events` |
| `termine.mitglieder` | `GET events/` | zusätzlich Termine für Mitglieder; „nur Vorstand“ nie | `events` |
| `statistik.lesen` | `GET statistics/census/` | Stichtagsstatistik: Anzahlen nach Alter, Geschlecht, Untereinheit (`date`, `ages`, `counting`), keine Personen, keine Wohnorte | `members` |
| `vorstand.lesen` | `GET board/` | Rollen mit „auf der Webseite zeigen“ und Funktionsadresse; Namen nur, wenn die öffentliche Webseite sie zeigt | – |
| `ergebnisse.lesen` | `GET results/`, `results/<id>/` | auf der Webseite veröffentlichte Wettbewerbe und Wertungen, im selben Umfang wie dort | `competitions` |
| `neuigkeiten.lesen` | `GET news/` | auf der Webseite gezeigte Beiträge der eigenen Kanäle | `social` |
| `dokumente.lesen` | `GET documents/` | auf der Webseite veröffentlichte Dokumente und Presseberichte | `website` |

Ein Zugang für eine Untereinheit bekommt nur `einheit.lesen`, die Termine und die Statistik.
„Veröffentlicht“ heißt: Die Webseite der Einheit ist öffentlich und zeigt den Inhalt; sonst
kommt `published: false` mit leerer Liste. Zu- und Absagen, Teilnehmende, Namen einzelner
Mitglieder, Kontaktdaten von Personen, Kasse und Bank gibt es in Stufe 1 nirgends.

## Fehler

Antworten mit `application/problem+json` (RFC 9457): `type`, `title`, `status`, `detail`, `code`.

| `code` | Status | Bedeutung |
| --- | --- | --- |
| `invalid_key` | 401 | Schlüssel fehlt oder ist unbekannt (auch: Modul aus) |
| `access_expired` | 401 | Zugang abgelaufen |
| `access_idle` | 401 | Zugang ruht nach 90 Tagen ohne Abruf |
| `ip_not_allowed` | 403 | Aufruf von einer nicht erlaubten Adresse |
| `missing_scope` | 403 | Bereich nicht vergeben (`scope` nennt ihn) |
| `too_many_requests` | 429 | Grenze erreicht, `Retry-After` beachten |
| `not_found` | 404 | gibt es nicht oder ist nicht veröffentlicht |
| `invalid_request` | 400 | Angabe ungültig (`errors` nennt das Feld) |

## Zusage zur Stabilität

Innerhalb von `v1` kommen nur Felder, Aufrufe und Bereiche hinzu; nichts fällt weg oder ändert
seine Bedeutung. Was wegfallen soll, wird zwölf Monate vorher in den Änderungshinweisen
angekündigt. Programme ignorieren unbekannte Felder. Feldnamen sind englisch, Kennungen von
Einheiten sind UUIDs, Zeiten stehen in ISO 8601 mit Zeitzone. Die Formate in
`partnerapi/views.py` sind der Vertrag; `tests/test_partnerapi.py` prüft, dass die Kopie
[api-openapi.json](api-openapi.json) zum Code passt. Nach Änderungen:

```bash
cd backend && python manage.py api_openapi ../docs/api-openapi.json
```

## Beispiel

```bash
curl -H "Authorization: Bearer hpk_…" \
  "https://verein.example/api/partner/v1/events/?from=2027-01-01&to=2027-03-31"
```

## Stufe 0: Offene Daten der Vereinswebseite

Was eine Einheit auf ihrer öffentlichen Webseite zeigt, liefert HUBIplan schon lange ohne
Anmeldung unter `/api/public/site/v1/<Kennung>/…` aus (`backend/website/public_views.py`). Die
Kennung der Webseite ist kein Geheimnis; `GET /api/public/site/v1/resolve/?host=<Domain>` nennt
sie zu einer Domain. Auch Dritte dürfen diese Schnittstelle lesen. Es gilt:

- Nur lesen, nur was die Webseite zeigt; im Wartungsmodus oder ohne öffentliche Webseite
  kommen keine Inhalte.
- Dieselbe Zusage wie in [versionen.md](versionen.md): innerhalb von `v1` wird nur hinzugefügt.
  Die Formate folgen aber der Vereinswebseite (`hubiplan-website`) und sind nicht Feld für Feld
  beschrieben. Wer ein festes, beschriebenes Format braucht, nimmt die API mit Schlüssel oben.
- 600 Abrufe je Minute und Adresse, darüber 429. Bitte Antworten zwischenspeichern.
- Für Kalender gibt es zusätzlich `events.ics` (iCalendar).

| Aufruf (unter `/api/public/site/v1/<Kennung>/`) | Inhalt |
| --- | --- |
| `` (leer) | Grunddaten, Menü, Begrüßung, was es auf der Webseite gibt |
| `events/`, `events.ics` | öffentliche Termine |
| `board/` | Vorstand und Ämter mit Veröffentlichung |
| `units/`, `units/<Kurzname>/` | Untereinheiten mit eigener Seite |
| `pages/<Kurzname>/` | Textseiten |
| `results/`, `results/<Kennung>/`, `results/series/<Kennung>/` | Wettbewerbe, Wertungen, Reihen |
| `honors/` | Würden und frühere Träger |
| `galleries/`, `galleries/<Kurzname>/` | Fotoalben |
| `documents/` | Dokumente und Pressespiegel |
| `posts/` | Beiträge aus den eigenen Kanälen |
| `bookings/`, `bookings.ics` | Belegung mit „auf der Webseite“ |
| `imprint/` | Impressum und Datenschutzhinweise |
| `search/?q=…` | Suche in den öffentlichen Texten |

`GET /api/public/site/v1/instance/` nennt Version und Funktionen der Instanz.

## Spätere Stufen

| Stufe | Inhalt |
| --- | --- |
| 2 | Verbandsmeldung, Mitglieder, Ehrungen, Qualifikationen lesend, nur mit Geschäftspartner und bestätigter Rechtsgrundlage; Benachrichtigungen (Webhooks) |
| 3 | Schreiben: Termine, Ergebnisse, Anwesenheit, Meldungen; Mitgliederdaten nur als Vorschlag |
| 4 | Anmeldung im Namen einer Person (OAuth), „Verbinden“ bekannter Anwendungen; betrifft dann auch die Apps |

Nie über die API: Kasse und Bank schreiben, Rollen und Rechte, vollständiger Export, endgültiges
Löschen, Versand an Mitglieder.
