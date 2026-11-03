# Aufbewahrung und Löschung je Datenart

Fachfrage FQ10 und FQ12 aus dem Gesamtaudit vom 02.11.2026. Die Übersicht zeigt je Datenart,
warum HUBIplan sie speichert, ab wann die Frist läuft und was danach passiert. Sie ist eine
Arbeitshilfe für Vorstand und Plattform-Verwaltung, keine Rechtsberatung. Die
Datenschutzhinweise des Vereins (Seite „Datenschutz“) stützen sich auf diese Tabelle.

## Grundsätze

- **Gesetzliche Fristen stehen fest im Code** und lassen sich nicht verkürzen (z. B. § 147 AO
  für Belege und Bücher). Länger aufbewahren geht: je Geschäftsjahr mit einer
  **Löschsperre** (Finanzen › Abschluss & Berichte, mit Grund, protokolliert), etwa bei einer
  laufenden Betriebsprüfung oder einem Rechtsstreit.
- **Einstellbare Fristen** haben einen Schutz vor zu frühem Löschen. Wird die Löschfrist für
  ehemalige Mitglieder (Plattform › Einstellungen) verkürzt, gilt die kürzere Frist erst
  30 Tage später; bis dahin wird nach der vorigen, längeren gelöscht. Verlängern gilt sofort.
  Fristen über Umgebungsvariablen (z. B. `OUTBOX_RETENTION_DAYS`) ändert nur, wer den Server
  betreibt; sie stehen in [betrieb.md](betrieb.md).
- **Gelöscht wird automatisch** durch tägliche Hintergrundaufgaben. Die Löschungen von
  Mitgliedsdaten stehen zusätzlich auf der Löschliste und gelten damit auch nach dem
  Einspielen eines älteren Backups ([betrieb.md](betrieb.md), „Wiederherstellen“).
- **Backups** enthalten gelöschte Daten noch bis zu `BACKUP_KEEP_DAYS` Tage (Standard 30).

## Übersicht

Abkürzungen: Art. 6 (1) b = Vertrag/Mitgliedschaft, c = rechtliche Pflicht,
f = berechtigtes Interesse, a = Einwilligung (DSGVO).

| Datenart | Zweck und Rechtsgrundlage | Frist beginnt | Danach |
|---|---|---|---|
| Stammdaten, Kontakt, Zusatzfelder, Zugehörigkeit, Ämter | Mitgliederverwaltung, Art. 6 (1) b | mit dem Ende der letzten Mitgliedschaft im Verein | nach der Löschfrist (Plattform, Standard 24 Monate) gelöscht; es bleiben Name, Geburtsjahr und Mitgliedszeiten |
| Rest nach der Löschfrist: Name, Geburtsjahr, Zeiträume | Vereinsgeschichte (Jubiläen, Ehrungen, Chronik), Art. 6 (1) f | – | bleibt, solange der Verein besteht; auf Widerspruch siehe „Chronik und Ehrungen“ |
| Würden, Begleitungen, Ehrungen, Wettbewerbsergebnisse | Vereinsgeschichte und öffentliche Chronik, Art. 6 (1) f | – | bleiben; jährliche Prüfung und Entfernen auf Wunsch (unten) |
| Mitgliederfoto | Ausweis und Akte, Art. 6 (1) a | Widerruf oder Löschfrist | beim Widerruf bzw. mit den Mitgliedsdaten gelöscht |
| SEPA-Mandate | Lastschrift, Art. 6 (1) b, c | letzte Lastschrift | 36 Monate nach der letzten Lastschrift ungültig (SEPA-Regel); Mandat bleibt als Beleg mit den Büchern |
| Rechnungen, Quittungen, Buchungsbelege, Kontoauszüge | Buchführung, Art. 6 (1) c, § 147 AO | Ende des Kalenderjahres, in dem das Geschäftsjahr endet | Belege nach 8 Jahren gelöscht (Finanzen › Abschluss, von Hand ausgelöst) |
| Bücher, Jahresabschlüsse | Buchführung, Art. 6 (1) c, § 147 AO | wie oben | nach 10 Jahren anonymisiert (Beträge bleiben) |
| Zuwendungsbestätigungen | § 50 EStDV, Art. 6 (1) c | wie oben | wie Belege |
| Postausgang (Mailtexte und Anhänge) | Nachweis des Versands, Art. 6 (1) b, f | Versand bzw. Anlage | zugestellt: Text und Anhänge nach 30 Tagen geleert, Kontaktformular nach 7; nicht zugestellt nach 90 Tagen (FQ14); Empfänger, Betreff und Art bleiben |
| Rundschreiben (versandt) | Information der Mitglieder, Art. 6 (1) b | – | bleiben nachlesbar; Empfängerliste wird mit den Mitgliedsdaten gelöscht |
| Eingänge an Mailverteiler | Versand und Missbrauchsschutz, Art. 6 (1) f | Eingang | mit dem Postausgang |
| Meldungen (Mannschaften, Aufgaben) | Organisation von Anlässen, Art. 6 (1) b | Datum des Anlasses | nach einem Jahr auf Name, Mannschaft und Aufgabe gekürzt |
| Änderungen zum Rückgängigmachen | Fehlerkorrektur, Art. 6 (1) f | Änderung | nach 30 Tagen gelöscht |
| Änderungsprotokoll | Nachvollziehbarkeit, GoBD, Art. 6 (1) c, f | – | Inhalte zu einer Person werden mit deren Löschung geleert (Kette bleibt prüfbar) |
| Exporte, Importe, Datenübernahmen | Arbeitsdateien, Art. 6 (1) f | Erstellung | nach 7 bzw. 30 Tagen gelöscht |
| App-Geräte | Anmeldung, Art. 6 (1) b | letzte Nutzung | nach 180 Tagen ohne Nutzung abgemeldet |
| Entwürfe in der App (nicht gesendet, nach dem Abmelden) | Kasse unterwegs, Art. 6 (1) b, c | Abmelden | nach 90 Tagen Rückfrage mit Export, nach 120 Tagen gelöscht; unlesbare sofort (FQ24) |
| Backups | Wiederherstellung, Art. 6 (1) f, Art. 32 | Erstellung | nach `BACKUP_KEEP_DAYS` Tagen |

