# Module

Einzige Quelle: `backend/access/modules.py` (Modulverzeichnis). Die Oberfläche liest es über
`GET /api/modules/`; der Rechtekatalog (`access/catalog.py`) leitet daraus ab, welche Module
abschaltbar sind und welche eine neue Einheit bekommt.

- **Eingeschaltet** steht in `Organization.enabled_modules`. Abfragen im Code nutzen die
  Kennung aus dem Verzeichnis, für Untereinheiten `module_on(org, id)` (sie erben die Module
  ihres Vereins; Kasse, Rechnungen und Webseite führen sie selbst).
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
- `tests/test_modulnamen.py` prüft, dass jede im Code abgefragte Kennung im Verzeichnis steht.
- Exportdateien tragen `modules_schema`; ältere Dateien ergänzt `upgrade_modules`, damit nichts
  verschwindet.

| Gruppe | Modul | Kennung | Vorgabe | Setzt voraus |
|---|---|---|---|---|
| Mitglieder | Mitglieder | `members` | an | – |
| | Mitgliedsausweise | `cards` | aus | Mitglieder |
| | Mitgliederbereich | `portal` | an | Mitglieder |
| | Ehrungen & Jubiläen | `awards` | an | Mitglieder |
| | Würden | `honors` | aus | – |
| Vereinsleben | Termine | `events` | an | – |
| | Aufgaben | `todos` | an | – |
| | Chronik | `chronicle` | aus | – |
| | Versammlungen | `meetings` | aus | Termine |
| | Helferdienste | `helpers` | aus | Termine |
| Musik | Musik | `music` | aus | Termine |
| Wettbewerbe | Wettbewerbe | `competitions` | aus | – |
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

Konzept und weitere Schritte: Projektunterlage „Module neu ordnen“.
