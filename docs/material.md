# Materialverwaltung

Die App `backend/materials` verwaltet einzelne Inventarteile im Datenbereich einer
Organisation oder Untereinheit. Die Weboberfläche liegt unter `/material`.
Das optionale Modul `material` wird in der Plattformverwaltung freigeschaltet.
Anschließend vergibt die Rollenverwaltung `material.view` beziehungsweise `material.edit`.
Bestehende Rollen erhalten keine zusätzlichen Rechte durch eine Datenmigration.

## Bedienung

Ein Teil hat eine automatisch aus seiner Kennung gebildete Inventarnummer, Bezeichnung,
Kurzbeschreibung, Verwendungszweck, Zustand und Standort. Der Standort ist entweder eine
Mitgliedschaft oder eine freie Adresse. Der Mitgliedsbezug setzt Leserecht auf die
Mitgliederdaten voraus. Eine freie Adresse ist für Materialleser dieser Einheit sichtbar.

Material kann mehrere Termine, Terminreihen, konkrete Vorkommen, Aufgaben und Dokumente
verwenden. Die bestehenden Ansichten zeigen Rückverweise auf berechtigt sichtbares Material.
Das Anlegen einer Aufgabe mit Materialbezug speichert Aufgabe und Verknüpfung gemeinsam.
Eine erledigte Aufgabe verändert den Standort nicht.

Fotos lassen sich als JPEG, PNG oder WebP bis 10 MB und 20 Millionen Pixeln hochladen.
Nach Virenprüfung, Anwendung der Bildorientierung und Entfernung der Metadaten wird eine
JPEG-Datei mit höchstens 1600 Pixel Kantenlänge gespeichert. Die API liefert sie nur nach
erneuter Rechteprüfung mit `Cache-Control: private, no-store`. Bilder zählen einschließlich
zurückgehaltener Fassungen zum gemeinsamen Dateibudget. Die Dokumentenablage bleibt der
Ort für Anleitungen, Kaufbelege und andere verknüpfte Dokumente.

## Termine und Rechte

Reihenbezüge verwenden die vorhandene Kalenderregel. Einzelbezüge speichern
`original_start`, sodass eine Verschiebung ihren Bezug erhält. Ausschlüsse gelten für ein
einzelnes Vorkommen. Ändert sich die Serienregel, gelten betroffene Zuordnungen bis zur
erneuten Zuordnung als prüfbedürftig. Änderungen an Einmalterminen folgen dem Termin.
Kommende Verwendungen werden für das nächste Jahr dargestellt; es entstehen keine
verbindlichen Reservierungen oder automatischen Standortwechsel.

Jeder Abruf verlangt das Materialrecht im aktiven Einheitenkontext. Private Aufgaben
und nicht zugängliche Dokumente erscheinen nicht in Listen, Suchergebnissen oder Zählern.
Aufgabenverknüpfungen benötigen zusätzlich Bearbeitungsrecht auf der Aufgabe.
Dokumentenabrufe folgen der aktuellen Fassung und prüfen die Ablagerechte erneut.
Verknüpfungen über Organisationsgrenzen sind nicht zugelassen.

RLS trennt Organisationen und Untereinheiten. Datenbanktrigger prüfen zusätzlich die
Einheit des Materials, seiner Mitgliedschaft und seiner Verknüpfungen. Schreibzugriffe
sperren das Teil und verlangen seine aktuelle Version; veraltete Eingaben erhalten HTTP 409.
Beschreibung, Zweck, Adressen, Hinweise und Verlaufsdaten verwenden verschlüsselte Felder.

## Verlauf und Aufbewahrung

Material hat einen eigenen Verlauf mit Zeitpunkt, Akteur und Änderungsart. Die letzte
eigene Änderung kann zurückgenommen werden, wenn alle dafür benötigten Ziele und Rechte
noch vorhanden sind. Auch Bilder können zurückgeholt werden. Private Verknüpfungen werden
nicht in das allgemeine Vereinsprotokoll kopiert; fremde Verknüpfungsänderungen werden im
Materialverlauf ausgeblendet.

