# API für andere Programme

Über diese Schnittstelle lesen Programme Dritter Daten einer Einheit und schreiben, wenn es
eigens erlaubt ist: die Software eines Dachverbands, eine eigene Webseite, eine Anzeigetafel,
eine Auswertesoftware, ein Skript. Umgesetzt sind **Stufe 0**
(die Schnittstelle der Vereinswebseite als offene Daten beschrieben, siehe unten), **Stufe 1**
(API-Zugänge mit Schlüssel, Lesen ohne Personendaten) und **Stufe 2** (Verbandsmeldung,
Mitglieder, Ehrungen und Qualifikationen lesen, nur mit Empfänger und Rechtsgrundlage;
Benachrichtigungen bei Änderungen) und **Stufe 3** (Schreiben: Termine, Ergebnisse, Anwesenheit,
Vorschläge zu Mitgliedern, Rundschreiben als Entwurf; Ausweisprüfung). Die Anmeldung im Namen
einer Person ist eine spätere Stufe.

## Kurz

| | |
| --- | --- |
| Adresse | `https://<Instanz>/api/partner/v1/` |
| Beschreibung | `https://<Instanz>/api/partner/v1/openapi.json` (OpenAPI 3, ohne Anmeldung), Kopie im Repo: [backend/partnerapi/openapi.json](../backend/partnerapi/openapi.json) |
| Lesbar | `https://<Instanz>/api/partner/v1/docs/` (ohne Anmeldung, aus der OpenAPI-Beschreibung, ohne Skripte und fremde Server; `?lang=en` auf Englisch) |
| Anmeldung | Kopfzeile `Authorization: Bearer hpk_…` |
| Wer vergibt | Vorstand der Einheit unter Einstellungen › API-Zugänge (`/einstellungen/api`) |
| Voraussetzung | Modul `api` („API für andere Programme“, anfangs aus) und Zusatzrecht `api.manage` |
| Abschalten | Betreiber: `HUBIPLAN_API=false` (dann 404 für alles unter `/api/partner/` und die Verwaltung) |

Code: App `backend/partnerapi/` (`models.py` Zugang, `auth.py` Schlüsselprüfung, `scopes.py`
Bereiche, `views.py` Aufrufe für Dritte, `personal.py` Aufrufe mit Personendaten, `refs.py`
feste Kennungen, `webhooks.py` und `signals.py` Benachrichtigungen, `writes.py` Schreiben,
`manage_views.py`
Verwaltung, `openapi.py` Beschreibung, `docs_page.py` lesbare Seite).
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
- **Aus fremden Webseiten aufrufbar** (CORS): nur ohne `termine.mitglieder`,
  `statistik.lesen`, `verbandsmeldung.lesen` und ohne Bereiche mit Personendaten, weil der
  Schlüssel dann im Quelltext der fremden Webseite steht.
- **Grenzen:** 600 Abrufe je Stunde und Zugang, 300 je Minute und Adresse; darüber 429 mit
  `Retry-After`. Höchstens 50 Zugänge je Einheit.
- **Frischer zweiter Faktor** (`accounts/step_up.py`) für Anlegen, Schlüsselwechsel,
  Wiedereinschalten, neues Geheimnis der Benachrichtigungen und jede Änderung, die mehr
  Personendaten herausgibt, den Empfänger wechselt oder die Adresse der Benachrichtigungen
  ändert. `api.manage` setzt „Einstellungen“ voraus und wird nie automatisch
  vergeben, auch nicht an neue Vorstandsrollen (`NOT_AUTOMATIC`).
- **Protokoll:** Anlegen, Ändern, Schlüsselwechsel, Wiedereinschalten und Löschen stehen im
  Änderungsprotokoll; zu Anlegen und Schlüsselwechsel geht eine Mail an alle mit `api.manage`.
  Am Zugang stehen letzter Abruf, dessen Adresse und die Zahl der Abrufe.
- Der Schlüssel gilt nur unter `/api/partner/`, nirgends sonst in HUBIplan.

