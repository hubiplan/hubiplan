---
key: page.members_import
titel: Members › Import
modul: members
rechte: [members.edit]
routen: [/mitglieder/import]
stichworte: [import, Excel, CSV, spreadsheet, migration]
---

With the import you take over an existing member list from a spreadsheet (Excel or CSV). HUBIplan first shows how it reads each column and which people already exist. Nothing is saved until you confirm. Rows without a membership number are given the next free numbers in turn when importing, counting the numbers in the file as well.

The import recognises organisations as members (company, association, authority …) by the column “Typ” with the value “Organisation”. For them there are the columns “Namenszusatz” (name suffix), “Rechtsform” (legal form) and “Ansprechpartner Name”, “Ansprechpartner Vorname”, “Ansprechpartner Funktion”, “Ansprechpartner E-Mail” and “Ansprechpartner Telefon” (contact person). Further contact persons go in further rows with the same membership number; the first becomes the primary contact. First name and date of birth stay empty for organisations. If a name without a type looks like an organisation (e.g. “… GmbH” or “… e. V.”), the check reports it instead of guessing.

A separate billing address (for people and organisations, e.g. a company’s accounts department or the parents of a child) goes in the columns “Rechnungsempfänger” (invoice recipient), “Rechnung z. Hd.” (attn.), “Rechnung Straße oder Postfach” (street or PO box), “Rechnung PLZ” (postcode), “Rechnung Ort” (town) and “Rechnung Land” (country), plus “Rechnungs-E-Mail” (billing email), “Bestellnummer” (purchase order number) and “Leitweg-ID”. These are the same columns as in the export. A separate address needs street (or PO box) and town; billing email, purchase order number and Leitweg-ID also work on their own.

A few rules during the check: HUBIplan adds the leading 0 that Excel drops from numbers to a four-digit postcode (country Germany or empty) and shows this in the preview. Numbers such as “1.000” without a comma are ambiguous and are rejected; please write “1000” or use a decimal comma. If several rows for the same person contain different values in a custom field, or different details for a period with the same entry date, the check reports the contradiction. An invalid date in a date custom field is an error in that row.
