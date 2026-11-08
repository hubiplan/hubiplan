---
key: page.finance_closing
titel: Finance › Closing & reports
bereich: finanzen
modul: finance
rechte: [finance.view]
routen: [/finanzen/abschluss]
stichworte: [year-end closing, cash report, audit, DATEV, retention period, deletion hold, taxes]
---

Here you produce the cash report for the general meeting and close a financial year. After closing, the bookings can no longer be changed. There are also exports, for example for DATEV or the cash audit.

Once the retention period has ended (receipts 8 years, books 10 years after the end of the calendar year), receipts can be deleted and books anonymised. The periods are set by law and cannot be shortened. If an audit or a legal dispute is still ongoing, use **Set deletion hold** on the financial year and give a reason. While it applies, nothing is deleted. Board members who can manage roles may set and lift it; both are recorded in the log.

The **Taxes** tab shows the tax report for a financial year. It belongs to the Tax & charitable status module. It also needs categories assigned to tax areas (Setup › Categories). You see:

- **Tax-free limit**: income from commercial operations including VAT compared with the tax-free limit (€50,000 since 2026, €45,000 before), plus the two previous years. From 80 % you get a note, above the limit a warning.
- **By tax area**: income, expenses and result per area. Cancellations are offset against the cancelled booking. A loss in the commercial operations shows a note.
- **Included cash books**: sub-units with their own cash book count towards the club unless their settings mark them as "separate for tax purposes". A sub-unit only sees its own figures in its own report.
- **Small-business limit**: turnover from purpose-related and commercial operations in the previous and the current year. If the club shows VAT on its invoices, this part is left out.
- **Tax return**: once the details of the exemption notice are entered, this shows for which years the next return is due.

The report is also available as PDF and Excel, for example for your tax adviser. It is a template, not tax advice.

The **VAT** tab (Tax & charitable status module) is a template for the advance VAT return. For the selected month, quarter or year it shows boxes 81 and 86 (taxable turnover at 19 % and 7 %, with the tax base in whole euros), 48 (tax-exempt turnover), 66 (input VAT) and 83 (amount payable or refund). Bookings with a tax rate are counted. Input VAT only counts for expenses outside the non-profit area, proportionally for mixed use; a cancellation reduces the cancelled booking. Sub-units that belong to the club for tax purposes are included. Under **Settings** you choose whether **The club is liable for VAT (not a small business)**, the **Advance return period** and whether input VAT is calculated as a flat rate under § 23a UStG: 7 % of taxable turnover instead of input VAT from invoices (box 63), only if this turnover did not exceed €50,000 in the previous year; the choice is binding for five years. HUBIplan does not transmit anything to ELSTER. In the DATEV export, bookings with a tax rate get the matching tax key.

The **Allowances** tab (also part of the Tax & charitable status module) adds up the trainer allowance (§ 3 no. 26 EStG, €3,300 since 2026) and the volunteer allowance (§ 3 no. 26a EStG, €960 since 2026) per person and calendar year. It counts expenses for which **Expense allowance to a person** is selected in the cash book; cancellations do not count. From 80 % there is a note, above the tax-free amount a warning: the payment is then taxable, usually as a mini-job.

The tax-free amounts apply across all payers together. Under **PDF** there is a declaration per person to sign, confirming they do not use the amount elsewhere. Once signed, it belongs with the receipts. If a board member receives an allowance, HUBIplan warns as long as **Our statutes allow the board to be paid** is not ticked (§ 27 (3) BGB).

Besides cash book expenses, the following also count:

- waiving the allowance as an expense donation: tick **Waiver of reimbursement of expenses** on the donation and choose the type under **Waiver of an allowance**. The amount uses up the tax-free allowance just like a payment,
- payments from the musician settlement: when an expense is assigned to an approved musician remuneration, HUBIplan sets the trainer allowance (artistic activity) and counts it for the musician,
- payments by sub-units with their own cash book that belong to the club for tax purposes. The same person then appears only once, with all payments in the expandable list below the name. The sub-unit itself only sees its own payments and a note where it is counted.

The **Fixed assets** tab is the fixed asset register: items from €250 net that are used for several years, such as tents, refrigerated trailers or furniture. With **Add fixed asset** you enter the date of acquisition, cost, tax area and type of depreciation: straight-line over the useful life (by month), at once as a low-value asset (up to €800 net), as a pool over five years (€250 to €1,000 net) or none. The register shows depreciation and book value for the selected financial year, also as Excel. Record a sale or scrapping as a disposal.

Depreciation only appears here and on the **Taxes** tab, never in the cash book. There it replaces the purchase expense in the result, so that an expensive purchase in commercial operations does not show up as a loss.

The **Cash audit** tab guides you through auditing a financial year. The treasury creates the assignment with **Create audit assignment**: financial year, names of the auditors, deadline and number of samples. HUBIplan draws the five largest expenses plus further random entries and adds a row per account for reconciliation. The auditors get access under Settings › Roles and permissions with a role that may read the treasury but not keep it, ideally with an end date. The page shows who currently has auditor rights and until when.

Only the auditors can tick items off, not the treasury itself. They compare each sample with its document (in order, or a query with a remark), enter the balance per bank statement or cash count for each account, rate the checkpoints and record findings and the recommendation on discharge. **Draw 5 more** enlarges the sample. When nothing is open, they finish with **Complete audit**. The **Audit report (PDF)** is meant for the meeting; if the audit is reopened, the reason goes into the change log. The **Before closing the audit** checklist shows what is still open: checkpoints, account reconciliation, samples, findings, auditor names and the recommendation.

The **Net assets** tab shows what the club owns and owes at the end of a financial year: account balances, open invoices to members and business partners, fixed assets at book value from the asset register (Tax & charitable status module) and open incoming invoices. Anything paid only after the year end counts as open on the reporting date. If reserves are switched on, it also shows how much is set aside and how much is freely available. The overview is also part of the treasurer's report for the general meeting.

The **Artists' social security levy** tab (Tax & charitable status module) adds up the fees paid to self-employed artists and writers per calendar year, e.g. for a band, drum corps, DJ or graphic designer. It counts expenses ticked **Fee paid to artists (artists' social security levy)** in the cash book and all expenses of a category marked as **Artist fees** under Setup › Categories; cancellations do not count. The page shows the total per recipient, the levy at that year's rate (2026: 4.9 %) and the deadline for reporting to the Künstlersozialkasse (31 March of the following year), also as Excel.

The **Use of funds** tab (Tax & charitable status module) is a simplified statement on the use of funds. Non-profit funds must be used for the statutory purposes or placed in permitted reserves by the end of the second financial year after they were received. The page shows per year the amount carried over, the funds received (income of the non-profit area and surpluses of the other areas), their use (expenses of the non-profit area, losses of purpose-related operations), additions to and releases from reserves, and what is still to be used by year of origin. The oldest funds are used first. If a deadline has passed, a notice appears. From 100,000 € income per year the tax office usually expects such a statement.
