---
key: page.settings_data_transfer
titel: Settings › Data transfer
rechte: [data.export, export.run]
routen: [/einstellungen/datenuebernahme]
stichworte: [export, backup, move, JSON]
---

With the full export you take all of the unit's data as a file, for example to move to another HUBIplan instance or as your own backup. The import loads such a file. Keep the file safe; it contains personal data.

## In detail

New exports explicitly identify their permission schema. Files without a schema and with ambiguous codes require an explicit selection
of the original meaning. **Check again** shows the resulting effective role
permissions, which must be explicitly confirmed before import. The historical
schema includes former photo/card/login data access. Newly
exported narrow read permissions remain narrow. Unknown schemas are rejected. URLs
must use HTTP(S). If scanning is enabled, every inner file actually reused is scanned
individually, even when the outer archive exceeded the upload scan limit. Required
scanning rejects missing scanners and oversized inner files; an error aborts import.

Importing a sub-unit from a file requires, besides “Settings”, the edit permissions for the areas the file contains, for example “Members” (edit) for memberships or “Documents” (edit) for folders and documents. If one is missing, the check lists the missing permissions. All rows of the file must belong to the new sub-unit; the statutes from the file are not taken over, they belong to the club. Importing, exporting a sub-unit and links in the federation require a fresh confirmation with the second factor.

When an umbrella association exports its clubs, the file contains for the clubs only what the association can also see in HUBIplan with its access: master data, contact details and memberships (with read access), member types and sub-units. Photos, the clubs’ own custom fields, honours, qualifications, roles with their holders, letterheads as well as the clubs’ documents, meetings, tasks, helper plans and statutes are not included. The platform handles the complete move of a club.
