---
key: guide.bank_fetch
titel: Fetch transactions directly from the bank
modul: finance
rechte: [finance.edit]
routen: [/finanzen/kontoauszuege]
reihe: 105
stichworte: [bank, FinTS, HBCI, transactions, fetch, PIN, TAN, bank access, online banking]
---

Instead of downloading a file from online banking, HUBIplan can fetch the transactions from the bank itself. For this the bank connection must be set up on the server and switched on for the club under Settings › Modules.

## Set up once

1. Under Finance › Accounts, enter the IBAN for the bank account.
2. Open [Finance › Bank statements](/finanzen/kontoauszuege) and click **Add bank access**.
3. Enter a name, the bank code (BLZ), the FinTS address of your bank and your login name for online banking. The bank states the FinTS address (also “HBCI with PIN/TAN”) on its website or by phone.
4. Enter your PIN and click **Sign in to the bank**. If the bank offers several approval methods, choose the one you also use in online banking.

HUBIplan then links the accounts whose IBAN the bank lists for this access.

## Fetch transactions

1. Click **Fetch transactions** next to the bank access and enter your PIN.
2. If the bank asks for an approval, type in the TAN or confirm in your bank’s app. With approval in the app, HUBIplan continues by itself.
3. The new transactions then appear as a statement in the list, with suggestions as for an imported file.

HUBIplan fetches from the last fetch onwards, the first time the last 90 days. Transactions that have already been imported, also from a file, are not added twice.

## Your PIN

Your PIN is entered anew for every fetch. HUBIplan does not store it. If the bank rejects the sign-in, HUBIplan asks before the next attempt; after two rejections the access is paused for 24 hours so that the bank does not block it.
