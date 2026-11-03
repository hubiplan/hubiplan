# Aufgaben: Aufbau und Umsetzung

Aufgaben gelten für Plattform, Dachverbände, Vereine und Untereinheiten. Eigene Aufgaben
bleiben privat. Zusätzliche Sichtbarkeit entsteht ausschließlich durch ausdrückliche Freigaben.

## Bestandsaufnahme

- Die Startseitenkachel und die App-Verwaltung nutzen dieselben fachlichen Sammlungen.
  Aufgabenrechte und App-Navigation müssen zusätzlich ergänzt werden.
- Rollen kennen Bereiche mit Lesen und Bearbeiten. Aufgabenlesen erlaubt die Pflege eigener
  Aufgaben; Aufgabenbearbeiten erlaubt zusätzlich das Teilen.
- Verschlüsselte Textfelder und private Dateien lassen sich wiederverwenden.
- Die Organisationsprüfung der bisherigen API genügt für organisationsübergreifende Aufgaben
  nicht. Der Empfänger greift im Kontext seiner berechtigten Zieleinheit zu.
- Rückgängig und Export benötigen neben Bereichsrechten die heutige Aufgabenberechtigung.
  Private Inhalte dürfen nicht im allgemeinen Vereinsprotokoll landen.
- Hintergrundjobs versenden nach atomarer Beanspruchung. Kanalfehler dürfen andere Kanäle
  nicht verhindern; aktuelle Rechte sind vor jedem Versand erneut zu prüfen.

## Lieferabschnitte

1. A1: Private Aufgaben, Oberfläche, Kachel, Papierkorb, Rückgängig, persönlicher Export.
2. A2: Freigaben innerhalb einer Einheit, Zuständige, Verantwortung und Nachfolge.
3. A3: Persönliche Einstellungen und Erinnerungen in HUBIplan, per Mail und Push.
4. A4: Verschlüsselte Anhänge und berechtigte Dokumentverweise.
5. A5: Serien mit höchstens einer offenen Ausgabe, Kalenderregeln und atomarer Rücknahme.
6. A6: Gemeinsame Aufgaben und unabhängige Zielkopien zwischen erlaubten Ebenen.
7. A7: Vollständige Android-Bedienung und sichere Push-Navigation.

Jeder Abschnitt erhält einen eigenen PR. Tests laufen lokal über `scripts/test.sh`;
automatische CI-Auslöser bleiben abgeschaltet. Migrationen bleiben additiv und rückführbar.
