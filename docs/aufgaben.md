# Aufgaben: Aufbau und Umsetzung

Aufgaben gelten für Plattform, Dachverbände, Vereine und Untereinheiten. Eigene Aufgaben
bleiben privat. Zusätzliche Sichtbarkeit entsteht ausschließlich durch ausdrückliche Freigaben.

## Bestandsaufnahme

- Die Startseitenkachel und die App-Verwaltung nutzen dieselben fachlichen Sammlungen.
  Aufgabenrechte und App-Navigation müssen zusätzlich ergänzt werden.
- Rollen kennen Bereiche mit Lesen und Bearbeiten. Aufgabenlesen erlaubt die Pflege eigener
  Aufgaben; Aufgabenbearbeiten erlaubt zusätzlich das Teilen.
  Bei der Neuanlage dienen Aufgabenrechte als Vorgabe. Ausdrücklich ausgewählte Rechte
  werden respektiert; reine Ämter ohne Zugriffsrechte bleiben ohne Zugang. Die Bestandsmigration
  ergänzt Rollen mit vorhandenen Zugriffsrechten, Vorstandsrollen erhalten Bearbeiten.
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

## Freigaben und Verantwortung

Freigaben an Personen und Rollen unterscheiden Lesen, Bearbeiten und Zuständigkeit.
Rollenfreigaben folgen aktiven Amtsinhabern. Nur das verantwortliche Konto teilt weiter,
löscht oder überträgt die Verantwortung an einen beteiligten Bearbeiter. Ein Rollenverwalter
mit Aufgabenbearbeitungsrecht kann eine verwaiste geteilte Aufgabe ausdrücklich übernehmen.
Diese begrenzte Verwaltungsprüfung liest zunächst nur Besitzdaten und liefert Aufgabennummern;
private Inhalte werden dabei nicht gelesen. Der normale Aufgabenabruf umgeht RLS nicht.

Persönliche Exporte enthalten eigene und aktuell berechtigt geteilte Aufgaben. Ein Exporteintrag
der Einheit enthält nur deren eigene geteilte Aufgaben, die das exportierende Konto sehen darf.
Beim Import wird der Inhalt dem importierenden Konto privat zugeordnet; Freigaben müssen
ausdrücklich neu vergeben werden. Fremde Konto- und Freigabenummern werden nicht übernommen.

Hinweise beim Teilen sind unter „Mein Konto › Benachrichtigungen“ pro Kanal abschaltbar. Mailtexte und Aufgabentitel
werden im allgemeinen Postausgang durch einen neutralen Versandvermerk ersetzt.

## Erinnerungen und Aufbewahrung

Die Kontovorgaben stehen unter „Mein Konto › Benachrichtigungen“. Je Aufgabe lassen sich
Zeitpunkte und Kanäle übersteuern. Zuständige werden erinnert; ohne Zuständige alle
beteiligten Bearbeiter. Rechte werden bei der Planung und unmittelbar vor dem Versand
erneut geprüft. Neue Rolleninhaber erhalten ausschließlich noch bevorstehende Erinnerungen.

Tagesfristen gelten bis zum folgenden lokalen Mitternachtsbeginn. Erinnerungen dafür
liegen um 8 Uhr am ausgewählten Kalendertag. Uhrzeitfristen verwenden den genauen Zeitpunkt
und Vorläufe von jeweils 24 Stunden pro Tag. Bei einer fehlenden Ortszeit gilt der nächste
gültige Zeitpunkt, bei einer doppelten die erste Ausprägung. Überfälligkeit erzeugt genau
einen zusätzlichen Versuch um 8 Uhr am Folgetag; danach bleibt die Hervorhebung bestehen.

Je Kanal wird ein Versuch atomar vor dem Versand beansprucht. Erfolg, Fehler und übersprungene
Versuche bleiben getrennt vermerkt; nach einem Absturz wird ein beanspruchter Versuch nicht
automatisch wiederholt. Friständerungen erhalten neue Versionen und überschreiben keine
vorhandenen Versandnachweise. Die Celery-Planung läuft alle fünf Minuten.

