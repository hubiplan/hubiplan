---
key: page.finance_incoming
titel: Finanzen › Rechnungseingang
modul: finance
rechte: [finance.view]
routen: [/finanzen/rechnungen/eingang]
stichworte: [E-Rechnung, ZUGFeRD, Eingang, Freigabe, XML]
---

Importiere XML-Rechnungen oder ZUGFeRD/Factur-X-PDFs. HUBIplan speichert das Original
auch bei fehlerhaften Rechnungen. Ein erneuter Import derselben Datei erzeugt keinen
zweiten Eingang. Andere Dateien mit derselben Rechnungsnummer musst du selbst auf
Dubletten prüfen.

**Rechnungspostfach**: Ist auf dem Server ein Rechnungspostfach eingerichtet, steht oben
die Adresse deiner Einheit, z. B. `rechnung+k7m2q9ab@example.org`. Gib sie deinen Lieferanten.
HUBIplan holt das Postfach jede Minute ab und übernimmt XML-Anhänge und ZUGFeRD/Factur-X-PDFs
wie beim Import. Beim Eingang steht dann **Per Mail von** mit dem Absender. Passt der Absender
zu keinem Geschäftspartner (E-Mail-Adresse unter Verein › Geschäftspartner), erscheint
**Absender unbekannt**; prüfe dann Rechnungssteller und Bankverbindung besonders genau.
Mails ohne E-Rechnung, etwa mit einer gewöhnlichen PDF-Rechnung, Spam oder Schadsoftware,
stehen unter **Hinweise aus dem Postfach**, bis du **Erledigt** wählst. **Neue Adresse vergeben**
macht die bisherige Adresse ungültig, etwa wenn sie Spam bekommt.

**Geschäftspartner**: HUBIplan schlägt zu jeder Rechnung einen Geschäftspartner vor, erkannt
an der USt-IdNr., der IBAN, dem Absender der Mail (auch die E-Mail-Adressen der
Ansprechpartner) oder am Namen. Mit **Vorschlag zuordnen** übernimmst du ihn, mit
**Als Geschäftspartner anlegen** legst du aus Name, USt-IdNr., IBAN und Absender einen neuen
Lieferanten an. **Zuordnung zum Geschäftspartner lösen** nimmt die Zuordnung zurück. Ordnest
du später eine Kassenbuchung zu, übernimmt sie den Geschäftspartner.

**Neue IBAN**: Weicht die IBAN der Rechnung von der beim Geschäftspartner gespeicherten ab,
warnt HUBIplan deutlich. Ruf den Rechnungssteller unter einer dir bekannten Nummer an, nicht
unter der aus der Rechnung, und setze vor der Freigabe **Neue IBAN telefonisch bestätigt**.
Die bestätigte IBAN speichert HUBIplan beim Geschäftspartner. So schützt du dich vor
gefälschten Rechnungen mit fremder Bankverbindung.

Die technische Prüfung (KoSIT) läuft nach dem Import im Hintergrund. Bis sie fertig ist,
steht beim Eingang **Wird geprüft**; das dauert meist unter einer Minute, die Seite
aktualisiert sich selbst. Abgelehnte Eingänge und Dateien, die keine lesbare E-Rechnung
enthalten, löscht HUBIplan nach 90 Tagen, wenn keine Buchung zugeordnet ist.

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