Ausgesonderte Teile werden standardmäßig ausgeblendet und können nicht neu zugeordnet
werden. Vorhandene Zuordnungen bleiben zur Klärung erhalten. Papierkorb, alte Bildfassungen
und Verlaufsdaten haben eine Aufbewahrung von 30 Tagen. `materials.tasks.purge_deleted`
bereinigt täglich; Dateien werden erst nach erfolgreichem Datenbank-Commit entfernt.
Beim endgültigen Entfernen von Mitgliedsdaten wird ein betroffener Standort zu „Zu klären“.

## Schnittstellen und Datenübernahme

Basisadressen sind `/api/orgs/<id>/materials/` und `/api/depts/<id>/materials/`.
Darunter liegen Einzelobjekte, `choices/`, `<id>/links/`, `<id>/photo/`, `<id>/history/`,
`<id>/restore/` und `<id>/documents/<document-id>/`.

Die Liste unterstützt Suche, Zustand, Archiv, Papierkorb, Prüfhinweise und Rückverweise
über `member`, `event`, `todo` oder `document`. Ein konkretes Vorkommen ergänzt
`original_start`. Listen werden mit 50 Einträgen pro Seite ausgegeben.
`export=1` erstellt mit zusätzlichem Exportrecht eine CSV-Inventarliste.

Der vollständige Datenexport und Untereinheitsexport übernehmen nur Material im
berechtigten Bereich. Aufgabenverweise beschränken sich dort auf tatsächlich exportierbare,
geteilte Aufgaben. Der Import setzt Kennungen auf importierte Ziele um; fehlende
Mitgliedsstandorte und Terminziele bleiben als zu klärende Angaben erhalten. Fotos sind
in Dateiübernahme und Backup-Dateifeldregister eingebunden. Der Verlauf wird nicht exportiert.

## Migration und Rückweg

Die Materialmigrationen ergänzen neue Tabellen, Constraints, RLS und Trigger. Bestehende
Tabellen werden nicht umgebaut. Eine vorherige Programmfassung ignoriert die neuen Tabellen
und Daten. Für einen Programm-Rückweg können sie erhalten bleiben; das Rückmigrieren auf
`materials zero` entfernt die Materialtabellen und damit die dort gespeicherten Daten.
Fotos erst nach gesicherter Entscheidung zur endgültigen Entfernung bereinigen.

Die native Android-Oberfläche und verbindliche Reservierungen sind eigenständige spätere
Erweiterungen. Die Weboberfläche ist auch auf dem Smartphone nutzbar.

## Infrastruktur

Ortsfeste Einrichtungen wie Schießstand, Schützenhaus oder Vereinsheim stehen im selben
Bestand (`MaterialItem.kind = "facility"`, Kennung `INF-…`). Sie haben ein eigenes optionales
Modul `infrastructure`, eigene Rechte (`infrastructure.view`/`.edit`), die Oberfläche
`/infrastruktur` und die Schnittstellen `/api/orgs/<id>/facilities/` bzw.
`/api/depts/<id>/facilities/` mit denselben Unteradressen wie beim Material.
Konzept: Projektordner `konzepte/infrastruktur.md`.

Zusätzliche Angaben: Art (`facility_type`), Eigentum und Nutzung, Kapazität, Zugangshinweis
(verschlüsselt) und bei Schießständen die Bahnen je Disziplin (`lanes`, Schlüssel aus
`competitions.targets.FACILITIES`). Ein Verwendungszweck ist nicht nötig.

- **Bereiche:** Eine Infrastruktur mit Standort „Bereich einer Infrastruktur“
  (`location_kind = "facility"`) ist Teil einer anderen, z. B. Saal oder Luftgewehrstand.
  Es gibt nur eine Ebene.
- **Material in einer Infrastruktur:** Material kann als Standort eine Infrastruktur haben;
  „Gehört zu“ (`belongs_to`) verbindet Material wie Schlüssel mit einer Infrastruktur.
  Die Detailseite der Infrastruktur zeigt beides nur mit Materialleserecht.
- Ein Datenbanktrigger erlaubt Standort und Zugehörigkeit nur innerhalb derselben Einheit
  und nur auf Infrastruktur.
- **Schießinfrastruktur:** `Organization.shooting_facilities = "infrastructure"` übernimmt
  die Disziplinen aus den Bahnen aller nutzbaren Schießstände
  (`competitions.targets.available_facilities`).

