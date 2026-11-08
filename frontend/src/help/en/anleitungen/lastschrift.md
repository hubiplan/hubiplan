---
key: guide.debit_run
titel: Create a direct debit and submit it to the bank
modul: billing
rechte: [billing.edit]
routen: [/finanzen/lastschrift]
reihe: 50
stichworte: [SEPA, direct debit, collection, bank, XML]
---

Before you start: the creditor ID is set under Setup › Invoice & payment, and the members have a SEPA mandate.

1. Open [Finance › Direct debits](/finanzen/lastschrift).
2. Check the list “Before the direct debit run”, for example expiring mandates.
3. Choose the collection date and click the button to create the direct debits.
4. Download the file and submit it in online banking.
5. Once the bank has collected, click **Book as collected** and then **Book payments**. The invoices are then marked as paid.

The collection date must be a bank business day: not a weekend and none of the TARGET2 holidays (1 January, Good Friday, Easter Monday, 1 May, 25 and 26 December). Otherwise HUBIplan names the next bank business day.

![Starting point: Create a direct debit and submit it to the bank](bild:lastschrift)