Alle Tabellen sind je Einheit zeilengesichert (`partnerapi/migrations/0002_rls.py`,
`0004_stufe2_rls.py`, `0006_stufe3_rls.py`). Zugänge, Kennungen, Abrufprotokoll,
Benachrichtigungen und die Einträge des Schreibens gehen bewusst
nicht in die Datenübernahme: Nach einem Umzug vergibt die Einheit neue Schlüssel.

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

Ein Zugang für eine Untereinheit bekommt nur `einheit.lesen`, die Termine, die Statistik und
die Bereiche mit Personendaten außer der Verbandsmeldung (siehe unten).
„Veröffentlicht“ heißt: Die Webseite der Einheit ist öffentlich und zeigt den Inhalt; sonst
kommt `published: false` mit leerer Liste. Zu- und Absagen, Teilnehmende, Namen einzelner
Mitglieder, Kontaktdaten von Personen, Kasse und Bank gibt es in diesen Bereichen nirgends.

## Personendaten (Stufe 2)

Diese Bereiche gibt es nur für Vereine. Im Katalog tragen sie `personal`.

| Bereich | Aufruf | Inhalt | Modul |
| --- | --- | --- | --- |
| `verbandsmeldung.lesen` | `GET federation-report/` | Mitgliedschaften mit einer Mitgliedsart „an Dachverband melden“ am Stichtag (`date`): Anzahl nach aktiv, passiv und Geburtsmonat. Mit „namentlich“ am Zugang zusätzlich `persons`: Name, Vorname, Geburtsdatum, Verbandsnummer, Mitgliedsart, Eintritt | `members` |
| `mitglieder.lesen` | `GET members/`, `members/<id>/` | Name, Vorname, Titel, Geschlecht, Geburtsdatum, Mitgliedsnummer, Zustand; Feldgruppen nach Wahl am Zugang (`status`, `unit`, `changed_since`, `limit`, `cursor`) | `members` |
| `ehrungen.lesen` | `GET honors/` | verliehene Ehrungen mit Name und Zeitraum (`current`, `unit`) | `awards` |
| `qualifikationen.lesen` | `GET qualifications/` | Nachweise mit Name, Erwerb und Gültigkeit (`valid`, `unit`, `changed_since`); nie Arten mit bloßem Einsichtsvermerk | `qualifications` |

**Voraussetzung am Zugang** (sonst lehnt die Verwaltung das Speichern ab, und ein Aufruf
antwortet mit 403 `legal_basis_missing`):

- **Empfänger:** ein aktiver Geschäftspartner der Einheit (`ApiAccess.partner`).
- **Rechtsgrundlage:** `processing` (Auftragsverarbeitung, Vertrag nach Art. 28 DSGVO) oder
  `transfer` (Übermittlung an einen eigenen Verantwortlichen).
- **Bestätigung** durch den Menschen, der den Zugang anlegt, mit Zeitpunkt und Konto. Sie gilt
  für genau diesen Empfänger und diese Rechtsgrundlage; ein Wechsel verlangt sie neu.

Die namentliche Verbandsmeldung zählt als Personendaten, die Zahlen nicht. Bei
Auftragsverarbeitung bekommt der Geschäftspartner die Rolle „Auftragsverarbeiter“ und steht
damit im Verzeichnis der Verarbeitungstätigkeiten; die Tätigkeit „Weitergabe über die API für
andere Programme“ steht dort, sobald das Modul an ist (`privacy/catalog.py`). Wird der
Geschäftspartner abgeschaltet oder gelöscht, gibt der Zugang sofort keine Personendaten mehr
heraus. Alle mit `api.manage` bekommen eine Mail, sobald ein Zugang neu Personendaten herausgibt.

**Datensparsamkeit:**

- Feldgruppen der Mitglieder (`member_fields`): `contact` (E-Mail, Telefon, Anschrift),
  `membership` (Eintritt, Austritt, Mitgliedsart, Verbandsnummer, Zeiträume), `units`
  (Untereinheiten). Nicht gewählte Gruppen fehlen in der Antwort.
