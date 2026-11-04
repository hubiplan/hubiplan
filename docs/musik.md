# Musik und Auftritte

Die Plattform schaltet das Modul Musik je Verein frei. Rollen benötigen Musik-Lese- oder Bearbeitungsrecht. Für Auftritte wird zusätzlich Kalenderleserecht benötigt.

Unter **Musiker** ein Mitglied oder einen Gast erfassen. Die Mitgliedsakte verlinkt zum Musikerprofil. Unter **Instrumentale Fähigkeiten** Instrument und Register/Stimme eintragen; das Hauptinstrument markieren. Gäste können mit Kontaktangaben verwaltet und später deaktiviert werden.

Einen eigenen Einzeltermin im Kalender anlegen. Unter **Auftritte** diesen Termin wählen und Auftraggeber, Treffzeit/-punkt, Aufbau, Uniform, Spielform und Hinweise ergänzen. Spielzeit und Ort bleiben im Kalender. Serien benötigen einzelne Auftrittstermine. Aufgaben werden über **Aufgaben zum Auftritt** im bestehenden Aufgabenbereich gepflegt.

Unter **Sollbesetzung** je Instrument und Stimme eine benötigte Anzahl festlegen. Unter **Einteilungen** passende Musiker auswählen. Ein Musiker kann je Auftritt einmal eingeteilt werden. Eine passende Fähigkeit ist erforderlich. Zugesagte und fehlende Musiker werden je Position gezählt.

Mitglieder sehen ihre Einteilungen unter **Mein Bereich** und können zu- oder absagen. Die Musikverwaltung erfasst Rückmeldungen von Gästen. Kalenderabsagen bleiben beim Auftritt sichtbar. Technische Freigaben des Kalenders gelten auch für die Auftrittsverwaltung.

Der fünfminütige Hintergrundjob `music.performance_tasks.performance_reminders` informiert aktive Mitglieder mit aktivem Portalzugang über neue Einteilungen, Änderungen an Termin, Treff-/Aufbauzeit, Uniform, Stimme und Programm sowie Absagen. Er sendet ausschließlich neutrale Hinweise mit Link zum Mitgliederbereich über die bestehende Ausgangspost. Fingerabdrücke und Zeitstempel verhindern wiederholte Hinweise zum selben Stand; zwischenzeitliche Änderungen werden zusammengefasst. Fehlgeschlagene Zustellungen bleiben wiederholbar. Gäste ohne Portalzugang werden nicht angeschrieben. Bestehende Einteilungen werden bei Migration als Ausgangsstand markiert und lösen keine rückwirkende Einladung aus.

`remind_days` steuert je Auftritt die Erinnerung an offene Rückmeldungen (0 bis 30 Tage, Standard 3, 0 deaktiviert Erinnerungen). Es gilt der früheste Treff-, Aufbau- oder Spielbeginn. Erinnerungen erfolgen einmal je Informationsstand und mindestens einen Tag nach Einladung oder Änderung. Zugesagte, abgelehnte, abgesagte oder vergangene Einteilungen werden nicht erinnert. Zustandsdaten sind mandantengetrennt und im allgemeinen Export enthalten. Die Migration ist additiv; die Datenbankvorgabe des neuen Felds unterstützt den Rückweg auf die vorige Fassung.

Migrationen ergänzen eigene Tabellen mit Organisations-RLS. Mitgliedschaften und Termine werden nicht kopiert. Vor Rückmigration die Musikdaten über den allgemeinen Datenexport sichern.

## Besetzungsvorlagen und Sammeleinteilung

Unter **Besetzungsvorlagen** wiederverwendbare Instrumente, Register/Stimmen und Sollzahlen erfassen. Jede Stimme darf nur einmal enthalten sein. Zum Beispiel eine kleine Konzertbesetzung oder eine Marschbesetzung anlegen. Nicht mehr verwendete Vorlagen mit **Aktiv** ausschalten. Anlegen und Bearbeiten benötigen Musikbearbeitungsrecht; Lesezugänge sehen die Vorlagen.

