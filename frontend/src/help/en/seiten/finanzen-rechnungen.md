---
key: page.finance_invoices
titel: Finance › Invoices
bereich: beitraege
modul: billing
rechte: [billing.view]
routen: [/finanzen/rechnungen]
stichworte: [invoice, fee, open, paid, cancellation]
---

This lists all of the unit's invoices, such as membership fees or uniform costs, with their status: open, paid, reminded or cancelled. You create a single invoice here; a fee run creates many at once.

Name searches ignore letter case and normalize Unicode spelling variants; “ß” and “ss” are treated as equal. Other selected filters still apply.

Enter a search term and choose **Search** or press Enter. Status and other filters apply immediately.

After you change the selection, previous results are hidden until the new request finishes. If loading fails, **Reload** retries the same selection.

Final invoices show credited advances and the remaining outstanding amount. A credited
advance invoice is marked “Settled”. Its receipts remain in the cashbook. Cancel the
associated final invoice before removing those payments. A final invoice fully covered
by advances can also be cancelled if it has no additional payments.

Cancelling: in the invoice, choose **Cancel invoice** and give a reason. HUBIplan then creates a separate cancellation invoice, for example R2026-0012-S. It has its own date and reason, refers to the number and date of the invoice and lists all items with negative amounts. The issued invoice stays unchanged. **View cancellation invoice** opens the document and **Send cancellation invoice by email** sends it to the recipient. Members also find it in the member area.

Paid invoices can be cancelled too. The payments then remain on the invoice as a credit. **Refund** reverses the payments in the cash book with today's date; then transfer the amount back. **Offset** moves the payments to an open invoice to the same recipient.

**Cancel and create again** cancels the invoice and opens a copy as a new draft, so you correct a wrong invoice in one step. Invoices from a fee run are recalculated in the fee run instead.
