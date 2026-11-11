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

**Invoice mailbox**: If an invoice mailbox is set up on the server, the address of your unit
is shown at the top, e.g. `rechnung+k7m2q9ab@example.org`. Give it to your suppliers. HUBIplan
collects the mailbox every minute and imports XML attachments and ZUGFeRD/Factur-X PDFs just
like an import. The entry then shows **By email from** with the sender. If the sender does not
match any business partner (email address under Club › Business partners), **Unknown sender**
appears; then check the issuer and bank details with particular care. Emails without
an e-invoice, such as an ordinary PDF invoice, spam or malware, are listed under **Notices from the mailbox**
until you choose **Done**. **Assign new address** invalidates the previous
address, for example if it receives spam.

**Business partners**: HUBIplan suggests a business partner for each invoice, recognised by
VAT ID, IBAN, the email sender (including the contact persons' email addresses) or name.
**Link suggestion** accepts it; **Create as business partner** creates a new supplier from the
name, VAT ID, IBAN and sender. **Unlink business partner** removes the link. When you later
link a cash book entry, it takes over the business partner.

**New IBAN**: If the invoice IBAN differs from the one stored for the business partner,
HUBIplan shows a clear warning. Call the issuer on a number you already know, not the one on
the invoice, and tick **New IBAN confirmed by phone** before approving. HUBIplan stores the
confirmed IBAN with the business partner. This protects you against fake invoices with
someone else's bank account.

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