Beim Auftritt **Besetzung planen** öffnen. Eine aktive Vorlage auswählen, die Positionen prüfen und **Vorlage anwenden** drücken. Fehlende Stimmen werden ergänzt, vorhandene Sollzahlen höchstens erhöht. Andere Stimmen, Einteilungen, Zusagen, Absagen und Vergütungsbezüge bleiben erhalten. Mehrfach vorhandene Positionen derselben Stimme vorher bereinigen. **Auftrittsbesetzung als Vorlage speichern** übernimmt die Sollpositionen in eine neue Vorlage; Musiker und Rückmeldungen werden nicht übernommen. Spätere Vorlagenänderungen verändern bestehende Auftritte erst beim erneuten Anwenden.

Unter **Sammeleinteilung** mehrere Musiker auswählen. Bei mehreren passenden Fähigkeiten die gewünschte Position wählen; ein Musikerprofil kann je Auftritt nur einmal eingeteilt sein. Angeboten werden aktive Mitglieder- und Gastmusikerprofile mit exakt passender Instrumenten-/Registerangabe und ohne vorhandene Einteilung. Angefragte und zugesagte Einteilungen belegen Sollplätze; bestehende Absagen bleiben im bisherigen Einteilungsbereich einzeln bearbeitbar.

**Ausgewählte Musiker anfragen** erzeugt neue Einteilungen mit Status Angefragt. Überschreitet die Auswahl die freien Sollplätze oder ist ein Verweis bzw. eine Fähigkeit nicht mehr gültig, wird die ganze Anfrage abgewiesen. Wiederholte Anfragen erzeugen keine doppelten Einteilungen oder Vorlagen. Fähigkeiten, Sollplätze und bekannte Verfügbarkeitskonflikte werden erneut vor dem Speichern geprüft. Kalenderfreigaben gelten auch für diese Auftrittsplanung.

Vorlagen und Vorlagenpositionen sind im allgemeinen Datenexport enthalten. Die additive Migration ergänzt zwei mandantengetrennte Tabellen. Vor einem Rückmigrieren die Vorlagen exportieren; bereits übertragene Sollpositionen und Einteilungen bleiben in den vorhandenen Tabellen erhalten.

## Verfügbarkeiten und Ersatzmusiker

Unter **Verfügbarkeiten** Abwesenheitszeiträume für aktive Mitglieder und Gäste eintragen, bearbeiten oder entfernen. Musikleserecht erlaubt das Anzeigen, Musikbearbeitungsrecht die Verwaltung. Aktuelle Mitglieder mit aktivem Musikerprofil können im eigenen Bereich **Meine Abwesenheiten** selbst pflegen, auch ohne bereits eingeteilt zu sein. Es werden nur Beginn und Ende gespeichert, keine Begründung. Das Ende gehört nicht mehr zum Zeitraum; direkt anschließende Termine überschneiden sich nicht.

Die Prüfung berücksichtigt im selben Verein Abwesenheiten, angefragte oder zugesagte andere Auftritte, aktive Probeneinteilungen und Kalenderzusagen. Bei Auftritten beginnt der belegte Zeitraum mit der frühesten Treff-, Aufbau- oder Spielzeit und endet mit dem Kalendertermin. Probenserien berücksichtigen verschobene, abgesagte und einzeln abgelehnte Termine. Eine Kalenderabsage zum Zieltermin verhindert ebenfalls eine neue Einteilung oder Zusage. Fahrt- und Pufferzeiten über entsprechende Treffzeiten oder zusätzliche Abwesenheitszeiträume planen. Andere Vereine und private Kalender ohne Vereinszusage sind nicht Teil dieser Prüfung.

