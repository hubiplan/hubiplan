---
key: page.members_import
titel: Mitglieder › Import
modul: members
rechte: [members.edit]
routen: [/mitglieder/import]
stichworte: [Import, Excel, CSV, Tabelle, Übernahme]
---

Mit dem Import übernehmt ihr eine bestehende Mitgliederliste aus einer Tabelle (Excel oder CSV). HUBIplan zeigt vorher, welche Spalten es wie versteht und welche Personen es schon gibt. Erst nach deiner Bestätigung wird etwas gespeichert.

Organisationen als Mitglieder (Firma, Verein, Behörde …) erkennt der Import an der Spalte „Typ“ mit dem Wert „Organisation“. Für sie gibt es die Spalten „Namenszusatz“, „Rechtsform“ und „Ansprechpartner Name“, „Ansprechpartner Vorname“, „Ansprechpartner Funktion“, „Ansprechpartner E-Mail“ und „Ansprechpartner Telefon“. Weitere Ansprechpartner stehen in weiteren Zeilen mit derselben Mitgliedsnummer; der erste wird Hauptansprechpartner. Vorname und Geburtsdatum bleiben bei Organisationen leer. Sieht ein Name ohne Typ nach einer Organisation aus (z. B. „… GmbH“ oder „… e. V.“), meldet die Prüfung das, statt zu raten.

Ein paar Regeln bei der Prüfung: Eine vierstellige PLZ (Land Deutschland oder leer) ergänzt HUBIplan um die führende 0, die Excel bei Zahlen weglässt, und zeigt das in der Vorschau. Zahlen wie „1.000“ ohne Komma sind mehrdeutig und werden abgelehnt; bitte „1000“ oder mit Komma schreiben. Stehen für dieselbe Person in mehreren Zeilen verschiedene Werte in einem Zusatzfeld oder verschiedene Angaben zu einem Zeitraum mit gleichem Eintritt, meldet die Prüfung den Widerspruch. Ein ungültiges Datum in einem Datums-Zusatzfeld ist ein Fehler in dieser Zeile.
