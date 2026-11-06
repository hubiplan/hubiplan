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

## Deactivating or deleting units

Under **Units** → **Edit**, clear “is active” and save to deactivate a unit. Its data is retained and the unit can be activated again later.

To delete it completely, choose **Delete unit** in the edit form, enter its full name and confirm with **Delete permanently**. The unit's members, roles, financial records and stored files are removed. User accounts are retained. Delete or move subordinate units first. If references from other units prevent deletion, an error is shown and the data is retained. The deletion is recorded in the platform audit log. Existing backups are unaffected.

## New versions

Once a day HUBIplan asks GitHub whether a newer release is available. If so, you see the notice “A newer version of HUBIplan is available” at the top, with a link to the changes. None of your data goes to GitHub; GitHub only sees the server's IP address, and the platform's privacy policy mentions this. Whoever runs the server can switch the check off with `HUBIPLAN_UPDATE_CHECK=0` in the `.env`. Once the new release is running, the changes are listed under [News](/hilfe/neuigkeiten).

## Updating from HUBIplan (self-update)

Platform › Version shows which version is running and whether a newer release is available. If the operator has turned on self-update (`HUBIPLAN_SELBSTUPDATE=1`, see `docs/betrieb.md`), you can install the new release there with “Update to …”. This needs two-factor sign-in, and you enter your password again.

HUBIplan only leaves an order. A service on the server first backs up the database, checks the release signature and that it is newer than the running version, and then installs it. HUBIplan is unavailable for a few minutes meanwhile; the page checks back on its own and then shows the result. If anything fails, the previous version keeps running. Every order is recorded in the change log, and the operator receives a security email.

## Addresses per unit

In the **Addresses per unit** section of the platform settings you assign further addresses to a unit, for example `mitglieder.sv-musterstadt.example` to Schützenverein Musterstadt. Anyone opening HUBIplan via that address sees the unit's name, colours, coat of arms and icon on the sign-in page; after signing in, the unit is preselected. Unknown addresses and the main address show the instance. Links in the unit's emails (invitation, sign-in link, events, volunteer shifts, tasks, membership card, photo link, circulars) lead to its address, otherwise to that of the next higher unit with its own address; “Forgot password” sends the link for the address on which it was requested. The unit uploads its own icon under Settings › Appearance; without one, HUBIplan uses its coat of arms. Sign-in applies per address. The address must point to the server via DNS. If the server has `HUBIPLAN_ADRESSEN_AUS_LISTE=1` set, it accepts listed addresses without further configuration and obtains the certificate on first access; otherwise the operator must allow them (`DJANGO_ALLOWED_HOSTS`, certificate). Nextcloud, the app connection and federation stay on the main address.
