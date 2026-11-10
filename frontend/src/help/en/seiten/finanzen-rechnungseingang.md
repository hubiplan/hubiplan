---
key: page.finance_incoming
titel: Finances › Incoming invoices
modul: finance
rechte: [finance.view]
routen: [/finanzen/rechnungen/eingang]
stichworte: [E-invoice, ZUGFeRD, incoming, approval, XML]
---

Import XML invoices or ZUGFeRD/Factur-X PDFs. HUBIplan retains the original even when
validation fails. Importing the identical file again does not create another entry.
Check different files with the same invoice number for duplicates yourself.

Technical validation (KoSIT) runs in the background after the import. Until it finishes,
the entry shows **Checking**; this usually takes less than a minute and the page refreshes
by itself. HUBIplan deletes declined entries and files without a readable e-invoice after
90 days if no booking is linked.

Validation covers the XML data. It does not certify PDF/A properties or consistency
between an external PDF view and its embedded XML. Use the **Readable view** of the
structured data for review.

Check the recipient, service, amount and bank details before approval. Enter a review
note and choose **Approve business review** or **Decline**. Approval requires successful
technical validation. Revalidation preserves previous reports in the audit export.

Importing and approving do not send a payment. After actual payment, link a matching
cash book entry. Type, EUR amount and an open financial year are checked; partial
payments cannot be linked here yet. The original also becomes a cash book attachment.