Migration `materials 0004` ergänzt nur Spalten mit Vorgaben, Constraints und den Trigger;
eine vorherige Programmfassung ignoriert sie. Beim Rückweg auf eine ältere Fassung
erscheint Infrastruktur dort als gewöhnliches Material.

## Buchungskalender und Belegung

Infrastruktur und Material können einen Buchungskalender bekommen (`MaterialItem.booking_rules`,
Feld `enabled`). Die Regeln legen fest, ob Buchungen eine Freigabe brauchen (`approval`), wie viele
Minuten Rüstzeit vor und nach einer Buchung frei bleiben (`buffer_before`, `buffer_after`), wie weit
im Voraus gebucht werden darf (`horizon_days`) und was später die Webseite zeigen darf (`website`).

Die App `bookings` speichert `Booking` (Zweck, Zeit, Wiederholung, Status, Sichtbarkeit,
optionaler externer Kontakt, Verknüpfung mit Termin oder Wettbewerb), `BookingException`
(abgesagte Einzeltermine einer Serie) und `BookingSlot` (ausgerechnete Belegungen je Objekt).
Eine Datenbank-Ausschlussbedingung (btree_gist) verhindert überlappende bestätigte Belegungen
desselben Objekts einschließlich Rüstzeit. Wer ein Gebäude bucht, belegt auch alle Bereiche.
Serien werden zwei Jahre im Voraus ausgerechnet; die nächtliche Aufgabe `bookings.extend_series`
rollt sie weiter.

Ist eine Buchung mit einem Termin oder Wettbewerb verknüpft, übernimmt sie dessen Zeiten. Wird der
Termin verschoben und ist die neue Zeit belegt, bleibt die Buchung als Anfrage mit „prüfen“
stehen; wird er abgesagt, wird auch die Buchung storniert.

Rechte: Den Kalender sieht, wer das Leserecht auf Material bzw. Infrastruktur oder das neue Recht
**Belegung** (`bookings.view`) hat. Buchen darf, wer `bookings.view` oder Bearbeitungsrecht auf
das Objekt hat; ohne Freigaberecht ist die Buchung bei Objekten mit Freigabe zunächst eine
Anfrage. Freigeben und für andere eintragen darf, wer `bookings.edit` oder Bearbeitungsrecht auf
das Objekt hat. Defekte und ausgemusterte Objekte sind nicht buchbar.

Schnittstelle: `/api/orgs/<id>/bookings/` bzw. `/api/depts/<id>/bookings/` mit `items/`,
`choices/`, `<pk>/`, `<pk>/decision/` und `<pk>/skip/`. Buchungen werden mit dem Modul exportiert
und importiert; die Belegungen werden beim Import neu ausgerechnet.

Migration und Rückweg: `materials/0005` ergänzt `booking_rules` (Standard leer), `bookings/0001`
legt die Tabellen samt Zeilensicherheit an. Für den Rückweg `migrate bookings zero` und
`migrate materials 0004` vor dem Zurückspielen der älteren Fassung.

### Belegung auf der Webseite

`booking_rules.website` bestimmt je Objekt, was die Webseite zeigt: `off` (Standard) nichts, `busy`
nur belegte Zeiten („Belegt“), `titles` zusätzlich den Zweck von Buchungen mit Sichtbarkeit
„öffentlich“. Namen und Kontaktdaten erscheinen nie. Der Webseitenbaustein `bookings` ist
anfangs aus. Öffentliche Schnittstelle: `/api/public/site/v1/<key>/bookings/?start=JJJJ-MM-TT`
(sieben Tage, Objekte mit Kennung statt Nummer) und `/api/public/site/v1/<key>/bookings.ics`
(Abo, eine Woche zurück und 180 Tage voraus). Die Vereinswebseite zeigt das unter `/belegung/`.

### Anfragen aus dem Mitgliederbereich

Mit `booking_rules.portal` dürfen Mitglieder ein Objekt im Mitgliederbereich anfragen
(`/api/portal/<zugang>/bookings/`, Stornieren über `…/<pk>/cancel/`). Sie sehen nur belegte
Zeiten (fremde Zwecke als „Belegt“) und ihre eigenen Anfragen; jede Anfrage braucht eine
Freigabe, höchstens 20 offene je Person. Bestätigt, lehnt ab oder storniert jemand anderes eine
Buchung, bekommt die buchende Person eine E-Mail über den Postausgang (Art `buchung`).
