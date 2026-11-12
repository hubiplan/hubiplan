# Module

Einzige Quelle: `backend/access/modules.py` (Modulverzeichnis). Die Oberfläche liest es über
`GET /api/modules/`; der Rechtekatalog (`access/catalog.py`) leitet daraus ab, welche Module
abschaltbar sind und welche eine neue Einheit bekommt.

- **Freigegeben** (Plattform, Obergrenze) steht in `Organization.released_modules`, gepflegt unter
  Plattform › Einheiten (`apply_release`: neu Freigegebenes wird eingeschaltet, Entzogenes
  aus). Leer heißt für eine Fassung: wie eingeschaltet (`released_of`).
- Die Einheit schaltet unter Einstellungen › Module (`/api/orgs/<id>/modules/`, Recht
  `settings.*`, `apply_enabled`) innerhalb der Freigabe ein und aus; `dry_run` zeigt vorher,
  was mit ein- oder ausgeschaltet wird.
- **Zusatzfunktionen** (`EXTRAS`: Schalter eines Moduls ohne eigene Seiten, etwa Zählprotokoll,
  DATEV, Rücklagen, SEPA, Wallet) stehen in derselben Antwort unter `extras` und werden mit
  `PATCH {extras: {id: bool}}` geschaltet, nur bei eingeschaltetem Modul. Es sind dieselben
  Felder wie in den Einrichtungsseiten der Module.
- **Eingeschaltet** steht in `Organization.enabled_modules`. Abfragen im Code nutzen die
  Kennung aus dem Verzeichnis, für Untereinheiten `module_on(org, id)` (sie erben die Module
  ihres Vereins; Kasse, Rechnungen und Webseite führen sie selbst).
- **Untereinheiten** mit eigenem Arbeitsbereich: Der Verein blendet Module, die dort auf den
  eigenen aufbauen (Steuern, Zuwendungen, Social Media), je Einheit aus
  (`Organization.unit_hidden_modules`, leer = alle). `module_on` beachtet das auch für die
  Einheiten darunter (`unit_hidden`).
- **Weitergabe:** Mit `modules_pass_down` (Schalter der Plattform) gibt ein Dachverband seinen
  Vereinen unter Untereinheiten selbst Module frei (`released_modules` am Vereins-Endpunkt
  `/api/orgs/<id>/clubs/<club>/`, `apply_release`).
- **Vorlagen** (`TEMPLATES`, `GET /api/modules/templates/`): schlagen beim Anlegen unter
  Plattform › Einheiten Module und die Bezeichnung der Untereinheiten vor; gespeichert wird
  nur das Ergebnis.
- **Rechte** eines abgeschalteten Moduls wirken nicht (`Area.module`), bleiben aber an der
  Rolle gespeichert.
- **Pfade ohne eigenes Rollenrecht** (Mitgliederbereich, Ehrungen, Würden, Social Media) bindet
  `access/module_gate.py` (`gate`, `gate_names`, `needs_module`) an das Modul; sonst 404.
- **Mitgliederbereich:** Modul `portal` und Schalter `member_portal_enabled` hält
  `Organization.save` gleich (der Schalter bleibt eine Fassung lang für ältere Stände).
- **Voraussetzungen** (`requires`, `requires_any`) nimmt das Backend beim Speichern mit
  (`with_requirements`).
- **Chronik:** eigener Menüpunkt „Chronik“ (`/chronik`, Recht `chronicle.*`). Gespeichert wird
  wie bisher als Textseite „geschichte“ der Webseite (Entwurf, Fassungen, Bilder, öffentliche
  Schnittstelle unverändert); ohne Webseite legt `GET /api/orgs/<id>/chronicle/` eine
  ausgeschaltete Webseite als Ablage an. Inhalte-Ansichten mit `chronicle_ok` lassen
  Chronik-Rechte nur an diese Seite und die Bilder.
- **Steuern & Gemeinnützigkeit:** Die Schalter „steuerliche Bereiche“ und „Rücklagen führen“
  bleiben gespeichert, wirken aber nur mit dem Modul (`Organization.tax_areas_on`,
  `reserves_on`). **Zuwendungsbestätigungen:** `finance.donations.available` fragt das Modul ab.
  Beide gelten für eine Untereinheit mit eigener Kasse, wenn ihr Verein sie eingeschaltet hat.
- **Notenarchiv:** Notenbestand und Katalogimport (`music/scores.py`, Recht `scores.*`). Lesen
  dürfen auch Musik-Rollen (Programme, Proben). Ohne Musik eigener Menüpunkt „Noten“ (`/noten`).
- **Schießsport:** Scheibenkatalog, Treffer, Fotoauswertung und Vogelschießen
  (`competitions/urls.py`, `SHOOTING`); neue Scheiben und Vogelschießen nur mit Modul,
  gespeicherte Scheiben bleiben.
- `tests/test_modulnamen.py` prüft, dass jede im Code und in der Hilfe (`modul:`) abgefragte
  Kennung im Verzeichnis steht.
- Exportdateien tragen `modules_schema`; ältere Dateien ergänzt `upgrade_modules`, damit nichts
  verschwindet.

| Gruppe | Modul | Kennung | Vorgabe | Setzt voraus |
|---|---|---|---|---|
| Mitglieder | Mitglieder | `members` | an | – |
| | Mitgliedsausweise | `cards` | aus | Mitglieder |
| | Mitgliederbereich | `portal` | an | Mitglieder |
| | Ehrungen & Jubiläen | `awards` | an | Mitglieder |
| | Qualifikationen | `qualifications` | an | Mitglieder |
| | Würden | `honors` | aus | – |
| Vereinsleben | Termine | `events` | an | – |
| | Aufgaben | `todos` | an | – |
| | Chronik | `chronicle` | aus | – |
| | Versammlungen | `meetings` | aus | Termine |
| | Helferdienste | `helpers` | aus | Termine |
| Musik | Musik | `music` | aus | Termine, Notenarchiv |
| | Notenarchiv | `scores` | aus | – |
| Wettbewerbe | Wettbewerbe | `competitions` | aus | – |
| | Schießsport | `shooting` | aus | Wettbewerbe |
| | Meldungen | `entries` | aus | – |
| | Ausschreibungen | `calls` | aus | – |
| Kommunikation | Rundschreiben | `circulars` | an | – |
| | Dokumente | `docs` | an | – |
| | Social Media | `social` | aus | Webseite |
| | Webseite | `website` | aus | – |
| Verwaltung | Kasse | `finance` | an | – |
| | Beiträge und Rechnungen | `billing` | an | – |
| | Material | `material` | aus | – |
| | Räume und Anlagen | `infrastructure` | aus | – |
| | Belegung | `bookings` | aus | Material oder Räume |
| | Steuern & Gemeinnützigkeit | `tax` | aus | Kasse |
| | Zuwendungsbestätigungen | `donations` | aus | Kasse |

Konzept und weitere Schritte: Projektunterlage „Module neu ordnen“.
