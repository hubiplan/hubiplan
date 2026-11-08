---
key: page.finance_einvoices
titel: Finanzen › Leistungsrechnungen
modul: billing
rechte: [billing.view]
routen: [/finanzen/rechnungen/leistungen, /finanzen/geschaeftspartner]
stichworte: [E-Rechnung, XRechnung, Geschäftspartner, Leistungsrechnung, EN16931]
---

Lege zunächst einen Kunden unter **Finanzen** → **Geschäftspartner** an. Eine Mitgliedschaft
ist nicht erforderlich. Unter **Rechnungen** → **Leistungsrechnungen** erfasst du eine
Rechnung mit Einnahmekategorie, Leistungszeitraum, Rechnungsanschriften, Käuferreferenz
und Zahlungs-IBAN. Preise sind netto und werden in EUR eingegeben.

Wähle die steuerliche Behandlung ausdrücklich. Steuerbefreit, Nullsatz und nicht
steuerbar sind unterschiedliche Angaben. Bei Befreiung, Reverse Charge oder
Nichtsteuerbarkeit ist ein Grund erforderlich. Die Kontaktdaten des Rechnungsstellers
einschließlich Kontaktperson und Telefon werden für XRechnung benötigt.
Ohne USt-IdNr. muss der Rechnungssteller eine eindeutige Geschäftspartnerkennung
angeben, beispielsweise seine mit dem Kunden vereinbarte Lieferantennummer.

**E-Rechnung prüfen** zeigt Fehler und Hinweise. **Prüfen und festschreiben** prüft
erneut und vergibt nur bei Erfolg die endgültige Rechnungsnummer. Danach bleiben
Rechnung und Anschriften unverändert. XML, Prüfbericht und lesbare Ansicht kannst
du herunterladen. Die technische Prüfung ersetzt keine Prüfung der Leistung und
der steuerlichen Behandlung.

Über **Zahlungen und Versand** öffnest du die bestehende Rechnungsansicht. Beim
Versand wird das XML zusammen mit der lesbaren Ansicht angehängt. Ein Storno erzeugt
zusätzlich einen eigenen strukturierten Stornobeleg mit Grund und Bezug auf Nummer und
Datum der Rechnung. **Stornorechnung per E-Mail senden** hängt XML und PDF an.

Unter **Rechnungsart** wählst du Rechnung, Anzahlungsrechnung oder Schlussrechnung.
Bei der Schlussrechnung erfasst du die gesamte Leistung und wählst bereits eingegangene
Anzahlungen desselben Auftraggebers und derselben Veranstaltung. Es entstehen keine
doppelten Einnahmen. Ändern sich Zahlungen zwischen Entwurf und Ausstellung, speichere
und prüfe den Entwurf erneut. Verrechnete Anzahlungsrechnungen heißen „Abgerechnet“.
Vor dem Entfernen ihrer Zahlungen musst du die Schlussrechnung stornieren.

**ZUGFeRD erstellen und prüfen** erzeugt aus dem Original eine lokal geprüfte PDF/A-Datei
mit eingebettetem XML. Danach kannst du **ZUGFeRD herunterladen**. Das gilt auch für
Stornobelege; Originale und Prüfberichte bleiben erhalten.

Für Peppol hinterlegst du beim Geschäftspartner und Rechnungssteller registrierte
elektronische Adressen samt EAS-Code. Die Plattformverwaltung richtet den gewählten
Anbieter pro Verein ein. **Elektronisch übermitteln** sendet ausdrücklich das Original;
**Versandstatus abrufen** fragt die Zustellbestätigung ab. Unbestätigte Übermittlungen
werden vor einem erneuten Versand beim Anbieter abgeglichen. Ein Storno wird separat
übermittelt. Ohne Anbieteranbindung nutzt du Download und manuellen Portal-Upload.
Bestehende Beitragsrechnungen bleiben unverändert nutzbar.
