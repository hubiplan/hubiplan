---
key: page.finance_incoming
titel: Finanzen › Rechnungseingang
bereich: finanzen
modul: finance
rechte: [finance.view]
routen: [/finanzen/rechnungen/eingang]
stichworte: [E-Rechnung, ZUGFeRD, Eingang, Freigabe, XML]
---

Importiere XML-Rechnungen oder ZUGFeRD/Factur-X-PDFs. HUBIplan speichert das Original
auch bei fehlerhaften Rechnungen. Ein erneuter Import derselben Datei erzeugt keinen
zweiten Eingang. Andere Dateien mit derselben Rechnungsnummer musst du selbst auf
Dubletten prüfen.

Der Prüfbericht bezieht sich auf die XML-Daten. Die PDF/A-Eigenschaften und die
Übereinstimmung eines fremden PDF-Sichtteils mit dem XML werden nicht bestätigt.
Nutze die **Lesbare Ansicht** der strukturierten Daten zur Prüfung.

Prüfe vor der Freigabe Empfänger, Leistung, Betrag und Bankverbindung. Trage einen
Prüfvermerk ein und wähle **Fachlich freigeben** oder **Ablehnen**. Eine Freigabe ist
nur nach erfolgreicher technischer Prüfung möglich. Erneute Prüfungen erhalten
vorherige Prüfberichte im Prüfexport.

Der Import und die Freigabe führen keine Überweisung aus. Nach tatsächlicher Zahlung
kannst du eine passende Kassenbuchung zuordnen. Art, EUR-Betrag und noch offenes
Geschäftsjahr werden geprüft; Teilzahlungen sind hier noch nicht zuordenbar.
Das Original erscheint zusätzlich als Beleg der Kassenbuchung.
