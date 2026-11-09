---
key: page.scores
titel: Noten
modul: scores
rechte: [scores.view]
routen: [/noten]
stichworte: [Noten, Notenarchiv, Notenbestand, Chor, Arrangement, Stimme]
---

# Noten

Das Notenarchiv verwaltet Stücke, Arrangements, Stimmen und digitale Notenunterlagen. Ohne das Modul Musik, etwa bei einem Chor ohne Auftrittsplanung, steht es als eigener Menüpunkt **Noten** in der Seitenleiste; mit Musik findest du es unter Musik › Notenbestand.

Pflegen darf, wer das Recht „Notenbestand pflegen“ hat. Rollen mit Musikrechten können den Bestand lesen, damit Programme und Proben Arrangements auswählen können.

Über **Notenkatalog importieren** übernimmst du einen vorhandenen Katalog aus einer CSV-Datei. Digitale Noten lädst du in der Dokumentenablage hoch und ordnest sie unter **Notenunterlagen** einem Arrangement zu.

## Notenmappen für die App

Unter **Notenmappen** legst du feste Mappen an, etwa ein **Marschbuch** oder das **Repertoire**. Jede Mappe enthält Arrangements in einer festen Reihenfolge, auf Wunsch mit einer Nummer („Nr. 27“). Mit ↑ und ↓ änderst du die Reihenfolge.

Musiker finden die Mappen in der App „HUBIplan“ unter **Noten** und können dort nach Titel, Komponist oder Nummer suchen. Jeder sieht nur die Noten seiner eigenen Stimme und nur Dateien, die die Dokumentenablage für Mitglieder freigibt. Ohne Auswahl unter **Sichtbar für** sehen alle Musiker die Mappe, sonst nur Mitglieder der gewählten Untereinheiten.

Hat ein Stück für eine Stimme mehrere Dateien (zum Beispiel Seite 1 und 2 als Bild), bestimmt unter **Notenunterlagen** das Feld **Reihenfolge bei mehreren Dateien**, in welcher Folge sie angezeigt werden.

## Notendateien: PDF, Bilder, MusicXML und MIDI

Noten lädst du in der Dokumentenablage hoch. Neben PDF, JPEG und PNG versteht HUBIplan MusicXML (`.musicxml`, `.mxl`, `.xml`), dazu die offenen Formate MEI und ABC. MuseScore, Capella, Sibelius und Finale exportieren MusicXML (meist unter „Exportieren“ oder „Speichern unter“).

- Aus einer MusicXML-Partitur bekommt jeder Musiker nur seine Stimme. Die Stimme sucht HUBIplan nach Instrument und Register der Zuordnung. Passt das nicht eindeutig, trägst du unter **Notenunterlagen** bei **Stimme in der MusicXML-Partitur (leer: nach Instrument)** den Namen der Stimme ein, wie er in der Datei steht.
- Im Browser öffnen sich MusicXML-Noten als PDF. In der App werden sie passend zum Bildschirm gesetzt und lassen sich transponieren.
- MIDI-Dateien (`.mid`) ordnest du als Hörbeispiel zu. Zu MusicXML-Noten erzeugt HUBIplan das Hörbeispiel selbst.

## Leitung in der App

Dirigent, Stabführer oder Tambourmajor können in der App allen Musikern das nächste Stück vorgeben; die Geräte springen dann in die eigene Stimme. Das darf, wer Musik bearbeiten darf, und wer als **Leitung in der App** eingetragen ist: bei einer Notenmappe (unter **Stücke zeigen**), bei einem Auftritt unter **Besetzung planen** oder bei einer Probe.
