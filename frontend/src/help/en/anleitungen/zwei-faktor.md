---
key: guide.two_factor
titel: Set up two-factor authentication
routen: [/mein-konto/anmeldung]
reihe: 20
stichworte: [2FA, authenticator, phone, code, TOTP, security]
---

You need an authenticator app on your phone, for example FreeOTP, Aegis or Google Authenticator.

1. Open [Sign-in & security](/mein-konto/anmeldung) under **My account**.
2. In the **Two-factor authentication** section, scan the QR code with the app.
3. Enter the **Code from the app** and **Your password for confirmation**.
4. Click **Activate**.
5. Keep the **Recovery codes** that appear in a safe place, for example printed. Each code
   works once if you don't have your phone.

![The “Two-factor authentication” section with the QR code](bild:konto-zwei-faktor)

Club logo in the app: The QR code contains your club's logo. Some apps such as FreeOTP show it
as the icon. Others, for example Google Authenticator, Microsoft Authenticator, 2FAS or Aegis, show
the initials instead. In Aegis you can choose your own image for the entry, in 2FAS you can change
the letters and colour. An entry
you already set up only changes when you set up two-factor authentication again.

## Confirming sensitive actions

For some actions HUBIplan asks again for a current code from the app if your last code is
older than 10 minutes: full exports and spin-offs, assigning roles or extending their rights,
resetting another person's two-factor authentication, creating the QR code for the HUBIplan app
and permanent deletion (club, former member, name in the chronicle). A recovery code works too.
If you have not set up two-factor authentication yet, you confirm with your password during the
transition period.

Platform administration has no transition period: without two-factor authentication its
rights are paused until you set it up here. Board and treasurer have 14 days; the deadline is
shown at the top of every page.
