# Arbeitsstunden mit Ersatzbeitrag

Viele Vereine mit Heim, Halle oder Stand verlangen von ihren Mitgliedern Arbeitsstunden im Jahr.
Wer sie nicht leistet, zahlt einen Ersatzbeitrag je fehlender Stunde. HUBIplan zählt die
geleisteten Stunden aus den Helferdiensten und stellt den Ersatzbeitrag mit dem Beitrag in
Rechnung.

## Einstellung

Finanzen › Einrichten › Beitragssätze › **Arbeitsstunden** (nur Vereine, Recht `billing.edit`):

- je Mitgliedsart **Pflichtstunden im Jahr** und **Ersatz je fehlender Stunde** (Modell
  `billing.WorkHourRule`; leere Stunden = keine Pflicht),
- **Pflicht ab Alter** und **Pflicht bis Alter** für alle Mitgliedsarten
  (`BillingSettings.work_min_age`/`work_max_age`; Alter zu Beginn des Geschäftsjahres; Personen
  ohne Geburtsdatum sind nicht ausgenommen).

Schnittstelle: `GET/PUT /api/orgs/<id>/billing/work-hours/` und
`GET /api/orgs/<id>/billing/work-hours/balance/?jahr=<Geschäftsjahr>` (Stand je Mitglied).

## Berechnung (`billing/workhours.py`)

- **Geleistet**: Einteilungen in Helferschichten (`helpers.ShiftAssignment`) mit
  `done=True` und Status „eingetragen“, deren Schicht im Geschäftsjahr beginnt; gezählt wird die
  Dauer der Schicht. Ohne eingeschaltetes Modul Helferdienste rechnet HUBIplan keinen
  Ersatzbeitrag.
- **Soll**: Pflichtstunden der Mitgliedsart am letzten Tag der Mitgliedschaft im Geschäftsjahr,
  anteilig je angefangenem Monat der Mitgliedschaft (`Stunden × Monate / 12`).
  Organisationsmitglieder sind ausgenommen.
- **Ersatzbeitrag**: `max(Soll − geleistet, 0) × Ersatz je Stunde`, auf Cent gerundet.

## Beitragslauf

Im **ersten Zeitraum** eines Geschäftsjahres (bei jährlicher Abrechnung also im einzigen) rechnet
`plan_run` den Ersatzbeitrag des Vorjahres. Er kommt als eigener Posten „Ersatzbeitrag für
fehlende Arbeitsstunden <Jahr>“ mit Soll, geleistet und Satz als Zusatz auf dieselbe Rechnung wie
der Beitrag (Einzel-, Sammel- oder Haushaltsrechnung). Der Posten ist wie der Beitrag ein
Beitragsposten (`is_fee`, mit Mitglied), denn der Ersatz für Arbeitsleistungen zählt steuerlich zu
den Mitgliedsbeiträgen. Familien- und Firmenbeiträge ermäßigen ihn nicht.

Mitglieder einer beitragsfreien Mitgliedsart mit Pflichtstunden bekommen eine Rechnung nur mit
dem Ersatzbeitrag. Mitglieder beitragsfreier Untereinheiten und Mitglieder, die vor dem Lauf
ausgetreten sind, bekommen keinen. Die Prüfliste vor dem Beitragslauf nennt Zahl und Summe.
