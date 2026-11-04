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

ZUGFeRD output, portal delivery and automatic advance/final invoices are not included
yet. Existing membership invoices remain available.
