# Designpakete

Ein Design der Vereinswebseite lässt sich als Paket (ZIP) speichern und als eigenes Design wieder
einspielen. So wird zum Beispiel das alte „Klassisch“ zu einem Design nur für einen Verein, während
das Repository ein neues Klassisch bekommt. Konzept: `konzepte/designs-import-export.md` im
Projektordner (Ralf 2026-11-02).

## Ablauf

1. **Exportieren** unter Webseite › Gestaltung › „Design weitergeben“ › „Als Paket speichern“.
   Standarddesigns liefert die Webseite selbst (`<webseite>/design-paket/<schlüssel>.zip`), weil nur
   sie deren CSS und Vorlagen kennt; eingespielte Designs liefert HUBIplan
   (`website/design-packages/<schlüssel>/export/`).
2. **Einspielen** (nur Plattformverwalter, die die Webseite verwalten): „Design aus Paket laden“,
   neues Kürzel und Namen eintragen, „Prüfen“, dann „Einspielen“. Das Design ist danach für diese
   Webseite freigegeben. Stammt das Paket aus einem Standarddesign (`quelle`), übernimmt HUBIplan
   dessen Farbzuordnung dieser Webseite.
3. **Wählen** wie jedes andere Design. Andere Webseiten sehen es erst nach einer Freigabe unter
   „Eingespielte Designs“.

Reihenfolge beim Ablösen eines Standarddesigns: erst exportieren, einspielen und umstellen, dann
das geänderte Standarddesign ausrollen. So zeigt die Webseite nie kurz das neue Design.

## Inhalt eines Pakets

| Datei | Pflicht | Inhalt |
| --- | --- | --- |
| `design.json` | ja | `format` = `hubiplan-designpaket`, `version` = 1, `key`, `label`/`hint` (de, en), `roles` (Farbrollen wie in `website/designs.py`), `skizze_wie`, `quelle`, `exportiert` |
| `design.css` | ja | Gestaltung auf `seite.css` aufgesetzt, höchstens 64 KB |
| `vorlagen/kopf.html`, `vorlagen/fuss.html`, `vorlagen/start.html` | nein | ersetzen Kopf, Fuß bzw. Startseite der Webseite (Startseite meist `{% extends "seite/start.html" %}` mit Block `bausteine`) |

Kein Wappen, keine Texte, keine Bilder, keine Schriften. Unterseiten bleiben für alle Designs gleich.

## Prüfung

HUBIplan (`website/design_packages.py`) prüft beim Einspielen, die Webseite
(`seite/designpaket.py`) beim Abholen noch einmal mit denselben Regeln. Abgelehnt wird:

- im CSS `@import`, `@font-face`, `url(…)`, `image-set(…)`, `expression(…)`, `javascript:`,
  `behavior`/`-moz-binding`, Rückstriche und spitze Klammern;
- in Vorlagen Skripte, eingebettete Fremdinhalte (`iframe`, `object`, `style`, `link` …),
  `on…=`-, `style=`- und `srcdoc=`-Attribute, `javascript:`-Adressen, Inhalte von fremden Adressen
  (`src=` usw.; Links mit `href` nach außen sind erlaubt);
- Vorlagen-Befehle und Filter außerhalb einer festen Liste (kein `safe`, kein `autoescape`,
  `load` nur `seite`, `static`, `i18n`; `extends` nur `seite/basis.html` oder `seite/start.html`;
  `include` nur feste Vorlagen unter `seite/` oder `vorlage`);
- andere Dateien, ZIP über 2 MB oder entpackt über 5 MB, unbekannte Version.

Besteht ein Paket die Prüfung der Webseite nicht oder fehlt es, zeigt die Webseite Klassisch.
Die Sicherheitsrichtlinie (CSP) der Webseite bleibt unverändert.

## Speicherort

Pakete liegen in der Datenbank (`website.DesignPackage`, Freigabe je Webseite) und damit in der
normalen Sicherung. Die ZIP-Datei dient als zusätzliche Sicherung und zum Übertragen zwischen
Installationen (Testserver ↔ Echtbetrieb). Die Datenübernahme einer Einheit nimmt Pakete nicht mit.