- „Nur aktuelle Mitglieder“ (Vorgabe) und „Nur Volljährige“ begrenzen den Zugang; ohne
  Geburtsdatum gilt eine Person nicht als volljährig. Die Begrenzung gilt auch für Ehrungen und
  Qualifikationen.
- Nie nach außen gehen: Bankdaten, Bemerkungen, Fotos, Zusatzfelder, Rollen, Mitgliedschaften
  nach Ablauf der Löschfrist, der genaue Austrittsgrund (nur `transfer` oder `other`).
- Kennungen (`id`, `member`) sind eigene UUIDs je Datensatz (`RecordRef`), nie interne
  Nummern. Sie entstehen beim ersten Abruf und bleiben gleich.

**Abrufprotokoll:** Jeder Abruf mit Personendaten steht mit Zugang, Bereich, Zeit und Zahl der
Datensätze in `ReadLog` (90 Tage, Aufgabe `partnerapi.tasks.purge_logs`). Die Seite
Einstellungen › API-Zugänge zeigt je Zugang die Summe und die letzten Abrufe.

`changed_since` findet Änderungen an Person, Kontakt und Mitgliedschaft samt Eintritt, Austritt,
Mitgliedsart und Untereinheit. Sammeländerungen (Import) können fehlen; ein vollständiger
Abgleich in größeren Abständen bleibt sinnvoll.

## Schreiben (Stufe 3)

Grundsätze:

- Jeder schreibende Bereich wird einzeln angekreuzt (im Katalog `write`) und ist nie vorgewählt.
  Wird einer neu vergeben, verlangt die Verwaltung einen frischen zweiten Faktor, und alle mit
  `api.manage` bekommen eine Mail.
- Welcher Bereich für einen Aufruf nötig ist, steht in der OpenAPI-Beschreibung am Aufruf
  (`x-scope` und im Text).
- Geschrieben wird nur Unkritisches (Termin, Ergebnis, Anwesenheit) oder ein Vorschlag bzw.
  Entwurf, den ein Mensch in HUBIplan übernimmt (Mitgliederdaten, Rundschreiben). Nichts wird
  gelöscht, nichts versendet.
- Ändern kann ein Zugang nur, was er selbst angelegt hat (`WrittenRecord`), sonst 404.
- Ein Zugang, der „aus fremden Webseiten aufrufbar“ ist, schreibt nie (`write_not_allowed`).
- Grenze: 60 schreibende Anfragen je Stunde und Zugang, zusätzlich zu den 600 Anfragen.
- Im Änderungsprotokoll steht „API-Zugang ‹Name›“ statt einer Person. Die Verwaltung zeigt je
  Zugang, wie oft und wann zuletzt geschrieben wurde.
- Kopfzeile `Idempotency-Key` (bis 100 Zeichen): Dieselbe Anfrage mit demselben Schlüssel legt
  innerhalb von 24 Stunden nichts doppelt an und bekommt dieselbe Antwort, dann mit
  `Idempotency-Replayed: true`. Derselbe Schlüssel mit anderem Inhalt: 409
  `idempotency_conflict`. Abgelehnte Anfragen belegen den Schlüssel nicht.
- `external_id`: eigene Kennung des Dritten, je Zugang und Art eindeutig. Eine zweite Anlage
  mit derselben Kennung gibt 409 `external_id_exists` mit der `id` des vorhandenen Datensatzes;
  `GET lookup/?kind=…&external_id=…` findet ihn (`kind`: `event`, `training`, `proposal`,
  `circular`).

