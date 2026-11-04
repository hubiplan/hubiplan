# Konzept Materialverwaltung

Stand: 4. November 2026. Fachkonzept; Hinweise zur Implementierung stehen in
[Materialverwaltung](material.md).

Die Materialverwaltung beantwortet für jedes inventarisierte Teil drei Fragen: Was ist es,
wo befindet es sich und wofür wird es gebraucht? Sie verbindet einen gemeinsamen
Materialbestand mit vorhandenen Mitgliedern, Terminen, Aufgaben und Dokumenten.
Der aktuelle Standort und die geplante Verwendung werden unabhängig voneinander gepflegt.

## Umfang

Jedes einzeln inventarisierte Teil erhält einen eigenen Datensatz und eine eindeutige
Inventarnummer. Zwei gleichartige Beamer sind damit zwei Teile mit jeweils eigenem Standort
und eigenen Zuordnungen. Ein zusammenbleibendes Set, etwa ein Werkzeugkoffer, kann als ein
Teil erfasst werden; sein Inhalt steht in der Beschreibung. Sobald Bestandteile unabhängig
eingesetzt oder gelagert werden, erhalten sie eigene Einträge.

Material gehört einer verwaltenden Einheit, etwa einem Verein oder einer Untereinheit.
Die Auswahl eines Mitglieds als Standort ändert diese Zugehörigkeit nicht.
Die Funktion wird als optionales Modul „Material“ in die bestehende Modulverwaltung aufgenommen.

## Angaben je Teil

| Angabe | Regel | Beispiel |
| --- | --- | --- |
| Inventarnummer | Automatisch vergeben, innerhalb des Datenbereichs eindeutig und unveränderlich | MAT-000123 |
| Bezeichnung | Pflichtfeld, kurzer Name | Beamer Epson |
| Kurzbeschreibung | Pflichtfeld, zur Erkennung und Abgrenzung | Schwarzer Beamer im Koffer mit Fernbedienung und HDMI-Kabel |
| Foto oder Bild | Optional, mit Vorschau, Ersetzen und Entfernen | Foto des Beamers mit Zubehör |
| Standort | Pflichtfeld: Mitglied oder frei eingegebene Adresse | Bei Erika Beispiel |
| Standortzusatz | Optional | Garage, Regal links |
| Verwendungszweck | Freitext und/oder mindestens eine Terminzuordnung | Präsentationen und Mitgliederversammlungen |
| Termine und Terminreihen | Keine, eine oder mehrere Zuordnungen | Mitgliederversammlung; monatlicher Vorstandsabend |
| Aufgaben | Keine, eine oder mehrere Zuordnungen | Beamer abholen; Funktion prüfen |
| Dokumente | Keine, eine oder mehrere Verknüpfungen aus der Ablage | Anleitung; Rechnung; Prüfprotokoll |
| Zustand | Einsatzbereit, eingeschränkt nutzbar, defekt oder ausgesondert; Vorgabe einsatzbereit | Eingeschränkt nutzbar |
| Zustandshinweis | Optional, bei eingeschränkt nutzbar oder defekt empfohlen | HDMI-Eingang hat Wackelkontakt |

Freitext und Terminzuordnungen dürfen gleichzeitig genutzt werden. Beim Anlegen muss
mindestens eine dieser beiden Formen den Verwendungszweck beschreiben. Aufgaben und
Dokumente ergänzen diese Information. Für allgemein vorgehaltenes Material genügt etwa
„Reserve für Vereinsveranstaltungen“.

## Standort

Das Formular bietet die Auswahl **„Bei einem Mitglied“** oder **„An einer Adresse“**.
Es ist immer genau eine Variante aktiv; beim Wechsel wird die bisher aktive Angabe ersetzt.

- **Mitglied:** Suche und Auswahl eines berechtigt sichtbaren Mitglieds. Gespeichert wird
  die Referenz auf dessen Mitgliedschaft im betreffenden Datenbereich, keine Namens- oder
  Adresskopie. Angezeigt wird „Bei [Name]“ mit optionalem Standortzusatz. Eine Privatadresse
  wird nur bei bestehender Berechtigung auf diese Mitgliederdaten angezeigt.
- **Adresse:** Freie Eingabe ohne Mitgliedsbezug. Felder sind Lagerortbezeichnung, Straße
  und Hausnummer, Postleitzahl, Ort und Land sowie ein optionaler Zusatz. Erforderlich ist
  eine nutzbare Anschrift; eine externe Adressprüfung ist nicht nötig.

