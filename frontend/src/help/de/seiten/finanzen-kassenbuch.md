---
key: page.finance_cashbook
titel: Finanzen › Kassenbuch
bereich: finanzen
modul: finance
rechte: [finance.view]
routen: [/finanzen/kassenbuch]
stichworte: [Buchung, Beleg, Einnahme, Ausgabe, Kasse, Splitbuchung, Aufteilen]
---

Im Kassenbuch steht jede Einnahme und Ausgabe mit Datum, Konto, Kategorie und Beleg. Buchungen eines abgeschlossenen Zeitraums lassen sich nicht mehr ändern, nur mit einer Gegenbuchung berichtigen. So bleibt das Kassenbuch prüfbar.

Buchungen mit Belegen nur stornieren. Importierte Kontoauszüge bleiben erhalten; unbenötigte Umsätze ignorieren. Gebuchte Kategorien für neue Zuordnungen archivieren und eine neue Kategorie anlegen. Mahnungen behalten ihre archivierte Fassung.

Die Namenssuche unterscheidet nicht zwischen Groß- und Kleinschreibung. Unicode-Schreibvarianten werden vereinheitlicht; „ß“ und „ss“ gelten dabei als gleich. Andere gewählte Filter gelten weiterhin.

Nach einem Wechsel der Auswahl werden die bisherigen Ergebnisse ausgeblendet, bis die neue Abfrage abgeschlossen ist. Falls das Laden fehlschlägt, kannst du mit **Erneut laden** dieselbe Auswahl erneut abfragen.

Schlägt das Laden der Konten oder Kategorien fehl, bietet **Erneut laden** einen lokalen Wiederholungsweg. Bereits eingegebene Buchungsangaben bleiben bei einer fehlgeschlagenen Aktualisierung erhalten.

**Aufteilen** (Splitbuchung): Gehört eine Zahlung zu mehreren Kategorien oder steuerlichen Bereichen, etwa die Abrechnung des Festwirts mit Getränken, Eintritt und Bandenwerbung, öffne die Buchung und wähle **Aufteilen**. Jeder Teil bekommt Kategorie, Betrag und auf Wunsch Veranstaltung und Text. Zusammen müssen die Teile genau den Betrag ergeben. Jeder Teil wird eine eigene Buchung mit eigener Nummer. Datum, Konto und Empfänger bzw. Zahler gelten für alle Teile, Belege und Kontoumsatz bleiben beim ersten Teil. Aufteilen geht, solange die Buchung nicht festgeschrieben ist und nicht zu einem Storno, einer Quittung, einer Rechnungszahlung oder einer Zuwendung gehört.

**Aufwandsvergütung an eine Person**: Zahlt der Verein einer Übungsleiterin oder einem Ehrenamtlichen eine Pauschale, wählt ihr bei der Ausgabe Übungsleiterfreibetrag oder Ehrenamtspauschale und tragt das Mitglied oder den Empfänger ein. Die Summen je Person stehen unter Finanzen › Pauschalen. Das Feld gibt es mit dem Modul Steuern & Gemeinnützigkeit.

**Umsatzsteuer im Betrag**: Ist der Verein umsatzsteuerpflichtig, wählt ihr bei Einnahmen und Ausgaben den Steuersatz (19 %, 7 %, steuerfrei oder keine). Der Betrag bleibt brutto; Netto und Steuer rechnet HUBIplan aus. Neue Buchungen übernehmen die Vorgabe der Kategorie (Einrichtung › Kategorien, Spalte **Umsatzsteuer**). Bei gemischt genutzten Ausgaben tragt ihr unter **Vorsteuer abziehbar (%)** den unternehmerischen Anteil ein. Die Summen stehen unter Finanzen › Steuern › Umsatzsteuer.

**Als Anlage erfassen**: Bei einer Ausgabe ab 250 € übernimmt dieser Knopf Betrag, Datum und Text in das Anlagenverzeichnis (Finanzen › Anlagen) und verknüpft die Anlage mit der Buchung.