| Bereich | Aufruf | Inhalt | Modul |
| --- | --- | --- | --- |
| `termine.schreiben` | `POST events/`, `GET`/`PATCH events/<id>/` | einzelnen Termin anlegen, ändern (nur `starts_at`: das Ende zieht mit), absagen (`is_cancelled`); Sichtbarkeit nur `public` oder `members`; keine Serien, keine Einladungen | `events` |
| `ergebnisse.schreiben` | `GET result-entry/`, `POST result-entry/<id>/` | offene eigene Wettbewerbe mit Einzelwertungen; Werte einliefern (bis 500 je Anfrage), Starter als Mitglied (`member`) oder Gast (`name`, `club`); jede Zeile einzeln geprüft (`accepted`, `rejected`) | `competitions` |
| `anwesenheit.schreiben` (P) | `POST trainings/`, `GET trainings/<id>/`, `POST trainings/<id>/attendance/` | Trainingstermin anlegen (nie Schießtermin), Mitglieder ein- und austragen (`present`, `absent`) | `training` |
| `mitglieder.schreiben` (P) | `POST members/<id>/proposals/`, `GET proposals/<id>/` | geänderte Namen und Kontaktdaten als Änderungsmeldung (`portal.ChangeRequest`), höchstens 3 offene je Mitglied und 200 je Zugang; Stand abfragen | `members` |
| `ausweis.pruefen` (P) | `POST card-check/` | Code eines Mitgliedsausweises: `valid`, `status`, `member_type`; nie Name, Foto oder Nummer; zählt nicht als Schreiben | `cards` |
| `rundschreiben.schreiben` | `POST circular-drafts/` | Betreff und Text als Entwurf, höchstens 20 Entwürfe je Zugang; Versand nur in HUBIplan | `circulars` |

„(P)“: Bereich mit Personendaten, also nur für Vereine und nur mit Empfänger und bestätigter
Rechtsgrundlage. `anwesenheit.schreiben` und `mitglieder.schreiben` setzen `mitglieder.lesen`
voraus (Kennungen der Mitglieder). Ergebnisse für Mitglieder brauchen ebenfalls
`mitglieder.lesen`; Gäste gehen ohne. Für eine Untereinheit gibt es Termine, Anwesenheit und
Vorschläge.

Bewusst nicht umgesetzt: neue Mitglieder anlegen (ein Mitgliedsantrag braucht die Erklärungen
der Person selbst; dafür gibt es das Antragsformular), Rechnungen einliefern (der Rechnungseingang
läuft über das Rechnungspostfach mit Prüfung), Ausschreibungen und Wettkampfmeldungen, Ehrungen
und Lehrgänge vorschlagen. Zu- und Absagen im Namen einer Person gehören zu Stufe 4.

## Benachrichtigungen (Webhooks)

Am Zugang lässt sich eine https-Adresse eintragen. Ändert sich etwas, sendet HUBIplan dorthin
ein `POST` mit einer schlanken Nachricht, nie mit Inhalten:

```json
{
  "id": "5f0e…",
  "type": "member.changed",
  "occurred_at": "2027-03-01T10:15:00+01:00",
  "unit": "<UUID der Einheit>",
  "object": { "type": "member", "id": "<Kennung wie unter members/>" }
}
```

| Ereignis | Bereich | Wann |
| --- | --- | --- |
| `member.created`, `member.changed` | `mitglieder.lesen` | Mitglied aufgenommen; Person, Kontakt, Mitgliedsart oder Untereinheit geändert |
| `member.left` | `mitglieder.lesen` | Austritt eingetragen |
| `member.deleted` | `mitglieder.lesen` | Mitgliedschaft gelöscht oder nach der Löschfrist geleert (nur, wenn sie schon einmal abgerufen wurde) |
| `event.created`, `event.changed`, `event.cancelled`, `event.deleted` | `termine.lesen` | eigener Termin, den der Zugang sehen darf; `object.id` ist `event_id` aus `events/` |

- **Unterschrift:** Kopfzeile `X-HUBIplan-Signature: t=<Unixzeit>,v1=<hex>`; `v1` ist
  HMAC-SHA256 über `<Unixzeit>.<Nachricht>` mit dem Geheimnis `hpw_…` des Zugangs. Das
  Geheimnis steht einmal in der Antwort, in der es entsteht, und liegt verschlüsselt in der
  Datenbank. Dazu `X-HUBIplan-Event` und `X-HUBIplan-Delivery` (gleich `id`).
- **Zustellung:** mindestens einmal, in Reihenfolge je Zugang. Antwort 2xx gilt als angekommen.
  Sonst neue Versuche nach 1, 5 und 30 Minuten, danach stündlich, bis zu drei Tage. Scheitert
  jede Zustellung sieben Tage lang, ruhen die Benachrichtigungen des Zugangs, und alle mit
  `api.manage` bekommen eine Mail.