„Standort ändern“ erfasst den tatsächlichen neuen Aufbewahrungsort. Eine Terminzuordnung,
ein vergangener Termin oder eine erledigte Transportaufgabe verschiebt das Teil nicht
automatisch. Die Übersicht zeigt immer den zuletzt bestätigten Standort.

Bei Austritt bleibt ein zugeordnetes Mitglied zunächst als bisheriger Standort erkennbar;
der Eintrag erhält den Hinweis „Standort prüfen“. Bei endgültiger Löschung der Mitgliedsdaten
wird die Referenz entfernt und der Standort als „Zu klären“ markiert. Das Teil bleibt erhalten.
Dieser Ausnahmezustand entsteht nur durch den Wegfall einer Referenz; bei Neuanlage und
bewusster Standortänderung ist weiterhin ein vollständiger Standort erforderlich.

## Verwendung für Termine und Terminreihen

Ein Teil kann mehreren Einzelterminen und mehreren Terminreihen zugeordnet werden.
Ein Termin kann seinerseits beliebig viele Teile benötigen. Jede Zuordnung erlaubt einen
kurzen Zusatz, beispielsweise „Für die Präsentation im Saal“.

Bei einer Terminreihe wählt die Person ausdrücklich zwischen **„Ganze Reihe“** und
**„Nur dieser Termin“**:

- Eine Reihenzuordnung gilt für alle nicht abgesagten Vorkommen innerhalb ihres
  Gültigkeitszeitraums. Vorgabe ist „ab heute“, optional mit Enddatum; eine rückwirkende
  Zuordnung ist ausdrücklich auswählbar.
- Eine Einzelzuordnung innerhalb einer Reihe gilt nur für das ausgewählte Vorkommen.
  Sie bleibt erhalten, wenn dieses Vorkommen verschoben wird.
- Ein Teil aus einer Reihenzuordnung lässt sich für ein einzelnes Vorkommen ausschließen.
  Die übrige Reihe bleibt unverändert.
- Treffen Reihen- und Einzelzuordnung zusammen, erscheint das Teil einmal, mit erkennbarer
  Herkunft der Zuordnung. Für ein Vorkommen können Einzelausschluss und Einzelzuordnung
  nicht gleichzeitig bestehen.
- Eine Absage beendet den Bedarf für das betroffene Vorkommen, erhält aber die Zuordnung
  als nachvollziehbare Information. Bei Rücknahme der Absage gilt sie wieder.

Änderungen an Serienbeginn oder Wiederholungsregel dürfen Einzelzuordnungen und Ausnahmen
nicht stillschweigend einem anderen Vorkommen zuweisen. Vor dem Speichern zeigt die
Oberfläche betroffene Zuordnungen zur Prüfung. Nicht mehr zuordenbare Einträge erhalten
„Terminbezug prüfen“ und gelten bis zur Klärung nicht als aktueller Bedarf.

Vergangene Einsätze bleiben abrufbar. Standardmäßig zeigt die Materialdetailseite die
kommenden Verwendungen. Wird die letzte Terminzuordnung entfernt und fehlt ein Freitext,
wird ein Verwendungszweck nachgefordert. Bei extern verursachtem Wegfall eines Termins
bleibt das Material erhalten und erhält stattdessen „Verwendung prüfen“.

Die erste Version erfasst geplanten Bedarf. Sie verspricht keine Verfügbarkeit und führt
keine verbindliche Reservierung durch. Eine spätere Reservierungsfunktion kann Zeiträume
für Abholung, Einsatz und Rückgabe sowie Konfliktwarnungen ergänzen.

## Aufgaben

Teile und Aufgaben werden beidseitig verknüpft: Auf der Materialdetailseite stehen die
zugehörigen Aufgaben, in einer Aufgabe die benötigten Teile. Eine Aufgabe kann mehrere
Teile betreffen, beispielsweise „Zelt, Tische und Kabel zum Festplatz bringen“.

„Aufgabe anlegen“ auf der Materialseite öffnet das bestehende Aufgabenformular und
übernimmt den Materialbezug. Zuständigkeit, Frist, Freigaben, Erinnerungen und Erledigung
bleiben Funktionen der Aufgabenverwaltung. Beim Zuordnen einer bestehenden Aufgabe wird
keine neue Aufgabe erzeugt.

