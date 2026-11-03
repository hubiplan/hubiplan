# Designpakete

Ein Paket enthält `design.json` und `design.css` (maximal 64 KB CSS; ZIP maximal 2 MB,
entpackt maximal 5 MB). Format `hubiplan-designpaket`, Version 1 bleibt lesbar.
`quelle` bzw. `skizze_wie` wählt eines der gepflegten Standardlayouts
(classic, festive, sidebar, stage, newspaper). Unbekannte Layouts ergeben Klassisch.
Farbrollen, Bezeichnungen und CSS können angepasst werden. Das Markup kommt immer
von den geprüften Komponenten der installierten Webseite.

Freie HTML-/Django-Vorlagen sind vollständig ausgeschlossen, auch bei scheinbar
harmlosen Vorlagen, Bedingungen, Kommentaren oder Includes. Die frühere DTL-Filterliste
ist keine Sicherheitsgrenze mehr. CSS darf weiterhin keine externen Ressourcen laden
(`url`, `@import`, `@font-face` usw.); die CSP bleibt aktiv.

Standarddesigns exportiert die Webseite unter `/design-paket/<layout>.zip` ohne
Vorlagendateien. Plattformverwalter importieren unter Webseite › Gestaltung mit eigenem
Kürzel, prüfen und geben je Webseite frei. `quelle` übernimmt auch die Farbzuordnung.
Der gewählte Layoutschlüssel ist Teil der Prüfsumme. Ein freigegebenes Datenpaket kann
wieder exportiert und importiert werden.

**Funktionsänderung:** Freie Vorlagen bestehender Pakete bleiben für die Verwaltung in
der Datenbank erhalten, sind jedoch öffentlich quarantänisiert. Die Webseite fällt
kontrolliert auf Klassisch zurück. Das Paket durch ein Paket ohne `vorlagen/` ersetzen,
Layoutschlüssel wählen und Darstellung prüfen. Veraltete Vorlagen werden nicht still
bereinigt oder ausgeführt. HUBIplan und Webseite gemeinsam aktualisieren. Ein Rückweg
auf die frühere freie DTL-Ausführung würde die Sicherheitsgrenze wieder aufheben.
Die Layoutkomponenten folgen künftig den gepflegten Standarddesigns; das Paket friert
keine alte HTML-Anordnung dauerhaft ein.

## English

Packages contain only `design.json` and `design.css`. `quelle`/`skizze_wie` selects a
maintained built-in layout; labels, colour roles and bounded CSS remain customizable.
No imported HTML or Django template source is compiled, including conditional or
apparently harmless templates. Built-in export/import and per-site release continue
to work. The layout identifier contributes to the content hash.

Legacy free-template packages remain stored for administrators but are quarantined
from public APIs. The website falls back to Classic without a server error. Replace
such packages with CSS/layout-only packages and review the result. Update both
applications. Layout markup follows maintained components rather than preserving
arbitrary historic HTML. Downgrading to free DTL would remove this security boundary.
