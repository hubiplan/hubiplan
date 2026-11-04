---
key: page.finance_debits
titel: Finance › Direct debits
bereich: beitraege
modul: billing
rechte: [billing.view]
routen: [/finanzen/lastschrift]
stichworte: [SEPA, direct debit, collection, mandate, bank]
---

From open invoices with a valid SEPA mandate HUBIplan creates a direct debit file that you upload in online banking. A checklist first checks the creditor ID, deadlines and expiring mandates. HUBIplan does not connect to the bank itself.

If loading fails, **Reload** retrieves proposals and runs again. A failed request is shown as an error rather than an empty selection.