Die Planung zeigt nur **Abwesend**, **Terminüberschneidung**, **Für diesen Termin abgesagt** oder **Kein Konflikt bekannt**. Titel, Orte, Notizen anderer Termine und Abwesenheitsgründe werden nicht ausgegeben. Kein bekannter Konflikt ist noch keine Zusage. Vor Einzel- und Sammeleinteilung sowie vor einer eigenen Auftritts- oder Probenzusage wird erneut geprüft. Eine ungültige Sammelauswahl wird vollständig abgewiesen; Absagen bleiben möglich.

Neue Abwesenheiten oder geänderte Kalendertermine können bestehende Einteilungen nachträglich widersprüchlich machen. Sie werden markiert, aber nicht automatisch entfernt oder abgesagt; Vergütungen bleiben unverändert. Die betreffende Einteilung bei Bedarf gezielt absagen. Bei einer Absage unter **Besetzung planen** auf **Ersatz suchen** klicken. Angezeigt werden konfliktfreie aktive Musiker mit derselben Stimme, passende Hauptinstrumente zuerst. Ersatzmusiker auswählen und wie gewohnt anfragen. Die bisherige Absage bleibt bestehen. **Alle Kandidaten anzeigen** beendet den Ersatzfilter; **Auswahl zurücksetzen** leert eine noch nicht gespeicherte Auswahl.

Abwesenheiten sind mit ihren Musikerbezügen im allgemeinen Datenexport enthalten. Die zusätzliche Tabelle ist mandantengetrennt. Vor einem Rückmigrieren Abwesenheiten exportieren; ältere Fassungen berücksichtigen sie bei der Besetzungsplanung nicht.

## Auftrittsabrechnung

Mit Musik- und Kalenderleserecht sowie freigeschalteter Kasse und Kassenleserecht öffnest du beim Auftritt die **Auftrittsabrechnung**. Zum Bearbeiten ist Kassenbearbeitungsrecht nötig. Vereinbartes Honorar, Fahrtkosten und weitere Leistungen als Bruttobeträge in EUR speichern. Mit zusätzlichem Rechnungsbearbeitungsrecht entsteht daraus ein Entwurf im bestehenden E-Rechnungseditor. Käufer und Gesamtbruttobetrag müssen zur Vereinbarung passen. Netto, Steuerkategorien und Rechnungsangaben dort ausdrücklich erfassen; prüfen, festschreiben, versenden und Zahlungseingänge in der Rechnungsansicht bearbeiten. Je Auftritt wird eine Veranstalterrechnung verknüpft.

Für jede Einteilung Gage, Pauschale und belegte Auslagen erfassen. Nach dem Auftritt die Teilnahme bestätigen und die Vergütung freigeben. Freigegebene Beträge sind gesperrt; ohne Auszahlung kann die Freigabe aufgehoben und der Entwurf erneut bearbeitet werden. Mitglieder sehen ausschließlich ihre eigene freigegebene Vergütung im eigenen Bereich. Die Abrechnung von Gästen führt die Kassenverwaltung.

Auszahlungen zuerst als Ausgaben mit Belegen in der Kasse erfassen. Anschließend nach Buchungstext suchen und die passende vollständige Zahlung zuordnen. Je Vergütung ist eine aktive Auszahlung möglich; Teilzahlungen werden nicht zugeordnet. Weitere Auftrittskosten werden ebenso mit vorhandenen Ausgaben verknüpft. Dieselbe Buchung kann nur einmal verwendet werden. Dies erzeugt keine Überweisung.

Fehlerhafte Auszahlungen in der Kasse stornieren. Der ursprüngliche Bezug bleibt sichtbar; die Vergütung ist wieder unbezahlt und kann nach Korrektur neu zugeordnet werden. Die Übersicht zeigt vereinbarte und fakturierte Beträge, tatsächliche Einnahmen und Ausgaben sowie das Ergebnis aus diesen Zahlungen. Freigegebene Vergütungen sind separat ausgewiesen und stellen keine bereits erfolgte Zahlung dar.

Allgemeiner Datenexport und Finanzprüfexport umfassen Vereinbarungen, Vergütungen und Buchungszuordnungen. Finanzaufbewahrung und Anonymisierung umfassen die Abrechnungsvermerke.