Das Verknüpfen setzt Materialbearbeitung und Bearbeitungsrecht an der konkreten Aufgabe
voraus. Die Anzeige verlangt Leserechte auf beide Objekte. Private Aufgaben bleiben privat:
Unberechtigte sehen weder Titel noch Kennung, Anzahl oder einen Hinweis auf ihre Existenz.
Das gilt auch für Änderungsprotokolle und Exporte.

Eine erledigte Aufgabe bleibt verknüpft und wird als erledigt angezeigt. Sie verändert
weder Standort noch Zustand automatisch. Die Terminzuordnung einer Aufgabe erzeugt keinen
zusätzlichen Materialbedarf im Termin. In der ersten Version beziehen sich Materiallinks
auf konkrete Aufgaben; eine Übernahme in künftige Ausgaben einer Aufgabenserie ist eine
gesonderte Erweiterung.

## Dokumente

„Dokument zuordnen“ öffnet eine Suche in der bereits zugänglichen Dokumentenablage.
Ein Teil kann mehrere Dokumente verwenden, ein Dokument mehrere Teile. Optional erhält
die Verbindung eine Erläuterung wie „Bedienungsanleitung“ oder „Kaufnachweis“.

Es wird ein Verweis auf das bestehende Dokument gespeichert. Die Datei wird nicht kopiert;
beim Öffnen gilt die aktuelle Fassung. Ältere Fassungen bleiben über die vorhandene
Dokumentenansicht erreichbar. Neue Dateien werden zunächst in der Dokumentenablage erfasst.

Materialzugriff erweitert keine Dokumentrechte. Titel, Kennung, Vorschau, Download und
Rückverweise werden jeweils anhand der aktuellen Rechte geprüft. Nicht sichtbare Dokumente
erscheinen auch nicht in Zählern oder Suchtreffern. Eine Rechteänderung wirkt sofort.
Entfernen einer Verknüpfung löscht kein Dokument. Dokumente im Papierkorb werden nicht als
aktive Anhänge angeboten; Wiederherstellen stellt den Bezug wieder bereit. Endgültiges
Löschen entfernt den Verweis, erhält aber das Material.

## Materialfoto

Ein Teil kann ein eigenes Foto erhalten. JPEG, PNG und WebP werden bis 10 MB angenommen,
geprüft, von Bildmetadaten bereinigt und auf höchstens 1600 Pixel Kantenlänge verkleinert.
Die Vorschau erscheint in Liste und Detailansicht. Ersetzen und Entfernen sind möglich;
das bisherige Bild bleibt für Rückgängig vorübergehend im privaten Speicher. Abrufe prüfen
die aktuellen Materialrechte. Materialbilder zählen zum gemeinsamen Speicherbudget.

## Bedienung

Der neue Navigationspunkt **„Material“** öffnet eine durchsuchbare Liste. Sie zeigt
Inventarnummer, Bezeichnung, Standort, Zustand und nächste sichtbare Verwendung.
Filter grenzen nach Einheit, Mitglied beziehungsweise Adressstandort, Zustand, Termin,
Terminreihe und offenen Prüfhinweisen ein. Archivierte Teile sind standardmäßig ausgeblendet.
Auf dem Smartphone erscheinen dieselben Informationen als kompakte Karten.

Die Detailseite gliedert sich in **Angaben**, **Standort**, **Verwendung**, **Aufgaben**,
**Dokumente** und **Verlauf**. Die Anlage beginnt mit den Pflichtangaben; Aufgaben und
Dokumente können anschließend ergänzt werden. Mehrfachauswahl mit Suchfeld erleichtert
die Zuordnung von Terminen, Aufgaben und Dokumenten.

Zusätzliche Einstiege verbinden die bestehenden Bereiche:

| Bestehende Ansicht | Ergänzung |
| --- | --- |
| Mitglied | „Material bei diesem Mitglied“ mit berechtigt sichtbaren Teilen |
| Einzeltermin oder Vorkommen | „Benötigtes Material“ einschließlich wirksamer Reihenzuordnungen |
| Terminreihe | „Material für diese Reihe“ mit Gültigkeit und Ausnahmen |
| Aufgabe | „Zugeordnetes Material“ |
| Dokument | „Verwendet bei Material“ mit berechtigt sichtbaren Rückverweisen |

