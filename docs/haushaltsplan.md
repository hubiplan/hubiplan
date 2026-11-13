# Haushaltsplan

Geplante Einnahmen und Ausgaben je Kategorie für ein Geschäftsjahr, verglichen mit dem
Kassenbuch. Seite: Finanzen › Auswerten & abschließen › Haushaltsplan (`/finanzen/haushaltsplan`),
Rechte `finance.view` (lesen) und `finance.edit` (planen), Modul `finance`.

## Daten

| Modell | Inhalt |
| --- | --- |
| `finance.Budget` | Plan eines Geschäftsjahres je Einheit: Stand Entwurf/beschlossen, beschlossen am/durch, Bemerkung, `version` gegen gleichzeitiges Bearbeiten |
| `finance.BudgetLine` | Art (Einnahmen/Ausgaben), Kategorie, Untereinheit (leer: alle), Planbetrag ≥ 0, Bemerkung |
| `finance.Project.plan_income/plan_expense` | Planwerte einer Veranstaltung (leer: nicht geplant) |

Beide Tabellen haben Row-Level Security (Migration `finance/0036`) und stehen im Datenexport
(`datatransfer/tables.py`). Eine Kategorie mit Planzeilen lässt sich nicht löschen.

## Rechnung (`finance/budget.py`)

- Ist: Einnahmen und Ausgaben im Geschäftsjahr mit Kategorie, ohne Umbuchungen. Eine
  Stornobuchung (`cancels`) mindert die Seite der stornierten Buchung.
- Zuordnung: Zeile mit Untereinheit zählt nur deren Buchungen, Zeile ohne Untereinheit den Rest
  der Kategorie; alles andere steht unter `unplanned`.
- Hochrechnung (nur laufendes Jahr): Ist plus Vorjahresbuchungen ab demselben Tag des
  Geschäftsjahres; ohne Vorjahreswerte `max(Ist, Plan)`.
- Vorlage aus dem Vorjahr: Plan unverändert oder Ist auf volle Euro gerundet.
- Ein beschlossener Plan lässt sich weder ändern noch löschen, bis er wieder Entwurf ist.

## Schnittstelle

| Aufruf | Zweck |
| --- | --- |
| `GET /api/orgs/<id>/finance/budget/?jahr=JJJJ` | Plan, Ist, Hochrechnung, Vorjahr; `&als=pdf\|xlsx` als Datei |
| `PUT …/finance/budget/?jahr=JJJJ` | `{lines, note, version}` ersetzt die Zeilen eines Entwurfs |
| `DELETE …/finance/budget/?jahr=JJJJ` | Entwurf löschen |
| `POST …/finance/budget/status/?jahr=JJJJ` | `{status: adopted, adopted_on, adopted_by}` oder `{status: draft}` |
| `POST …/finance/budget/copy/?jahr=JJJJ` | `{source: plan\|actual}` übernimmt das Vorjahr |

Änderungen stehen im Änderungsprotokoll (Zahl der Zeilen und Summen, Stand).