Eine vollständig stornierte Veranstalterrechnung kann mit **Stornierte Rechnung ersetzen** abgelöst werden. Danach die Vereinbarung korrigieren und eine neue Rechnung erstellen. Frühere Rechnungen bleiben verknüpft und im Prüfexport nachvollziehbar.

## Notenbestand und Programme

Unter **Musik** → **Notenbestand** zuerst Stücke mit Komponist und dann Ausgaben/Arrangements mit Arrangeur, Verlag, Dauer in Sekunden, Schwierigkeit, Besetzung und Lizenzhinweisen erfassen. Nicht mehr verwendete Arrangements archivieren. Unter **Stimmenbestand** je Instrument und Register/Stimme die benötigten Spieler, Exemplare, Lagerorte und das Konzert- oder Marschbuchformat angeben. Partituren gesondert als Partitur erfassen. Mehrere Lagerorte/Bestände werden für dieselbe Stimme addiert; die höchste Spieleranforderung gilt.

Digitale Dateien in der bestehenden **Dokumente** hochladen und unter **Notenunterlagen** dem Arrangement und optional einer Stimme zuordnen. Zum Verknüpfen und Öffnen ist zusätzlich Dokumentenleserecht erforderlich. Freigaben und Löschungen wirken sofort auf die Verknüpfung. Musikrechte erweitern keine Dokumentenfreigabe. Lizenz- und Nutzungshinweise erfassen; eine Bestandszahl oder Datei gewährt keine Kopier- oder Aufführungsrechte.

Beim Auftritt **Musikalisches Programm** öffnen. Stücke und Zugaben mit Arrangement, Pausen mit eigener Dauer hinzufügen. Eine leere Dauer übernimmt die Arrangementdauer; ein eigener Wert überschreibt sie. Programmpunkte bearbeiten, entfernen und nach oben/unten verschieben. Angezeigt werden reguläre Dauer einschließlich Pausen, Zugaben und Gesamtdauer. Null bedeutet unbekannte Dauer und wird markiert.

Die Vorbereitungsliste vergleicht benötigte Instrumente/Stimmen mit Sollbesetzung und aktiven Musikern mit Zusage. Schreibweisen werden ohne Groß-/Kleinschreibung und äußere Leerzeichen verglichen; unterschiedliche Instrumentenbezeichnungen bleiben getrennt. Fehlende Musiker, geplante Anzahl und fehlende Exemplare im gewählten Format bleiben sichtbar. Exemplare im anderen Format zählen nicht mit. Bei wiederholten Stücken wird derselbe Notensatz je Format einmal vorbereitet. Fehlende Besetzungsangaben werden markiert. Bestandsänderungen und Arrangementdauern wirken auf bestehende Programme.

**Programmliste herunterladen** und **Stimmenliste herunterladen** geben CSV-Dateien aus. Über **Aufgaben für Notenvorbereitung** im bestehenden Aufgabenbereich Aufgaben mit dem Auftrittstermin anlegen. Programme erfordern Musik- und Kalenderleserecht; Änderungen Musikbearbeitungsrecht. Der allgemeine Datenexport enthält den Katalog und Programme. Digitale Dateien verbleiben im vorhandenen Dokumentenexport.

## Proben und persönliche Noten

Unter **Proben und Notenausgabe** eigene Kalendertermine oder Terminserien als Proben verknüpfen. Datum, Ort, Wiederholung und Einzelabsagen werden im bestehenden Kalender gepflegt. Probenschwerpunkt und Probenstücke bilden die gemeinsame Serienvorlage. Unter **Probeneinteilung** Musiker zuordnen; nicht mehr benötigte Einteilungen deaktivieren. Gäste werden durch die Musikverwaltung betreut.

