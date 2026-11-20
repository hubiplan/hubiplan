---
key: page.finance_rates
titel: Finance › Set up › Fee rates
modul: billing
rechte: [billing.edit]
routen: [/finanzen/einrichtung/beitraege]
stichworte: [fee, fee rate, membership type, reduction, size, bands, work hours, required hours, substitute fee]
---

Fee rates define who pays how much, usually per membership type and period. A fee run uses them to calculate the invoices.

With **Fees by size**, organisation members pay a fee based on their size, e.g. number of employees or inhabitants. Each band has a minimum and/or maximum size and an annual fee; a band for a specific membership type takes precedence over a general one. Enter the size in the member file. Organisations without a size pay the fee of their membership type.

![“Fees by size” card](bild:beitragsstaffel-groesse)

## In detail

The **Family and company fee** applies to invoices to a household or company (see Members › Households and companies). For each kind you choose a type: **Maximum per invoice** (the sum of the individual fees is capped), **Flat rate** (exactly this amount, never more than the sum) or **Graduated (second person, from the third)** (the second person pays a percentage less, from the third a further one). Amounts are per year and are split across instalments like fees. With **from persons** and **only with at least one adult** you limit when the reduction applies. The invoice keeps the individual fees; the reduction is a separate line below them.

You set **Work hours** per membership type: **required hours per year** and the **substitute fee per missing hour**. Empty means no required hours. With **Required from age** and **Required up to age** you exempt younger and older members; the age at the start of the financial year counts. Hours done are volunteer shifts where the person is ticked as **done** (Volunteer duties module). Anyone who was a member for only part of the year owes the hours pro rata per started month. Missing hours are added to the fee invoice in the first fee run of the following financial year as a separate item “Substitute fee for missing work hours”, also for fee-free membership types. **Status per member** shows beforehand who did how many hours and what is missing. Anyone who leaves before the fee run gets no fee invoice and therefore no substitute fee either.
