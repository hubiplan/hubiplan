---
key: guide.member_import
titel: Import a member list from Excel
modul: members
rechte: [members.edit]
routen: [/mitglieder/import]
reihe: 20
stichworte: [import, Excel, CSV, migration, spreadsheet]
---

1. Open [Members › Import](/mitglieder/import).
2. Under **1. Upload file**, choose the spreadsheet (Excel or CSV, one row per person).
3. Under **2. Assign columns**, say which column contains what, such as name, date of birth or joining date.
   Only surname and first name are required. If the date of birth is missing and the club already
   has someone with the same name, the check reports an error.
4. Map values if needed, for example “A” to the membership type “active”.
5. Check the preview under **4. Check**; HUBIplan shows errors and people who already exist.
6. Click **Import**.

An import can be removed again under “Previous imports” with **Undo**.

![Starting point: Import a member list from Excel](bild:mitglieder-importieren)