Unter **Nächste Proben** beim gewünschten Termin **Probenprogramm bearbeiten** öffnen. **Nur diesen Termin** speichert einen eigenen Schwerpunkt und eine eigene Stückliste; Stücke können ergänzt, entfernt oder mit eigenen Schwerpunkten versehen werden. Auch ein leeres Einzelprogramm ist möglich. **Gesamte Serie** lädt und ändert die gemeinsame Vorlage. Bereits individuell geplante Termine behalten ihre Inhalte, alle anderen übernehmen die geänderte Vorlage. **Serienprogramm übernehmen** entfernt das Einzelprogramm und verwendet wieder die aktuelle Vorlage. Die Bereiche Probenplanung und Probenstücke bearbeiten weiterhin die Vorlage.

Einzelprogramme gehören zum ursprünglichen Beginn der Kalenderregel. Beim Verschieben eines Termins bleiben sie erhalten; Rückmeldungen ändern sich durch Programmänderungen nicht. Ändert sich die Serienregel, werden Programme ohne passenden ursprünglichen Beginn nicht angezeigt und müssen beim gewünschten neuen Termin erneut geplant werden.

Die Übersicht zeigt Termine von 14 Tagen vor heute bis 90 Tage voraus. Jede Zu-/Absage gehört zum ursprünglichen Einzelbeginn der Kalenderregel; verschobene Termine bleiben diesem Beginn zugeordnet. Nach einer Änderung der Serienregel sind neue Rückmeldungen erforderlich. Zu abgesagten oder begonnenen Proben ist keine Rückmeldung mehr möglich. Fehlende Antworten erscheinen in der Übersicht.

Aktuelle Mitglieder mit aktivem Musikerprofil sehen unter **Mein Bereich** eigene Proben und Auftritte, deren tatsächlich gültige Programme, Schwerpunkte und passende Noten. **Noten für diesen Probentermin** zeigt Dateien aus dem jeweiligen Einzelprogramm oder der geerbten Vorlage. Für Notendownloads gelten die Mitgliederfreigaben der Dokumentenablage zusätzlich zur passenden Stimme oder instrumentalen Fähigkeit. Entfernte Stücke geben keine Dateien mehr frei, soweit sie nicht für andere eigene Termine benötigt werden. Für Proben zählen die angezeigten 14 Tage rückwärts und 90 Tage voraus; abgesagte Proben und eigene Absagen geben keine Noten frei. Gesperrte, gelöschte und fremde Unterlagen bleiben unzugänglich.

**Notenausgabe** erfasst Musiker, Stimme, Anzahl und Rückgabefrist. Jede Ausgabe reduziert den freien Bestand. Teilrückgaben sind möglich und bleiben mit Zeitstempel nachvollziehbar. Ausstehende Ausgaben verhindern das Verkleinern oder Umwidmen des Bestands. Überfällige Rückgaben sind markiert; Mitglieder sehen ihre eigenen offenen Mengen. Bei der Vorbereitung werden frei verfügbare Exemplare und bereits bei Eingeteilten befindliche Exemplare getrennt angezeigt.

Neue Probeneinteilungen und bevorstehende offene Rückmeldungen erzeugen neutrale Hinweise über die bestehende Ausgangspost. Der stündliche Job erinnert je Probentermin einmal innerhalb der eingestellten Tage; 0 schaltet Erinnerungen aus. Nachrichten enthalten einen Link zum Mitgliederbereich, keine Notenanhänge oder vertraulichen Termininhalte. Gäste ohne Mitgliederzugang erhalten diese Hinweise nicht. Vorbereitungsaufgaben und weitere Kalenderkommunikation bleiben im bestehenden Aufgaben-/Terminbereich.

Die Proben-, Rückmeldungs-, Einzelprogramm- und Notenausgabedaten sind im allgemeinen Datenexport enthalten. Die Datenbankmigration ergänzt Tabellen, RLS und Mengengrenzen; vor einem Rückweg die neuen Verläufe exportieren. Einzelprogramme sind zusätzliche Tabellen; frühere Fassungen ignorieren sie und zeigen nur die Serienvorlage.
