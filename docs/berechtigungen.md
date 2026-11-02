# Berechtigungen: Bereiche mit drei Stufen

Seit November 2026 (Ralf 02.11.): Jede Rolle hat je **Bereich** eine Stufe:
*kein Zugriff*, *lesen* (`<bereich>.view`) oder *bearbeiten* (`<bereich>.edit`). Bearbeiten
schließt Lesen ein. Dazu kommen **Zusatzrechte** zum Ankreuzen, die nur mit dem Leserecht
ihres Bereichs gehen: `export.lists` (Mitgliederlisten), `export.full` (vollständiger
Datenexport, Auskunft), `roles.preview` (Ansicht als Rolle).

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
- Migration `access/0016_bereiche` schreibt bestehende Rollen verlustfrei um (mit Rückweg).

Bereiche und Zuordnung der früheren Codes: Konzept `konzepte/berechtigungen.md` im
Projektordner.
