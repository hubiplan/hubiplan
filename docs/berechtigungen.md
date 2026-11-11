# Berechtigungen: Bereiche mit drei Stufen

Seit November 2026 (Ralf 02.11.): Jede Rolle hat je **Bereich** eine Stufe:
*kein Zugriff*, *lesen* (`<bereich>.view`) oder *bearbeiten* (`<bereich>.edit`). Bearbeiten
schließt Lesen ein. Dazu kommen **Zusatzrechte** zum Ankreuzen, die nur mit dem Leserecht
ihres Bereichs gehen: `export.lists` (Mitgliederlisten), `export.full` (vollständiger
Datenexport, Auskunft), `roles.preview` (Ansicht als Rolle), `mcp.connect` (KI-Assistenten
verbinden, mit „Webseite: Inhalte lesen“, nur mit zweitem Faktor; siehe [mcp.md](mcp.md)).

- Katalog: `backend/access/catalog.py` (`AREAS`, `EXTRAS`). Rollen von Untereinheiten
  (Zug-Rollen über die Mitgliedschaft) nutzen dieselben Bereiche, nur eine Auswahl
  (`Area.dept_levels`).
- Gespeichert wird `Role.permissions` als Liste der neuen Codes. `Role.save()` und die
  Schnittstellen übersetzen frühere Codes (`normalize`); alte Exportdateien übersetzt
  `from_legacy`.
- Prüfung: `OrgScopedMixin.read_permission` / `write_permission` (ein Code oder ein Tupel, von
  dem einer genügt). Die wirksamen Rechte (`permissions_in`, `department_contexts`) enthalten für
  den Übergang auch die früheren Codes (`effective`), damit ältere Prüfstellen und die
  Android-App weiter funktionieren. Neue Prüfungen nutzen die neuen Codes.
- Mehrere Rollen: je Bereich die höchste Stufe. Ansicht als Rolle: Schnittmenge.
- Zwei-Faktor-Pflicht für *bearbeiten* in Rollen, Kasse, Vereine, Plattform und für
  `export.full` (`accounts/mfa_policy.py`).
- Verwaltungsdaten benötigen das Leserecht ihres Bereichs: Organisation, Impressum und
  Briefbogen `settings.view`, eigene Farbkonfiguration `theme.view`, Rollendefinitionen
  `roles.view`. Die minimale Untereinheitsauswahl und mitgliederbezogene Einstellungen
  haben getrennte Schnittstellen; sie geben keine Verwaltungs- oder fremden Rollendaten aus.
- Einstellungen bearbeiten vermittelt keine Rollenverwaltung. Rollen einer Untereinheit,
  ihre wirksamen Zuweisungen und das Einrichten eines Verwalters erfordern `roles.edit`.
  Bestehende Einstellungsrollen werden nicht automatisch zu vereinsweiten Rollenverwaltern
  aufgewertet. Ihre bisher implizite Untereinheits-Rollenpflege entfällt ebenfalls.
  Soll jemand sie weiter ausführen, muss ein Rollenverwalter das Bearbeitungsrecht für
  Rollen bewusst vergeben. Die gespeicherten Codes ändern sich nicht; eine Datenmigration
  ist nicht nötig. Eine ältere Programmfassung hat wieder ihre frühere implizite Kopplung.
- Migration `access/0016_bereiche` schreibt bestehende Rollen verlustfrei um (mit Rückweg).

Bereiche und Zuordnung der früheren Codes: Konzept `konzepte/berechtigungen.md` im
Projektordner.