Private und geteilte erledigte Einzelaufgaben können optional nach zwölf Monaten in den
Papierkorb wechseln. Beide Vorgaben sind aus. Die gemeinsame Vorgabe benötigt Aufgaben-
und Rollenbearbeitungsrecht; Serienhistorie bleibt ausgenommen. Nach weiteren 30 Tagen
erfolgt die endgültige Bereinigung. Private Aufgaben bleiben im Kontoprofil auch nach
einem Rollenverlust exportierbar und endgültig löschbar.

## Anhänge und Dokumentverweise

Dateien verwenden den verschlüsselten privaten Speicher und dieselben Dateiarten,
20-MB-Grenze und Upload-Virenprüfung wie Dokumente. Das gemeinsame Speicherbudget
zählt auch private Aufgabenanhänge und deren Papierkorb mit. Eine Sperre der Einheit
verhindert, dass parallele Uploads gemeinsam das Budget überschreiten.

Jeder Abruf prüft die aktuelle Aufgabenfreigabe. Dokumentverweise prüfen zusätzlich
die Ablagerechte; ohne Zugriff werden weder Titel noch Dokumentnummer ausgegeben.
Entfernte Anhänge haben einen eigenen 30-Tage-Papierkorb. Endgültige Löschungen entfernen
Dateien erst nach erfolgreichem Commit; eine zurückgerollte Löschung erhält die Datei.

Der persönliche ZIP-Export enthält berechtigte Aufgaben, eigene Einstellungen und Dateien.
Eigene private Dateien bleiben nach Rollenverlust exportierbar. Einheitsexporte enthalten
nur berechtigte geteilte Aufgaben und deren eigene Dateien; der Import ordnet sie privat
dem importierenden Konto zu und übernimmt keine fremden Freigaben oder Verantwortlichen.
Dokumentnummern werden ausschließlich auf mitimportierte Dokumente umgesetzt.

## Serien

Eine konkrete Ausgabenfolge besitzt einen unveränderlichen Kalenderanker, einen Abstand,
eine Frist- oder Erledigungsbasis und optional Enddatum oder Gesamtzahl. Die Datenbank
erzwingt eine offene Ausgabe und eindeutige Ausgabennummern. Alle schreibenden Aufgabenwege
sperren zuerst die Serie und danach die Ausgabe. Erledigen und Folgeanlage sind atomar.
Verspätete Erledigung überspringt abgelaufene Kalenderplätze ohne den Zähler zu verbrauchen.

Vorlagenänderungen betreffen künftige Ausgaben; erledigte Historie bleibt bestehen.
Dokumentverweise und persönliche Erinnerungsregeln werden übernommen, Binärdateien nicht.
Wiederöffnen und Rückgängig ziehen ausschließlich eine unberührte direkte Folge zurück.
Diese bleibt intern mit ihren Sendemarken bestehen, ist aber aus Listen und Zählern
ausgenommen; ihre Ausgabennummer kann eine neue Aufgaben-ID erhalten. Erzwungenes
Rückgängig umgeht diese Prüfung nicht. Serien haben einen eigenen Papierkorb; ihre Historie
ist von der optionalen Einzelaufgaben-Aufbewahrung ausgeschlossen. Importierte Serien
behalten den Verlauf und starten mit abgeschalteter Fortsetzung und privaten Aufgaben.

## Freigaben über Ebenen

Erlaubte Ziele werden aus der Beziehung der Einheiten bestimmt und beim Schreiben erneut
geprüft. Gemeinsame Aufgaben bleiben im Quelldatenbereich; ihre RLS erlaubt ausschließlich
aktuell berechtigten Empfängern den Abruf aus der Zieleinheit. Ein eigener Aufgabenweg für
Rücknahmen prüft zuerst Akteur und Objektnummern und öffnet erst danach das konkrete Paket.

Bei getrennter Erledigung gehören Kopien und Ausgabenfolgen der Zieleinheit. Zentrale Felder
bleiben vorgegeben; lokale Notizen, Dateien und Beteiligte verbleiben dort. Die Quelle liest
eine gesonderte Fortschrittsprojektion ohne lokale Inhalte oder Dateien. Änderungen betreffen
nur offene Kopien, erhöhen ihre Versionen und erhalten erledigte Stände. Entfernte Ziele
oder gelöschte Quellen stoppen weitere Ausgaben und Quellanhänge; lokale Bestände bleiben.

