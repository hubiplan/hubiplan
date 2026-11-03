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
