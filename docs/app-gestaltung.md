# Gestaltung der Apps („Frisch mobil“)

Die Apps für Android (`hubiplan-android`) und iOS (`hubiplan-ios`) teilen sich Aufbau, Werte und
Symbole. Was sie mit HUBIplan sprechen, steht in [app.md](app.md).

## Aufbau

- **Reiter:** Start, Termine, Neues, Ich und ein fünfter je Rolle (Verwaltung, sonst Noten, sonst
  Aufgaben; wählbar in den Einstellungen der App). Was nicht in der Leiste steht, ist auf „Start“
  unter „Schnell erreichbar“.
- **Start:** nächster Termin mit Zusage und Absage, „Wartet auf dich“ und die Kacheln der
  Startseite. Die Zeilen kommen von `GET /api/portal/<Zugang>/start/`; ältere Server antworten mit
  404, dann rechnet die App aus Terminen und Mitteilungen selbst.
- **Termine:** nach Monaten, mit Schalter „ohne Rückmeldung“.
- **Neues:** Mitteilungen, Pinnwand und Umfragen in einem Reiter.
- **Ich:** Ausweis und Mein Bereich in vier Gruppen (Geld, Mitmachen, Verein, Meine Daten).
- **Verwaltung:** Arbeitsplatz mit „Ausweis prüfen“, „Neu“, „Zu erledigen“ und den Bereichen in
  den Gruppen des Hauptmenüs im Browser (Planen, Verein, Vereinsleben, Verwaltung), mit Suche.
- **Formulare:** angefangene Eingaben sind geschützt; Zurück und Reiterwechsel fragen nach.
  Datum und Uhrzeit kommen aus der Auswahl des Systems.
- **Darstellung:** wie das Gerät, hell oder dunkel.

## Gemeinsame Dateien

Beide Apps enthalten dieselben zwei Dateien; ein Test in jeder App hält ihre Prüfsumme fest und
vergleicht die Werte im Code damit. Wer etwas ändert, ändert es in beiden Apps im selben Zug.

| Datei | Inhalt | Android | iOS |
|---|---|---|---|
| `werte.json` | Abstände, Radien, Farben (hell und dunkel), Schriftstufen | `app/src/main/assets/design/` | `Sources/HubiplanKern/Gestaltung/` |
| `symbole.json` | Strichsymbole im Raster 24, Strich 1,75, runde Enden | `app/src/main/assets/design/` | `Sources/HubiplanKern/Gestaltung/` |

`symbole.json` entsteht aus `scripts/app-symbole.py` (braucht `fonttools`):

```
python3 scripts/app-symbole.py > symbole.json
```

Jedes Symbol besteht aus Teilpfaden mit nur vier Befehlen (M, L, C, Z) in absoluten Koordinaten,
damit beide Apps denselben kleinen Leser nutzen. Ein neues Symbol kommt als einfache SVG-Form in
das Skript, die erzeugte Datei unverändert in beide Apps, dazu der Name in die Aufzählung
(`Strich` in Android, `Strichsymbol` in iOS).

Die Schrift ist Inter (SIL Open Font License 1.1) und liegt beiden Apps bei; es wird nichts von
fremden Servern geladen.

## Bausteine

Seiten setzen sich in beiden Apps aus denselben Bausteinen zusammen: Karte, Abschnittstitel,
Zeile, Zähler, Symbolkopf, Leerzustand und Platzhalter. Einzelheiten stehen in den Apps
(`docs/gestaltung.md` in `hubiplan-android`, README in `hubiplan-ios`).