Beispiel: Der Beamer MAT-000123 liegt bei Erika Beispiel und dient allgemein für
Präsentationen. Er ist der Mitgliederversammlung und der Reihe „Vorstandsabend“ zugeordnet.
Die Aufgabe „Beamer für die Versammlung abholen“ und die vorhandene Bedienungsanleitung
sind verknüpft. Nach der Abholung bestätigt ein Bearbeiter den Standort „Vereinsheim,
Saal“. Die allgemeinen Verwendungsangaben bleiben bestehen.

## Rechte und Datenbereiche

Der neue Bereich folgt dem bestehenden Modell mit **kein Zugriff**, **lesen**
(`material.view`) und **bearbeiten** (`material.edit`). Bearbeiten schließt Lesen ein.
Lesen erlaubt die berechtigte Materialübersicht und ihre Verknüpfungen; Bearbeiten erlaubt
Anlage, Änderungen, Zuordnungen, Archivierung und Papierkorb. Export folgt zusätzlich den
vorhandenen Exportberechtigungen. Rollen erhalten keine neuen Rechte allein dadurch, dass
sie Termine oder Dokumente verwalten.

Materialrechte gelten im jeweiligen Einheitenkontext. Eine übergeordnete Einheit erhält
keinen automatischen Einblick in das Material ihrer Untereinheiten. Die Standortzuordnung
an ein Mitglied gewährt diesem ebenfalls keinen Zugang. Freie Standortadressen sind für
Materialleser sichtbar; darauf weist das Eingabeformular hin. Der Zugriff auf zusätzliche
Mitgliederdaten folgt weiterhin den Mitgliederdatenrechten.

Zum Verknüpfen eines Termins oder Dokuments genügen Materialbearbeitung und Leserecht am
Ziel; das Ziel selbst wird nicht verändert. Bei Aufgaben gilt die zusätzliche oben genannte
Bearbeitungsprüfung. Jede Auswahl und jeder Schreibzugriff prüfen Datenbereich und aktuelle
Objektrechte. Sichtbare Ziele innerhalb derselben Organisation, einschließlich berechtigt
sichtbarer Untereinheitsziele, können verwendet werden. Verknüpfungen über Organisations-
oder Instanzgrenzen sind eine spätere Erweiterung.

Öffentliche Termine und öffentliche Dokumentlinks veröffentlichen kein Material und keine
Standortdaten. Material erscheint in der ersten Version weder auf der Vereinswebseite noch
in öffentlichen Kalenderexporten.

## Verlauf und Lebenszyklus

Änderungen an Beschreibung, Standort, Zustand und Verwendungsangaben werden mit Zeitpunkt
und bearbeitender Person protokolliert. Die bestehende Infrastruktur für Änderungsprotokoll
und Rückgängig wird genutzt. Verknüpfungen dürfen darüber keine geschützten Zielinhalte oder
dauerhaften Kopien gelöschter Mitgliederdaten offenlegen. Rückgängig prüft erneut die heutigen
Rechte und die Existenz der Ziele.

Ausgesondertes Material bleibt archiviert auffindbar und wird für neue Zuordnungen nicht
mehr angeboten. Beim Aussondern zeigt die Oberfläche noch offene Aufgaben und künftige
Terminbezüge zur Klärung an; sie werden nicht automatisch erledigt oder gelöscht.
Versehentlich erfasste Einträge können in den Papierkorb verschoben und innerhalb von
30 Tagen wiederhergestellt werden. Verknüpfte Termine, Aufgaben und Dokumente bleiben bei
einer Materiallöschung erhalten.

## Technische Einordnung

Die Umsetzung ergänzt eine Django-App `materials` und die entsprechenden React-Ansichten.
Die folgenden Namen beschreiben das vorgeschlagene Datenmodell:

| Modell | Aufgabe |
| --- | --- |
| `MaterialItem` | Stammdaten, Organisation, optionale Untereinheit, Inventarnummer, Standortvariante, Mitgliedsreferenz oder Adresse, Zweck, Zustand, Archiv- und Löschstatus |
| `MaterialEventLink` | Teil, vorhandenes `Event`, Bezug auf Einzeltermin, ganze Reihe oder einzelnes Vorkommen, Gültigkeit und Verwendungshinweis |
| `MaterialEventExclusion` | Ausschluss eines Vorkommens aus einer Reihenzuordnung |
| `MaterialTodoLink` | Eindeutige Verbindung von Teil und vorhandener `Todo` |
| `MaterialDocumentLink` | Eindeutige Verbindung von Teil und vorhandenem `Document`, optionale Erläuterung |

