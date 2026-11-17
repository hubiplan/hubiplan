---
key: page.account_login
titel: My account › Sign-in & security
routen: [/mein-konto/anmeldung]
stichworte: [password, two-factor, 2FA, authenticator, delete account]
---

This is where you change your password and switch **Two-factor authentication** on or off. With it,
signing in needs a code from your phone in addition to your password. Anyone who manages roles,
runs exports, posts in the cash book, may see all members or reads the change log and outbox has
to set it up; for platform administration this applies immediately. Before sensitive actions such
as a full export HUBIplan asks for a code again (guide “Set up two-factor authentication”).

A new address under **Change sign-in email** only takes effect once you have confirmed it with the link sent to the new
address. If you have no password of your own and only sign in with links, you also have to confirm
the change with the link sent to your previous address. After the change your other browsers are
signed out; the app stays connected.

To confirm, HUBIplan asks for your HUBIplan password, not the password of your email mailbox.
You have five attempts per hour for the sign-in email and ten for the password. After that the
message tells you in how many minutes you can try again. The hour starts with the first attempt.

If someone enters a wrong password for your account several times in a row, signing in with a
password is blocked for a few minutes, but only on unknown devices. On devices you have signed in
with before, and with a passkey, you can still get in. You will receive an email about it.

## Delete account

Under **Delete account** you delete your account yourself, with passkeys, connected devices,
authorisations for Nextcloud and AI assistants and your personal tasks. To confirm, enter your
login email; as with other sensitive actions, HUBIplan also asks for your passkey, code or
password. If you only sign in with links, delete the account within 10 minutes of signing in.
This is not possible while you hold roles: have them ended in the club first. What your club keeps
about you as a member remains; you can only leave or request deletion of your member data with
the club. A Nextcloud account you sign in to through HUBIplan is deactivated if the club has switched on “Disable accounts automatically”; otherwise the Nextcloud administration removes it.

If your account has had no access for 90 days (no member access, no role), HUBIplan deletes it
automatically. You receive an email two weeks before. If you get access again before then, the
account is kept.

A sign-in in the browser lasts twelve hours. Ten minutes before, HUBIplan asks; **Stay signed in**
lets you keep working without interruption. If the session has already expired, the page stays as
it is with your input: sign in again with **Sign in in a new tab**, come back and choose
**I am signed in again**.
