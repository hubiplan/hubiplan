# Auslagen erstatten

Modul `expenses` (Gruppe Finanzen, nur Vereine), App `backend/expenses`, Seite
`/finanzen/auslagen`, im Mitgliederbereich „Auslagen“, in den Apps unter „Ich“ › Auslagen.
Mitglieder melden selbst bezahlte Ausgaben für den Verein mit einem Foto oder einer Datei des
Belegs und bekommen genau diesen Betrag erstattet. Die Kasse prüft, gibt frei und zahlt aus;
die Auszahlung wird als Ausgabe mit dem Beleg gebucht.

Rechte: `expenses.view` (sehen, sachlich bestätigen) und `expenses.edit` (freigeben, ablehnen,
Einstellungen, persönliche Links). Auszahlen braucht zusätzlich `finance.edit`. Die Migration
gibt `expenses.view` allen Vereinsrollen mit `finance.view` oder `finance.edit` und
`expenses.edit` allen mit `finance.edit`. Untereinheiten bekommen keine Rechte von selbst.

## Ablauf

1. **Melden** (Mitgliederbereich, App oder Kasse für jemanden): Zweck, Datum des Kaufs,
   eine oder mehrere Positionen, Belege (Bilder, PDF, XRechnung/ZUGFeRD-XML; höchstens 10),
   Auszahlung als Überweisung (Kontoinhaber und IBAN, aus dem SEPA-Mandat vorbelegt) oder bar,
   optional Untereinheit und Projekt. Fahrtkosten mit Strecke und Kilometern statt Beleg
   (Satz je km in den Einstellungen). Entwurf oder gleich einreichen; die Nummer
   `AJJJJ-NNNN` wird beim Einreichen vergeben. `Idempotency-Key` schützt vor doppeltem Anlegen.
2. **Sachlich bestätigen** (nur für Untereinheiten, die das in den Einstellungen wollen): die
   Leitung bestätigt unter Untereinheit › Auslagen, dass die Ausgabe für sie war, oder fragt nach.
3. **Prüfen** (Kasse): Kategorie je Position, Hinweise (Kauf älter als die eingestellten
   Monate, gleicher Beleg oder gleicher Betrag und Tag in einer anderen Auslage, E-Rechnung
   nennt einen anderen Betrag, Rechnung über 250 € auf das Mitglied statt den Verein) und Stand
   im Haushaltsplan je Kategorie; freigeben, kürzen (nur mit Grund), Rückfrage stellen,
   ablehnen (mit Grund).
4. **Auszahlen**: bar oder per Überweisung (GiroCode zum Abscannen) mit Buchung auf dem
   gewählten Konto, oder gesammelt als **Sammelüberweisung** (pain.001 wie bei den
   Musikerauszahlungen). Beim Export werden alle Auslagen der Datei gebucht. Ein Storno der
   Buchung setzt die Auslage auf „freigegeben“ zurück.
5. **Verzicht** (wenn in den Einstellungen mit Satzung oder Beschluss hinterlegt): das Mitglied
   verzichtet auf die Erstattung, die Kasse stellt eine Zuwendungsbestätigung
   (Aufwandsspende) aus. Nur bei einem vorher bestehenden Anspruch (§ 10b Abs. 3 EStG).

Stand: `draft`, `submitted`, `question`, `confirmed`, `approved`, `paid`, `rejected`,
`withdrawn`, `waived`.

## Vier-Augen-Regel und Kleinbeträge

Eine eigene Auslage gibt immer jemand anderes frei. Ausnahme für die Kasse: eigene Auslagen
bis zur Kleinbetragsgrenze (Vorgabe 200 €, einstellbar) darf sie selbst freigeben und auszahlen;
sie erscheinen dann unter „Zu sichten“, bis eine zweite Person mit `expenses.edit` sie
nachträglich gesichtet hat. Ab einem einstellbaren Betrag braucht jede Auslage zwei
Freigaben.

## Vorschüsse und persönliche Links

