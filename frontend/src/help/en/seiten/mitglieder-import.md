---
key: page.members_import
titel: Members › Import
bereich: mitglieder
modul: members
rechte: [members.edit]
routen: [/mitglieder/import]
stichworte: [import, Excel, CSV, spreadsheet, migration]
---

With the import you take over an existing member list from a spreadsheet (Excel or CSV). HUBIplan first shows how it reads each column and which people already exist. Nothing is saved until you confirm.

The import recognises organisations as members (company, association, authority …) by the column “Typ” with the value “Organisation”. For them there are the columns “Namenszusatz” (name suffix), “Rechtsform” (legal form) and “Ansprechpartner Name”, “Ansprechpartner Vorname”, “Ansprechpartner Funktion”, “Ansprechpartner E-Mail” and “Ansprechpartner Telefon” (contact person). Further contact persons go in further rows with the same membership number; the first becomes the primary contact. First name and date of birth stay empty for organisations. If a name without a type looks like an organisation (e.g. “… GmbH” or “… e. V.”), the check reports it instead of guessing.
