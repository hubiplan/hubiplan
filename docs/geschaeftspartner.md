# Geschäftspartner

Firmen, Behörden, Vereine und Personen außerhalb der Mitgliederliste: Lieferanten,
Dienstleister, Kunden, Sponsoren, Spender, Vermieter, Künstler, Presse, Versicherungen, Banken.
Menüpunkt *Verein › Geschäftspartner* (`/geschaeftspartner`), ohne eigenes Modul, für Vereine,
Dachverbände und Untereinheiten mit eigenem Datenbereich.

## Daten

- `billing.BusinessPartner`: Name, Art (`kind`: company, authority, association, person,
  other), Rollen (`roles`, Liste), Nummer `GP-0001` (fortlaufend je Datenbereich, änderbar),
  zuständige Einheit (`unit`), Verweis auf eine Mitgliedschaft (`membership`, statt doppelt
  pflegen), Angaben (`details`, verschlüsselt, Schema wie bei der E-Rechnung, nur der Name ist
  Pflicht), Bankverbindung (`bank`, verschlüsselt, mit Datum und Name der letzten
  IBAN-Änderung), unsere Kundennummer, Standardkategorie, Zahlungsziel, Künstlerkennzeichen
  (KSVG), Notizen. `is_customer`/`is_supplier` folgen aus den Rollen (Kunde; Lieferant oder
  Dienstleister); ohne Rollen bleiben sie, wie sie sind.
- `billing.PartnerContact`: Ansprechpartner (Name, Vorname, Funktion, E-Mail, Telefon,
  Hauptansprechpartner, erhält Rechnungen, erhält Post, Notiz), verschlüsselt, mit RLS.

## Rechte

- `partners.view` / `partners.edit` (Bereich „Geschäftspartner“). Die Migration
  `access/0018_geschaeftspartner` gibt sie Rollen, die bisher Kasse oder Beiträge lasen bzw.
  pflegten.
- Lesen und Pflegen bleibt auch mit `finance.*` oder `billing.*` möglich, weil Rechnungen und
  der Rechnungseingang die Liste brauchen.
- Bank, Standardkategorie, Zahlungsziel und Künstlerkennzeichen liefert die Schnittstelle nur mit
  `finance.view` oder `billing.view`; ändern nur mit `finance.edit` oder `billing.edit`.

## Schnittstelle

`/api/orgs/<id>/billing/partners/`

| Weg | Zweck |
| --- | --- |
| `GET`, `POST` | Liste (mit Ansprechpartnern), anlegen |
| `GET`, `PATCH`, `DELETE <pk>/` | Akte, ändern, löschen (nur ohne Verweise, sonst 400) |
| `POST <pk>/merge/ {other}` | doppelten Eintrag übernehmen: Rechnungen, Buchungen, Bankzeilen, Quittungen, Zuwendungen, Vereinbarungen, Auftritte und Ansprechpartner wandern mit, Rollen und leere Angaben werden ergänzt |
| `GET export/` | Excel (Bank nur mit Kassen- oder Beitragsrecht) |
| `POST import/` (`?probe=1`) | Excel mit Kopfzeile wie der Export, mindestens „Name“; vorhandene Namen werden übersprungen, höchstens 500 Zeilen |
| `GET <pk>/turnover/` | Einnahmen/Ausgaben je Jahr ohne Stornos und Umbuchungen, letzte 10 Buchungen (Modul Finanzen, `finance.view`) |
| `GET`, `POST suggestions/ {name, kind?, roles?}` | Bestand übernehmen: Freitexte, die mindestens zweimal ohne Partner im Kassenbuch stehen; POST legt den Partner an und verknüpft Buchungen und Bankzeilen mit genau diesem Namen (`finance.edit`) |
| `…/<pk>/agreements/` | Vereinbarungen (P4) anlegen, ändern, entfernen; `POST …/agreements/<id>/thanks/ {text?}` liefert den Dankesbrief als PDF |
| `…/<pk>/documents/` (`<id>/`) | Dokumente (P5): hochladen (`file`, `title?`, `agreement?`), herunterladen, entfernen; zählen zum Speicherbudget, Virenprüfung wie in der Ablage |
| `GET`, `POST mailing/` | Partnergruppe nach `role`/`kind`: Empfänger mit E-Mail-Adressen; POST `{subject, text}` liefert den Serienbrief als PDF (P5) |
| `…/<pk>/contacts/` | Ansprechpartner anlegen, ändern, entfernen; nur ein Hauptansprechpartner |

## Kasse (P2)

- `partner` an `Booking`, `CashReceipt`, `BankLine` und `Donation` (`finance/0034`, `SET_NULL`).
  Der Freitext `counterparty` bleibt; ohne Freitext übernimmt die Buchung den Partnernamen.
- Storno, Splitteile, Quittungsstorno, Buchung aus Bankzeile und Rechnungszahlung übernehmen den
  Partner. Die Aufbewahrungsfrist löscht den Verweis mit.
- `bookings/counterparties/` nennt aktive Partner zuerst (`partner`, `category` =
  Standardkategorie); `bookings/?geschaeftspartner=<id>` filtert.
- Der Bankimport ordnet Zeilen über die IBAN zu (`partners_by_iban`, entschlüsselt im Speicher,
  weil Vereine wenige Partner haben).
- Künstlersozialabgabe zählt auch Buchungen mit Partnern, die als künstlerisch tätig gelten.

## Sponsoring (P4)

- `PartnerAgreement` (`billing/0027`): Art, Zeitraum, Betrag, Sachleistung, Gegenleistungen,
  steuerliche Einordnung (`mention` = nur Nennung, `advertising` = aktive Werbung,
  `none`), Kategorie, Erinnerung in Tagen vor Ende.
- Mit Enddatum und Modul Aufgaben legt `sync_reminder` eine Aufgabe für die anlegende Person an
  und verschiebt sie mit dem Enddatum; ohne Enddatum wird eine offene Erinnerung gelöscht.
- Dankesbrief: PDF auf dem Briefbogen (`letterhead`), an die Anschrift und den ersten
  Ansprechpartner mit „erhält Post“; `thanked_at` merkt das Datum.
- `website_consent` und `website_url` am Partner. `GET /api/orgs/<id>/billing/partner-logos/`
  liefert Name und Link der Partner mit Einwilligung für den Abschnitt „Partner und Sponsoren“;
  das Logo bleibt ein Webseitenbild.

## Verträge, Dokumente, Serienbrief (P5)

- Vereinbarungsart `contract` mit `notice_days` (Kündigungsfrist) und `auto_renew`. Die
  Erinnerung liegt `remind_days` vor dem letzten Kündigungstag (`notice_by`), ohne Frist vor
  dem Ende.
- `PartnerDocument` (`billing/0028`): Datei an der Akte, optional zu einer Vereinbarung;
  zählt in `documents.services.total_bytes`.
- Serienbrief: ein Brief je Partner mit Anschrift (höchstens 500), Anrede je erstem
  Ansprechpartner mit „erhält Post“. Der Verteiler nimmt deren E-Mail-Adressen, sonst die des
  Partners; HUBIplan verschickt selbst nichts.

Änderungen stehen im Änderungsprotokoll. Der Datenumzug übernimmt beide Tabellen.

Konzept und weitere Stufen (Kasse, Rechnungseingang, Sponsoring, Verträge): Projektordner
`konzepte/geschaeftspartner.md`.
