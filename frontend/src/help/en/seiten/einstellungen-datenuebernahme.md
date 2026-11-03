---
key: page.settings_data_transfer
titel: Settings › Data transfer
bereich: einstellungen
rechte: [data.export, export.run]
routen: [/einstellungen/datenuebernahme]
stichworte: [export, backup, move, JSON]
---

With the full export you take all of the unit's data as a file, for example to move to another HUBIplan instance or as your own backup. The import loads such a file. Keep the file safe; it contains personal data.

New exports explicitly identify their permission schema. Files without a schema and with ambiguous codes require an explicit selection
of the original meaning. **Check again** shows the resulting effective role
permissions, which must be explicitly confirmed before import. The historical
schema includes former photo/card/login data access. Newly
exported narrow read permissions remain narrow. Unknown schemas are rejected. URLs
must use HTTP(S). If scanning is enabled, every inner file actually reused is scanned
individually, even when the outer archive exceeded the upload scan limit. Required
scanning rejects missing scanners and oversized inner files; an error aborts import.
