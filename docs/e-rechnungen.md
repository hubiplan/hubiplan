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

## Rechnungspostfach

Lieferanten schicken E-Rechnungen meist per Mail. Ein Postfach je Server (z. B.
`rechnung@example.org`) nimmt sie für alle Einheiten an; jede Einheit hat eine Plus-Adresse mit
zufälliger Kennung (`rechnung+k7m2q9ab@example.org`), die unter Finanzen › Rechnungseingang
steht. **Neue Adresse vergeben** ersetzt die Kennung; Mails an die alte gehen dann keiner
Einheit mehr zu. Der Mailserver muss Plus-Adressen in das Postfach zustellen (Exim auf Hestia
tut das); nach dem Einrichten eine Probemail schicken.

Ablauf (`billing/incoming_mail.py`, Celery-Job `erechnungen-postfach` jede Minute):

- Zuordnung nur über die Plus-Adresse in `Delivered-To`, `X-Original-To`, `Envelope-To`, `To`
  oder `Cc` mit der Domain des Postfachs. Mails an keine bekannte Kennung bleiben gelesen im
  Postfach und erscheinen nirgends.
- Angenommen wird jeder Absender. Passt er zu keiner E-Mail-Adresse eines aktiven
  Geschäftspartners, zeigt der Eingang **Absender unbekannt**; geprüft wird bei der fachlichen
  Freigabe, die nichts auszahlt.
- XML-Anhänge und PDFs mit eingebettetem XML (ZUGFeRD/Factur-X) gehen nach der Virenprüfung
  denselben Weg wie das Hochladen: Original, Prüfung im Hintergrund, Dublettenschutz über den
  SHA-256 der Datei. Höchstens 10 Rechnungen und 15 MB je Datei, 25 MB je Mail. Dieselbe Mail
  (Message-ID) wird nur einmal übernommen.
- Übernommene Mails wandern in `EINVOICE_IMAP_DONE_FOLDER` (Standard `INBOX.Verarbeitet`, wird
  bei Bedarf angelegt; leer oder nicht anlegbar: nur gelesen). Mails ohne E-Rechnung, vom
  Spamfilter markierte Mails (`X-Spam-Flag`) und Mails mit Schadsoftware bleiben gelesen im
  Posteingang und erscheinen im Rechnungseingang als Hinweis.
- Ist der Virenscanner nicht erreichbar, bleibt die Mail ungelesen und kommt beim nächsten
  Abruf wieder dran.
- Einträge des Postfachs ohne übernommene Rechnung werden nach 90 Tagen gelöscht; die übrigen
  bleiben, solange es die Rechnung gibt. Gespeichert werden Absender und Betreff verschlüsselt
  sowie ein Hash der Message-ID, nicht der Mailtext.

Einstellungen (`.env`): `EINVOICE_IMAP_HOST`, `EINVOICE_IMAP_PORT` (993, TLS),
`EINVOICE_IMAP_USER`, `EINVOICE_IMAP_PASSWORD`, `EINVOICE_IMAP_FOLDER` (`INBOX`),
`EINVOICE_IMAP_DONE_FOLDER` und `EINVOICE_IMAP_ADDRESS` (angezeigte Grundadresse, Standard
der Benutzername). Auf Hestia legt `deploy/hestia/rechnungspostfach.sh` Postfach und Einträge an.
Ohne `EINVOICE_IMAP_HOST` gibt es kein Postfach und keine Adresse in der Oberfläche.

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

Zusätzlich verfügbar: Anzahlungsrechnungen (Typ 386), Schlussrechnungen mit Anrechnung
tatsächlich eingegangener Anzahlungen, ZUGFeRD/Factur-X EN16931 und eine konfigurierbare
HTTPS-Anbindung für Peppol-/Portal-Gateways. Noch nicht enthalten: andere Ausgabewährungen,
automatische Bankauszahlungen sowie Zuordnung
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

## Beitragsrechnungen an Mitglieder mit Leitweg-ID

Öffentliche Auftraggeber, die Mitglied sind (Stadt, Kreis, Behörde), nehmen Rechnungen oft
nur als XRechnung an. Unter Finanzen › Einrichtung › Rechnung & Zahlung schaltet der Verein
„Rechnungen an Mitglieder mit Leitweg-ID als E-Rechnung (XRechnung)“ ein. Dann bekommt jede
Rechnung an ein Mitglied, dessen Rechnungsanschrift eine Leitweg-ID trägt, beim Festschreiben
die fachlichen Daten (`billing/member_einvoice.py`) und läuft danach durch denselben Weg wie
Leistungsrechnungen: XML erzeugen, mit KoSIT prüfen, Original und lesbare Fassung ablegen,
XML an die Rechnungsmail hängen.

