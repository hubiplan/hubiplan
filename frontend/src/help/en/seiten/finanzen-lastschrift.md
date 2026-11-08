---
key: page.finance_debits
titel: Finance › Direct debits
modul: billing
rechte: [billing.view]
routen: [/finanzen/lastschrift]
stichworte: [SEPA, direct debit, collection, mandate, bank]
---

From open invoices with a valid SEPA mandate HUBIplan creates a direct debit file that you upload in online banking. A checklist first checks the creditor ID, deadlines and expiring mandates. HUBIplan does not connect to the bank itself.

For organisation members (and for clubs of an association) you can choose **Business direct debit (B2B)** as the **Scheme** when recording a paper mandate. This needs a signed mandate on the business form, and the payer must register it with their bank. The payer cannot reverse a business direct debit once it has been paid. In a direct debit run, core and business debits sit in separate blocks of the same file. For persons there is only the **Core direct debit**.

If loading fails, **Reload** retrieves proposals and runs again. A failed request is shown as an error rather than an empty selection.
