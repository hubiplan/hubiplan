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
| `POST <pk>/merge/ {other}` | doppelten Eintrag übernehmen: Rechnungen, Auftritte und Ansprechpartner wandern mit, Rollen und leere Angaben werden ergänzt |
| `GET export/` | Excel (Bank nur mit Kassen- oder Beitragsrecht) |
| `POST import/` (`?probe=1`) | Excel mit Kopfzeile wie der Export, mindestens „Name“; vorhandene Namen werden übersprungen, höchstens 500 Zeilen |
| `…/<pk>/contacts/` | Ansprechpartner anlegen, ändern, entfernen; nur ein Hauptansprechpartner |

Änderungen stehen im Änderungsprotokoll. Der Datenumzug übernimmt beide Tabellen.

Konzept und weitere Stufen (Kasse, Rechnungseingang, Sponsoring, Verträge): Projektordner
`konzepte/geschaeftspartner.md`.