- Käufer: Name und Anschrift aus der Rechnungsanschrift (sonst Anschrift des Mitglieds),
  `BuyerReference` und elektronische Adresse = Leitweg-ID (Schema 0204), Bestellnummer als
  `OrderReference`.
- Verkäufer: Name und Anschrift aus Impressum bzw. Einheit; Ansprechpartner, Telefon, E-Mail
  aus den Beitragseinstellungen, sonst aus dem Kontakt der Einheit; Kennung aus den
  Beitragseinstellungen, sonst Registergericht und -nummer aus dem Impressum.
- Posten ohne Steuersatz sind nicht steuerbar (Kategorie O, „Echter Mitgliedsbeitrag, nicht
  steuerbar“); stehen steuerpflichtige Posten daneben, werden sie als steuerfrei (E) mit
  demselben Grund geführt. Gutschriften erscheinen mit Menge −1.
- Fehlt etwas oder schlägt die Prüfung fehl, bleibt die Rechnung ein Entwurf; im Beitragslauf
  bricht das Festschreiben dann mit der Meldung ab. Im Arbeitsbereich einer Untereinheit gibt
  es keine E-Rechnung.

## Anzahlungs- und Schlussrechnungen

Unter **Rechnungsart** die Anzahlungsrechnung wählen, prüfen und festschreiben.
Zahlungseingänge wie bisher bei der Rechnung erfassen. Eine Schlussrechnung enthält
die gesamte Leistung und wählt bereits bezahlte Anzahlungsrechnungen desselben Kunden
und Projekts. Auch Teilzahlungen werden angerechnet. EUR, positive Leistungen und
passende Steuergruppen sind erforderlich; Überanrechnung wird abgewiesen.

Das Original enthält BG-3-Bezüge, BT-113 (vereinnahmte Bruttoanzahlungen) und in BT-22
die Einzelaufstellung mit Zahlungstagen, Nettobeträgen und Umsatzsteuer. Die Aufstellung
muss fachlich geprüft werden. Änderungen der Zahlungseingänge nach Entwurfserstellung
verlangen erneutes Speichern und Prüfen. Beim Festschreiben werden die Zahlungen
einmalig zugeordnet; es entstehen keine weiteren Kassenbuchungen. Die Anzahlungsrechnung
erhält den Status „Abgerechnet“ und wird nicht weiter gemahnt. Die Schlussrechnung
weist nur den verbleibenden Zahlbetrag als offen aus. Ein Storno der Schlussrechnung
gibt die Anzahlungen wieder frei. Zugeordnete Anzahlungen und ihre Zahlungen können
erst danach storniert bzw. entfernt werden. Das ist keine automatische Bankauszahlung.

## ZUGFeRD erstellen

Bei festgeschriebenen Rechnungen bzw. Stornobelegen **ZUGFeRD erstellen und prüfen**
wählen. Der Server konvertiert das unveränderte UBL-Original nach CII EN16931 und
vergleicht Beträge, Steuergruppen, Positionen, Anschriften und Hinweise. Aus denselben
Daten wird eine lesbare Ansicht erzeugt, mit Ghostscript nach PDF/A-3b konvertiert
und das XML mit factur-x eingebettet. Lokale XSD-/Schematron-Prüfung sowie veraPDF
prüfen XML und endgültiges PDF. Erst danach steht die Ausgabe zur Verfügung.
XML, PDF und beide Prüfberichte werden privat mit Prüfsummen aufbewahrt. Wiederholte
Abrufe liefern dieselbe Datei. Die vorhandene XRechnung bleibt parallel erhalten.

Das Backend-Image enthält zusätzlich factur-x 7.9, Ghostscript und veraPDF 1.30.3.
Bei eigener Installation ist `install_pdf_validator.py` auszuführen; Ghostscript samt
sRGB-ICC-Profil muss verfügbar sein. Eine fehlende/fehlerhafte Prüfung sperrt nur
die neue Hybrid-Ausgabe. Es werden keine externen Prüfstellen aufgerufen.

## Anbieterneutrales Versand-Gateway

