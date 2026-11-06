---
key: page.finance_cashbook
titel: Finance › Cash book
bereich: finanzen
modul: finance
rechte: [finance.view]
routen: [/finanzen/kassenbuch]
stichworte: [booking, receipt, income, expense, cash, split booking, split]
---

The cash book records every income and expense with date, account, category and receipt. Bookings in a closed period can no longer be changed, only corrected with a reversing entry. This keeps the cash book auditable.

Cancel bookings with receipts instead of deleting them. Imported bank statements are retained; ignore unwanted transactions. Archive used categories and create a new category for new assignments. Reminders retain their archived version.

Name searches ignore letter case and normalize Unicode spelling variants; “ß” and “ss” are treated as equal. Other selected filters still apply.

After you change the selection, previous results are hidden until the new request finishes. If loading fails, **Reload** retries the same selection.

If loading accounts or categories fails, **Reload** retries locally. Booking details you have already entered are retained when a refresh fails.

**Split (split booking):** If one payment belongs to several categories or tax areas, for example the caterer's settlement with drinks, admission and advertising, open the booking and choose **Split**. Each part gets a category, an amount and optionally an event and a description. Together the parts must add up exactly to the amount. Each part becomes a booking of its own with its own number. Date, account and payee or payer apply to all parts; receipts and the bank transaction stay with the first part. Splitting works as long as the booking is not locked and does not belong to a cancellation, a signed receipt, an invoice payment or a donation.
