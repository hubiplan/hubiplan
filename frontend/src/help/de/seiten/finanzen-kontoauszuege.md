---
key: page.finance_statements
titel: Finanzen › Kontoauszüge
modul: finance
rechte: [finance.view]
routen: [/finanzen/kontoauszuege]
stichworte: [Kontoauszug, CAMT, Bank, Zuordnung, FinTS, Abruf]
---

Hier lädst du den Kontoauszug aus dem Online-Banking im Format CAMT.053 hoch. HUBIplan schlägt für jeden Umsatz vor, wozu er gehört, etwa zu einer Rechnung oder einer Buchung, und du bestätigst. Dieselbe Datei zweimal einzulesen erkennt HUBIplan. Importierte Auszüge bleiben als Original erhalten. Nicht benötigte Umsätze kannst du ignorieren; falsche Zuordnungen kannst du lösen.

Steht die IBAN eines Umsatzes bei einem Geschäftspartner (Verwaltung › Geschäftspartner, Abschnitt Kasse), ordnet HUBIplan den Umsatz diesem Partner zu. Eine daraus angelegte Buchung übernimmt den Partner.

Die Namenssuche unterscheidet nicht zwischen Groß- und Kleinschreibung. Unicode-Schreibvarianten werden vereinheitlicht; „ß“ und „ss“ gelten dabei als gleich. Andere gewählte Filter gelten weiterhin.

## Umsätze bei der Bank abrufen

Ist die Bankanbindung eingeschaltet (Einstellungen › Module), steht oben die Karte „Umsätze bei der Bank abrufen“. Dort richtest du einen Bankzugang ein und holst die Umsätze mit deiner PIN und der Freigabe der Bank direkt ab. Die PIN wird nicht gespeichert. Abgerufene Auszüge tragen den Vermerk „Abruf“; die Antwort der Bank bleibt wie eine hochgeladene Datei als Original erhalten.
