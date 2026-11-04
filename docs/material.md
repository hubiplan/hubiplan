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