Im bestehenden Kalender sind Reihen `Event`-Datensätze mit Wiederholungsregel;
Vorkommen werden berechnet. Einzelbezüge verwenden deshalb wie `EventException` die
Kombination aus Termin-ID und `original_start`, nicht den nach einer Verschiebung wirksamen
Beginn. Gültigkeitsgrenzen und Tagesbezüge verwenden die Kalenderzeitzone. Eine neue,
parallel gepflegte Tabelle aller Serienvorkommen ist nicht erforderlich.

Fremdschlüssel und eindeutige Constraints verhindern doppelte Verknüpfungen. Die
Standortvarianten werden gegenseitig ausgeschlossen; der systemseitige Klärungszustand
wird ausdrücklich modelliert. Datenbankregeln und serverseitige Prüfungen sichern
Einheitengrenzen und gültige Beziehungen. RLS wird für Material und Zuordnungstabellen
ergänzt. Gleichzeitige Änderungen werden durch Versionsprüfung vor unbeabsichtigtem
Überschreiben geschützt. Personenbezogene Freitexte und Adressen werden in das bestehende
Verschlüsselungs- und Löschkonzept aufgenommen.

Inventarlisten und vollständiger Datenexport enthalten nur berechtigte Inhalte. Beim Import
werden Beziehungen auf tatsächlich importierte oder berechtigt aufgelöste Ziele umgesetzt;
fremde IDs werden nicht ungeprüft übernommen. Fehlende Standort- und Terminziele erzeugen
die beschriebenen Prüfhinweise. Die Moduldeaktivierung blendet die Funktion aus und sperrt
ihre Schnittstellen, löscht aber keine Bestandsdaten.

## Lieferumfang und Abnahme

Die erste Version umfasst Inventar, beide Standortvarianten, freie Verwendungszwecke,
Mehrfachzuordnungen zu Terminen und Reihen einschließlich einzelner Vorkommen und
Ausnahmen, Aufgaben- und Dokumentverweise, Rückverweise, Rechte, Verlauf, Archiv,
Papierkorb sowie die Einbindung in Export und Import. Die Weboberfläche ist mobil nutzbar.
Eine native Android-Erweiterung kann darauf aufbauen.

Für die Abnahme sind insbesondere diese Fälle zu prüfen:

1. Zwei gleichartige Teile lassen sich getrennt inventarisieren; die Pflichtangaben werden geprüft.
2. Ein Wechsel von Mitglied zu Adresse lässt genau einen aktuellen Standort zurück.
3. Freitext, mehrere Termine und mehrere Reihen lassen sich gleichzeitig hinterlegen.
4. Verschieben, Absagen und Ausschließen einzelner Serienvorkommen liefern den richtigen Bedarf.
5. Eine Serienregeländerung verliert oder verschiebt keine Einzelzuordnung unbemerkt.
6. Mehrere Teile können dieselbe Aufgabe und dasselbe Dokument verwenden, ohne Dubletten.
7. Private Aufgaben und gesperrte Dokumente bleiben auch in Zählern, Protokollen und Exporten verborgen.
8. Austritt, endgültige Mitgliederlöschung und gelöschte Termine hinterlassen verständliche Prüfhinweise.
9. Aufgabe erledigen und Terminablauf verändern den Standort nicht automatisch.
10. Papierkorb, Wiederherstellung, Rechteentzug und Einheitsgrenzen gelten auch für direkte API-Aufrufe.

Spätere Erweiterungen sind verbindliche Reservierungen mit Konfliktprüfung, Ausleihe und
Rückgabe, Mengenbestände für Verbrauchsmaterial, QR-Etiketten, Wartungsfristen sowie
Kaufpreise und Abschreibungen. Sie sind für die beschriebene Inventarisierung nicht erforderlich.

## Anschluss an die vorhandene Anwendung

- [Aufgaben und ihre Freigaben](aufgaben.md)
- [Dokumentenablage](dokumente.md)
- [Berechtigungsmodell](berechtigungen.md)
- [Bestehendes Terminmodell](../backend/events/models.py)
- [Bestehendes Aufgabenmodell](../backend/todos/models.py)
- [Bestehendes Dokumentenmodell](../backend/documents/models.py)
