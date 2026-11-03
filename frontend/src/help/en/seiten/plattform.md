---
key: page.platform
titel: Platform
bereich: einstellungen
modul: platform
rechte: [platform.manage]
routen: [/plattform]
stichworte: [platform, create club, umbrella association, enable modules, self-update]
---

Platform administration creates clubs and umbrella associations on this HUBIplan instance and enables modules. When creating one, a person receives the “board” role with all rights and then manages roles and users themselves.

Under settings you set the deletion period after leaving. A shorter period only applies 30 days after the change. Until then, data is still deleted after the longer one, so that a typo does not immediately delete the data of former members.

## New versions

Once a day HUBIplan asks GitHub whether a newer release is available. If so, you see the notice “A newer version of HUBIplan is available” at the top, with a link to the changes. None of your data goes to GitHub; GitHub only sees the server's IP address, and the platform's privacy policy mentions this. Whoever runs the server can switch the check off with `HUBIPLAN_UPDATE_CHECK=0` in the `.env`. Once the new release is running, the changes are listed under [News](/hilfe/neuigkeiten).

## Updating from HUBIplan (self-update)

Platform › Version shows which version is running and whether a newer release is available. If the operator has turned on self-update (`HUBIPLAN_SELBSTUPDATE=1`, see `docs/betrieb.md`), you can install the new release there with “Update to …”. This needs two-factor sign-in, and you enter your password again.

HUBIplan only leaves an order. A service on the server first backs up the database, checks the release signature and that it is newer than the running version, and then installs it. HUBIplan is unavailable for a few minutes meanwhile; the page checks back on its own and then shows the result. If anything fails, the previous version keeps running. Every order is recorded in the change log, and the operator receives a security email.