RLS trennt Lesen, Schreiben und Löschen. Datenbanktrigger schützen Einheitenbeziehungen und
zentrale Kopienfelder. Eine begrenzte SQL-Funktion beantwortet ausschließlich die Besitz-
und Zielbeziehungsprüfung von Freigaben; ihr fester Suchpfad und die boolesche Rückgabe
vermeiden RLS-Rekursion und geben keine Aufgabeninhalte aus. Serienvorlagen bleiben für
andere Konten gesperrt; Regelmetadaten werden nach Aufgabenprüfung gezielt projiziert.
Exporte verwenden ausschließlich berechtigt sichtbare Ausgaben als Inhalt einer Vorlage,
damit eine einzeln freigegebene Ausgabe keine private Zukunftsvorlage mit exportiert.

## Termine und Mitgliederbereich

Eine Aufgabe kann einen Termin derselben Einheit verknüpfen. Der Abruf von Termindaten prüft die aktuellen Kalenderrechte unabhängig von den Aufgabenrechten. Eine gelöschte Veranstaltung entfernt nur die Verknüpfung.

Veröffentlichungen für Mitglieder sind ausdrücklich: einzelne aktuelle Mitglieder erhalten Lese- oder Erledigungsrechte, oder die Einheit bietet eine Aufgabe zum Übernehmen an. Angebote haben genau eine übernehmende Person. Jede Anfrage prüft Konto, Portalzugang, Mitgliedschaft und gegebenenfalls Untereinheit erneut. Eine gesonderte RLS-Prüfung und ein Feldtrigger erlauben Mitgliedern ausschließlich den freigegebenen Erledigungsstand. Lokale Notizen werden nicht ins Mitgliederportal projiziert. Folgeausgaben erben eine Veröffentlichung nur bei ausdrücklicher Freigabe.

## Getrennte Installationen

Das Aufgabenpaket ist standardmäßig ausgeschaltet. Die bestätigte Kopplung, die Empfangsannahme und eine ausdrückliche Freigabe jeder Aufgabe sind getrennte Voraussetzungen. Übernommene Aufgaben erhalten ein verantwortliches Konto und örtliche Freigaben; ein allgemeines Vorstandsrecht eröffnet keinen Inhaltszugriff.

Eigene Kopien haben einen unabhängigen Erledigungsstand und gegebenenfalls eine eigene Ausgabenfolge. Zentrale Inhaltsänderungen betreffen offene Kopien. Fortschrittsberichte enthalten ausschließlich Ausgabe, Frist, Status, Erledigungszeit und Beendigungskennzeichen. Notizen, eigene Dateien und Kontonamen bleiben vor Ort. Ein Widerruf stoppt weitere Aktualisierungen, Folgeausgaben und Quellanhänge; übernommene Kopien bleiben erhalten.

Gemeinsame Aufgaben werden beim Lesen und bei Statusänderungen frisch an der Quelle geprüft. Signierte, verschlüsselte Abfragen sind auf genau die freigegebene Kopplung und Aufgabe begrenzt. Versionsprüfung und Serien-/Aufgabensperren schützen gleichzeitige Änderungen. Ohne Quellbestätigung wird kein Erledigungsstand vorgespiegelt; widerrufene gemeinsame Inhalte werden nicht mehr ausgegeben. Gemeinsame Folgeausgaben entstehen ausschließlich an der Quelle. Bei einer empfangenen gemeinsamen Aufgabe wird vor der örtlichen Aufgabe ihre Verbundzuordnung gesperrt, passend zum Eingang von Aktualisierungen.

Quellanhänge werden in begrenzten Dateibereichen mit aktueller Freigabe abgerufen und vor der Weitergabe auf Typ und Viren geprüft. Dokumentverweise benötigen zusätzlich die heutigen Dokumentrechte des verantwortlichen Quellkontos. Empfangene Angebote und Fortschrittsstände sind verschlüsselt gespeichert. Datenimporte übernehmen keine fremden Verbundzuordnungen oder Freigaben.

Vor einem Rückweg auf eine Serverfassung ohne diese Funktion sind Aufgabenfreigaben zu widerrufen, betroffene Kopplungen zu pausieren und benötigte Bestände zu sichern. Zusätzliche Tabellen und Felder bleiben beim reinen Code-Rückweg zunächst erhalten; ein Rückmigrieren entfernt die Verbundzuordnungen.