## Chronik und Ehrungen (FQ12)

Namen ehemaliger Mitglieder in Würden, Begleitungen, Ehrungen und Wettbewerbsergebnissen
bleiben auch nach der Löschfrist, weil die Vereinsgeschichte ohne sie nicht vollständig ist
(berechtigtes Interesse, Art. 6 (1) f). Dafür gilt:

- **Zweck:** Vereinsgeschichte, Chronik auf der Webseite (nur Würden mit „in der Chronik auf
  der Webseite“), Jubiläen. Keine anderen Auswertungen.
- **Prüfung:** Der Vorstand sieht einmal im Jahr (z. B. vor der Jahreshauptversammlung) die
  öffentliche Chronik durch und entscheidet, ob Einträge ohne Bezug zur Vereinsgeschichte
  entfernt werden.
- **Widerspruch (Art. 21 DSGVO):** In der Akte des ehemaligen Mitglieds unter „Datenschutz“
  entfernt „Namen aus Chronik und Ehrungen entfernen“ den Namen aus Würden, Begleitungen und
  Wettbewerbsergebnissen dieses Vereins und seiner Einheiten (dort steht dann „Name auf
  Wunsch entfernt“) und löscht Ehrungen und Fotos dieser Würden. Jahre und Würden bleiben als
  Lücke. Ist die Person in keinem anderen Verein erfasst, wird auch ihr Name anonymisiert.
  Das geht erst nach dem Löschen der Mitgliedsdaten und steht auf der Löschliste.

## DSGVO-Auskunft bei Sammelrechnungen (FQ13)

Die Auskunft eines Mitglieds enthält Rechnungen an die Person vollständig. Aus
Sammelrechnungen an andere (z. B. an eine Abteilung) enthält sie nur die eigenen Posten,
mit Nummer, Datum, Betreff und Rechnungsempfänger als Zusammenhang; Posten, Anschrift und
Zahlungen anderer Personen und das PDF der ganzen Rechnung bleiben draußen.

## CAMT-Originale und spätere Importe

Einlesen, Entfernen und Fristbereinigung von Kontoauszügen werden je Verein serialisiert.
Mehrere Auszüge dürfen dasselbe unveränderte Original teilen; die Datei wird erst nach
erfolgreichem Commit und ohne verbleibenden Verweis entfernt. Ein fehlgeschlagener Import
entfernt nur neu angelegte Dateien. Der Import muss eine eigene äußerste Transaktion haben.

Fehlen im Auszug Periodendaten, dienen die enthaltenen Buchungstage als Fristanker. Bei
vollständig undatierten leeren Auszügen gilt konservativ das Importdatum. Bestehende fehlende
Periodendaten werden entsprechend ergänzt. Das verändert die Originaldatei nicht. Noch
vorhandene Originale können nach Fristablauf erneut bereinigt werden, auch wenn das Jahr
bereits einen Bereinigungsvermerk hat. Löschsperren gelten weiterhin.

Auszüge für bereits bereinigte Geschäftsjahre können nicht erneut eingelesen werden:
Sie würden entfernte personenbezogene Angaben zurückbringen. Eine fachlich notwendige
Wiederaufnahme benötigt eine gesonderte Entscheidung und Dokumentation.

Der Widerspruch gegen Chroniknamen ist mit neuen Mitgliedschaften derselben Person
serialisiert. Freitexte, fremde Partnerkopien und externe Veröffentlichungen gehören
weiterhin zur gesonderten Prüfung durch den Vorstand.

English: CAMT import, removal and retention cleanup are serialized per club. Shared original
files survive until their last reference is removed and the transaction commits. Failed
imports delete only newly created files. Missing statement periods use entry dates, or the
import date for completely undated empty statements. Existing missing dates are backfilled
without changing original files. Retention cleanup can revisit remaining originals; legal
holds still apply. Imports into already purged financial years are rejected to prevent
reintroducing personal data. History-name erasure shares the person's lifecycle lock;
free-text and external partner copies still require separate review.