- Welcher Bereich für einen Aufruf nötig ist, steht in der OpenAPI-Beschreibung am Aufruf
  (`x-scope` und im Text). Empfänger sollten doppelte Nachrichten an `id` erkennen.
- **Schutz:** nur https, keine internen Adressen, keine Weiterleitungen (`core/safehttp.py`).
  Gleichartige Nachrichten zu einem Datensatz werden zusammengefasst, solange sie warten.
- Mitglieder-Ereignisse gibt es nur für Zugänge der ganzen Einheit mit gültiger
  Rechtsgrundlage; Termine „nur Vorstand“ melden nie, Mitgliedertermine nur mit
  `termine.mitglieder`.
- **Ablauf im Code:** `signals.py` merkt eine Änderung beim Speichern nur vor; geprüft und
  eingereiht wird nach dem Abschluss der Änderung (`transaction.on_commit`), zugestellt jede
  Minute (`partnerapi.tasks.deliver_webhooks`).

## Fehler

Antworten mit `application/problem+json` (RFC 9457): `type`, `title`, `status`, `detail`, `code`.

| `code` | Status | Bedeutung |
| --- | --- | --- |
| `invalid_key` | 401 | Schlüssel fehlt oder ist unbekannt (auch: Modul aus) |
| `access_expired` | 401 | Zugang abgelaufen |
| `access_idle` | 401 | Zugang ruht nach 90 Tagen ohne Abruf |
| `ip_not_allowed` | 403 | Aufruf von einer nicht erlaubten Adresse |
| `missing_scope` | 403 | Bereich nicht vergeben (`scope` nennt ihn) |
| `legal_basis_missing` | 403 | Personendaten: Empfänger oder bestätigte Rechtsgrundlage fehlen |
| `too_many_requests` | 429 | Grenze erreicht, `Retry-After` beachten |
| `write_not_allowed` | 403 | Zugang ist aus fremden Webseiten aufrufbar und schreibt deshalb nicht |
| `external_id_exists` | 409 | eigene Kennung schon vergeben (`id` nennt den Datensatz) |
| `idempotency_conflict` | 409 | `Idempotency-Key` gehört zu einer anderen Anfrage |
| `record_locked` | 409 | Termin wurde in HUBIplan zur Serie oder „nur Vorstand“ |
| `too_many_open` | 409 | zu viele offene Vorschläge oder Entwürfe |
| `not_found` | 404 | gibt es nicht oder ist nicht veröffentlicht |
| `invalid_request` | 400 | Angabe ungültig (`errors` nennt das Feld) |

## Zusage zur Stabilität

Innerhalb von `v1` kommen nur Felder, Aufrufe und Bereiche hinzu; nichts fällt weg oder ändert
seine Bedeutung. Was wegfallen soll, wird zwölf Monate vorher in den Änderungshinweisen
angekündigt. Programme ignorieren unbekannte Felder. Feldnamen sind englisch, Kennungen von
Einheiten sind UUIDs, Zeiten stehen in ISO 8601 mit Zeitzone. Die Formate in
`partnerapi/views.py`, `partnerapi/personal.py` und `partnerapi/writes.py` sind der Vertrag; `tests/test_partnerapi.py` prüft, dass die Kopie
[backend/partnerapi/openapi.json](../backend/partnerapi/openapi.json) zum Code passt. Nach Änderungen:

```bash
cd backend && python manage.py api_openapi partnerapi/openapi.json
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
| 4 | Anmeldung im Namen einer Person (OAuth), „Verbinden“ bekannter Anwendungen; betrifft dann auch die Apps |

Offen aus Stufe 3: Ausschreibungen und Wettkampfmeldungen, Rechnungen einliefern, Ehrungen und
Lehrgänge vorschlagen.

Nie über die API: Kasse und Bank schreiben, Rollen und Rechte, vollständiger Export, endgültiges
Löschen, Versand an Mitglieder.
