---
key: page.finance_einvoices
titel: Finances › Customer invoices
bereich: beitraege
modul: billing
rechte: [billing.view]
routen: [/finanzen/rechnungen/leistungen, /finanzen/geschaeftspartner]
stichworte: [E-invoice, XRechnung, business partner, customer invoice, EN16931]
---

Create a customer under **Finances** → **Business partners** first. Membership is not
required. Under **Invoices** → **Customer invoices**, enter the income category, service
period, addresses, buyer reference and payment IBAN. Enter net prices in EUR.

Choose the tax treatment explicitly. Exempt, zero-rated and outside the scope of VAT
are different categories. Exempt, reverse-charge and out-of-scope items require a
reason. XRechnung requires the supplier's contact name and phone number.
Without a VAT identifier, the supplier needs a unique business partner identifier,
such as the supplier number agreed with the customer.

**Validate e-invoice** displays errors and warnings. **Validate and issue** validates
again and assigns the final invoice number only on success. Issued invoices and
addresses cannot be changed. Download the XML, validation report and readable view.
Technical validation does not replace checking the service or tax treatment.

**Payments and delivery** opens the existing invoice view. Sending includes the XML
and readable view. Cancelling an open, unpaid invoice creates a separate structured
cancellation document. Download and deliver that document to the recipient yourself.

Use **Invoice type** to choose an invoice, advance invoice or final invoice. A final
invoice includes the entire service and credits payments already received against
advance invoices for the same customer and event. This creates no duplicate income.
If payments change after drafting, save and validate the draft again. Credited advances
are marked “Settled”. Cancel the final invoice before removing their payments.

**Create and validate ZUGFeRD** generates a locally validated PDF/A file with embedded
XML from the original. Then **Download ZUGFeRD**, including cancellation documents.
Originals and validation reports remain available.

For Peppol, enter registered electronic addresses and EAS codes for the business
partner and supplier. The platform administrator configures the selected provider
for each club. **Transmit electronically** explicitly sends the original;
**Fetch delivery status** retrieves confirmation. Unconfirmed attempts are reconciled
with the provider before retrying. Send cancellations separately. Without a provider
connection, download the document and upload it manually to the recipient's portal.
Existing membership invoices remain available.