Eine Peppol-Teilnehmerregistrierung und ein Access Point sind weiterhin erforderlich.
HUBIplan selbst wird durch dieses Modul kein Access Point. Die Plattformverwaltung
richtet pro Verein ein Gateway ein, das folgenden festen HTTPS-Vertrag implementiert.
Ein vorhandener Anbieter wird über einen kleinen Adapter an diesen Vertrag angebunden.
Ohne Konfiguration bleiben Download und manueller Upload im Empfängerportal möglich.
Das Gateway ist für die Netz-/Empfängerprofilprüfung (z. B. Peppol BIS) verantwortlich;
KoSIT-Prüfung allein garantiert keine Annahme durch einen bestimmten Empfänger.

`EINVOICE_GATEWAYS` ist ein JSON-Objekt mit Organisations-IDs als Schlüsseln, z. B.:

```json
{"123":{"base_url":"https://gateway.example.org/v1","channel":"peppol","participant":"0204:BEISPIEL","label":"Vereinsgateway","token_env":"EINVOICE_GATEWAY_EXAMPLE_TOKEN"}}
```

Das benannte Secret wird separat als Umgebungsvariable bereitgestellt, niemals in der
Gateway-Konfiguration, im Datenexport oder Browser. Das Standard-Server-Compose leitet
alternativ `EINVOICE_GATEWAY_TOKENS` weiter: ein JSON-Objekt, das `token_env`-Namen auf
die jeweiligen Secrets abbildet. Beide JSON-Werte in der privaten Server-`.env` mit
einfachen Anführungszeichen umschließen; Zugangsdaten niemals ins Repository übernehmen.
`channel` ist `peppol` oder `portal`. Nur HTTPS ohne
URL-Zugangsdaten, Query oder Fragment ist zulässig. HTTP-Redirects sind gesperrt.
Absender und Empfänger kommen aus den elektronischen Adressen des festgeschriebenen
Originals; für Peppol sind vierstellige EAS-Codes erforderlich. Der Absender muss
zur für den Verein konfigurierten Teilnehmerkennung passen.

- `GET /documents/{request_id}`: Status lesen, `404` falls unbekannt.
- `POST /documents`: JSON mit `request_id` (UUID), `sha256`, `channel`, `sender`,
  `recipient`, `document` (`invoice`/`cancellation`), `content_type` (`application/xml`)
  und `content_base64` (unverändertes UBL-Original).
- Beide Aufrufe tragen `Authorization: Bearer <secret>`; POST zusätzlich einen stabilen
  `Idempotency-Key` mit derselben UUID. Der Adapter muss gleiche UUIDs dauerhaft
  deduplizieren und GET nach einem akzeptierten POST konsistent beantworten.
- Erfolg: HTTP `200`, `201` oder `202`, JSON mit passender `request_id`, `sha256`,
  `status` (`submitted`, `delivered`, `rejected`) und optional `reference` (max. 200 Zeichen).
  Referenzen dürfen keine personenbezogenen Daten, Geheimnisse oder URLs enthalten.
- `submitted` bedeutet nur Annahme durch den Anbieter. Zustellung wird über
  **Versandstatus abrufen** ausdrücklich abgefragt. Fehler/Timeouts führen zu
  „Übermittlung unbestätigt“. Jeder Wiederholungsversuch gleicht zuerst per GET ab;
  nur bei `404` wird dieselbe UUID erneut per POST übermittelt. Keine automatische
  Neuübermittlung, keine stillen Anbieterwechsel und kein automatischer Stornoversand.

Vor Freischaltung sind Sandbox-Registrierung, Empfängerprofil, Deduplizierung,
Statusabfrage und Quittung mit dem tatsächlichen Anbieter zu prüfen. Der lokale
Test verwendet ausschließlich einen simulierten Gateway-Vertrag.

Die Migration `0018` ergänzt Felder mit Datenbank-Defaults sowie RLS-Tabellen für
Zuordnungen, Hybrid-Archive und Versandprotokolle. Vor einem Software-Rollback neue
Ausstellungen und Übermittlungen anhalten; alte Software versteht angerechnete
Anzahlungen und „Abgerechnet“ nicht. Tabellen und Originale bleiben erhalten.

Quellen: [factur-x](https://github.com/akretion/factur-x),
[veraPDF](https://verapdf.org/software/),
[Ghostscript PDF/A](https://ghostscript.readthedocs.io/en/latest/VectorDevices.html),
[FeRD: Pflichtangaben](https://www.ferd-net.de/fileadmin/user_upload/FeRD/Downloads/Empfehlungen_zu_Pflichtangaben_in_einer_E-Rechnung/Empfehlungen_Pflichtangaben_E-Rechnung_gem_UStG_20250725.pdf).
