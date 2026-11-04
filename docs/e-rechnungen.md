# Geschäftspartner und E-Rechnungen

Die allgemeinen Finanzmodule unterstützen Leistungsrechnungen an externe Kunden und
den Eingang strukturierter Rechnungen. Ein Musikmodul ist dafür nicht erforderlich.

## Bedienung

- **Finanzen → Geschäftspartner**: Kunden und Lieferanten mit strukturierten Anschriften
  anlegen. Ein Geschäftspartner braucht keine Mitgliedschaft. Nicht mehr benötigte
  Kontakte deaktivieren; ausgestellte Rechnungen behalten ihre eigenen Anschriften.
- **Rechnungen → Leistungsrechnungen**: Kunde, Einnahmekategorie, Leistungszeitraum,
  Rechnungssteller, Käuferreferenz, IBAN und Positionen erfassen. Preise sind netto,
  Zu-/Abschläge absolute Nettobeträge je Position. Der Steuersatz wird ausdrücklich
  gewählt: regulär, Nullsatz, steuerbefreit, Reverse Charge oder nicht steuerbar.
- **Prüfen und festschreiben**: KoSIT prüft die XRechnung vor der Freigabe. Bei Fehlern
  bleibt der Entwurf ohne Rechnungsnummer. Erfolgreiche Ausgabe archiviert XML,
  vollständigen Prüfbericht, Prüfsumme und lesbare PDF-Ansicht.
- **Zahlungen und Versand**: bestehende Rechnungsansicht mit Zahlungen, Mahnungen und
  Versand verwenden. Der Versand einer E-Rechnung enthält XML und lesbare Ansicht.
  Die gewählte Einnahmekategorie gilt für Zahlungseingänge. Gebührenpflichtige
  Mahnungen dürfen das ausgestellte Rechnungsoriginal nicht verändern und müssen
  separat abgerechnet werden.
- **Storno**: bei einer offenen Rechnung ohne Zahlungen wird ein ebenfalls validierter
  UBL-CreditNote-Beleg mit Nummer `<Rechnungsnummer>-S` und Bezug zum Original erzeugt.
  Das Original bleibt erhalten. Den Stornobeleg herunterladen und dem Empfänger
  übermitteln; ein Storno versendet nicht automatisch eine Nachricht.
- **Rechnungen → Rechnungseingang**: XML oder PDF mit eingebettetem XML hochladen.
  Original, extrahierte Daten und Prüfbericht werden auch bei fehlerhaften Rechnungen
  aufbewahrt. Identische Dateien werden je Organisation nur einmal aufgenommen.
  Erneute technische Prüfungen erhalten frühere Prüfberichte im Prüfexport.
- Vor einer fachlichen Freigabe Empfänger, Leistung, Betrag und Bankverbindung prüfen.
  Nach Zahlung kann eine passende, noch nicht zugeordnete Kassenbuchung verknüpft
  werden. Das Original wird zusätzlich als Kassenbeleg kopiert. Der Import selbst
  erzeugt weder eine Buchung noch eine Überweisung.

## Unterstützter Umfang

Ausgabe: XRechnung 3.0 in UBL 2.1, EUR, Rechnungen und vollständige Stornos,
positive Mengen/Preise, mehrere Steuersätze, Zu-/Abschläge je Position.
Die Umsatzsteuer wird je Steuerkategorie und Satz kaufmännisch gerundet. Die
Bruttobeträge der Positionen stimmen nach Restcentverteilung mit der Gesamtsumme überein.

Eingang: UBL Invoice/CreditNote und CII, einschließlich XML in ZUGFeRD/Factur-X-PDFs.
Für ZUGFeRD/Factur-X wird insbesondere das Profil EN16931 mit der Kennung
`urn:cen.eu:en16931:2017` geprüft. Profile, die das festgeschriebene Regelpaket nicht
kennt, werden archiviert, aber nicht zur fachlichen Freigabe zugelassen.
Die technische Validierung bezieht sich auf den XML-Inhalt und das vom Regelpaket
erkannte Profil. Sie zertifiziert weder die PDF/A-Konformität noch die inhaltliche
Übereinstimmung eines fremden PDF-Sichtteils mit dem XML. Maßgeblich ist das XML.

Noch nicht enthalten: ZUGFeRD-Ausgabe, Peppol/Portalübertragung, andere Ausgabewährungen,
Abschlags-/Schlussrechnungsautomatik, automatische Bankauszahlungen sowie Zuordnung
von Teilzahlungen zu Eingangsrechnungen. Unterschiedliche Dateien mit gleicher
Lieferanten-Rechnungsnummer müssen fachlich auf Dubletten geprüft werden.

## Betrieb und Prüfregeln

Das Backend-Image installiert eine Java-Laufzeit sowie KoSIT Validator 1.6.3 und
die Prüfkonfiguration XRechnung 3.0.2 vom 31.08.2026. Downloads erfolgen ausschließlich
beim Image-Bau über feste offizielle URLs mit SHA-256-Prüfung. Im Betrieb werden
keine Rechnungsdaten an externe Prüfstellen übertragen. Java ist auf 256 MB Heap und
ein Prüflauf auf 45 Sekunden begrenzt. DTDs und externe XML-Entitäten werden abgewiesen.

Bei Installation ohne das bereitgestellte Image die offiziellen Dateien über
`python install_einvoice_validator.py /opt/hubiplan-einvoice` installieren und Java
bereitstellen. `EINVOICE_VALIDATOR_DIR` kann das Installationsverzeichnis überschreiben.
Fehlt die Prüfung, ist keine Ausstellung oder fachliche Freigabe möglich.

Die Migrationen ergänzen Tabellen und optionale Felder; bestehende Beitragsdaten
werden nicht umgerechnet. Vor Rückmigration neue Originale und Geschäftspartner
vollständig exportieren. Alte Software versteht neue Empfängerarten nicht; bei
einem Anwendungsrollback keine neuen Leistungsrechnungen bearbeiten. Die zusätzlichen
Tabellen dürfen nicht vor Ablauf der Aufbewahrung gelöscht werden.

## Rechte, Archiv und Datenschutz

Geschäftspartner: bestehende Lese-/Schreibrechte für Rechnungen oder Kasse, jeweils
mit aktiviertem Modul. Ausgang: `billing.view/edit`. Eingang: `finance.view/edit`.
Alle neuen Tabellen verwenden organisationsbezogene RLS-Regeln. Kontakte,
Rechnungsinhalte, Prüfergebnisse und private Dateien werden verschlüsselt gespeichert.

Der GoBD-Prüfexport enthält `erechnungen.csv`, Originale, XML, Prüfberichte und
Stornobelege. Der allgemeine Datenexport übernimmt die neuen Tabellen und Dateien.
Die vorhandenen Fristen und Löschsperren gelten auch für die neuen Archive. Beim
Eingang ist das Empfangsjahr maßgeblich; Kassenbelege sind unabhängige Kopien.

Offizielle Quellen:
- [KoSIT Validator](https://github.com/itplr-kosit/validator)
- [Prüfkonfiguration XRechnung](https://github.com/itplr-kosit/validator-configuration-xrechnung)
- [FeRD: ZUGFeRD](https://www.ferd-net.de/standards/zugferd)