- **Vorschuss** (A5, einstellbar): vorab ausgezahlter Betrag; die spätere Abrechnung mit Belegen
  verrechnet ihn, ein Rest wird nachgezahlt oder zurückgefordert.
- **Persönlicher Link** (A6, einstellbar): für Personen ohne Zugang (Helfer, Übungsleiter ohne
  Konto). Die Kasse legt ihn an, er gilt nur für diese Person und läuft ab; widerrufen gibt 404.
  Öffentliche Seite `/auslage/<token>`, Schnittstelle `GET/POST /api/public/expense/<token>/`.

Nicht gebaut: Überweisungen direkt über FinTS (braucht die FinTS-Anbindung, siehe Konzept
FinTS) und Belegerkennung auf dem Server (Betrag und Datum aus dem Foto). Die Beträge tippt das
Mitglied selbst ein.

## Schnittstelle

Verein (`/api/orgs/<id>/`):

- `GET expenses/` (Liste mit `summary`: Zahl und Summe freigegebener, in Prüfung, zu sichten),
  `POST expenses/` (Kasse meldet für jemanden), `GET/PATCH expenses/<id>/` (mit `version`),
  `POST expenses/<id>/<Aktion>/` mit `submit`, `ask`, `approve` (`amount`, `reason`),
  `reject` (`reason`), `pay` (`account`, `date`), `POST expenses/review/` (sichten),
  `POST expenses/<id>/files/`, `GET expenses/<id>/files/<Datei>/`.
- `GET/PATCH expenses/settings/`, `GET expenses/options/`, `GET/POST expenses/transfers/`,
  `POST expenses/transfers/<id>/` (Datei, gebucht), `GET/POST expenses/links/`,
  `DELETE expenses/links/<id>/`.

Untereinheit (`/api/depts/<id>/`): `GET expenses/`, `GET expenses/<id>/`,
`POST expenses/<id>/confirm/` bzw. `ask/`, Belege lesen.

Mitgliederbereich und Apps (`/api/portal/<Zugang>/`, auch mit dem Geräteschlüssel):
`GET expenses/` (`claims`, `options`), `POST expenses/` (mehrteilig: Felder, `lines` und
`payee` als JSON-Text, Belege als `file`, `submit=true` zum Einreichen, `source=app` aus den
Apps), `GET/PATCH/DELETE expenses/<id>/` (löschen nur Entwürfe ohne Nummer),
`POST expenses/<id>/files/`, `DELETE expenses/<id>/files/<Datei>/`,
`POST expenses/<id>/<Aktion>/` mit `submit`, `answer` (`text`), `withdraw`, `waive`.
`expenses_enabled` und `expenses_questions` (offene Rückfragen der Kasse) stehen in `portal`.

## Daten und Sicherheit

`ExpenseSettings`, `ExpenseClaim`, `ExpenseLine`, `ExpenseFile`, `ExpenseEvent`,
`ExpenseLink`, `TransferRun`, `TransferItem`. Zweck, Notizen und Bankverbindung sind
verschlüsselt gespeichert, Belege liegen im geschützten Speicher mit Prüfsumme. Alle Tabellen
haben Zeilenschutz (RLS) nach Verein; ein Trigger prüft, dass Positionen, Belege, Verlauf und
Sammelüberweisungen zum selben Verein gehören. Benachrichtigungen per Mail und Push
(Rückfrage, Freigabe, Ablehnung, Auszahlung). In der Selbstauskunft steht `auslagen.json`
(IBAN gekürzt).

Offene, freigegebene Auslagen zählen in der Vermögensübersicht und im Jahresabschluss als
Verbindlichkeiten.

## Aufbewahrung

Siehe [aufbewahrung.md](aufbewahrung.md): Ausgezahlte Auslagen gehören zur Buchführung (Belege
8 Jahre, Antrag und Verlauf mit den Büchern nach 10 Jahren anonymisiert). Abgelehnte und
zurückgezogene: Belege und Bankverbindung nach 6 Monaten gelöscht, Eckdaten bis Ende des
Folgejahres. Entwürfe nach 90 Tagen ohne Änderung gelöscht (täglicher Job).
