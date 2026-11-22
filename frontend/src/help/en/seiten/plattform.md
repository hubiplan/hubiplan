---
key: page.platform
titel: Platform
modul: platform
rechte: [platform.manage]
routen: [/plattform]
stichworte: [platform, create club, umbrella association, enable modules, self-update]
---

Platform administration creates clubs and umbrella associations on this HUBIplan instance and enables modules. When creating one, a person receives the “board” role with all rights and then manages roles and users themselves.

In the list of units, each unit shows the number of enabled modules (“12 modules”); click it to see them one by one.

Under settings you set the deletion period after leaving. A shorter period only applies 30 days after the change. Until then, data is still deleted after the longer one, so that a typo does not immediately delete the data of former members.

## Deactivating or deleting units

Under **Units** → **Edit**, clear “is active” and save to deactivate a unit. Its data is retained and the unit can be activated again later.

Deletion happens in two stages:

1. **Deactivate and schedule deletion**: in the edit form, enter the full name under “Delete unit”. The unit and all subunits below it are deactivated immediately; nobody can access them any more and the data is retained. While deletion is scheduled the unit cannot be activated again; **Withdraw scheduling** cancels it.
2. **Delete permanently**: at the earliest 30 days after scheduling (an empty unit that never had members or financial data straight away) and only once the statutory retention periods for books and vouchers of all financial years have expired (§ 147 AO: vouchers 8, books 10 years). The form shows until when the periods run. A deletion hold on a financial year prevents deletion. To confirm, enter the name; HUBIplan also asks for a current two-factor code. If the unit has financial data, state who confirmed the retention periods (e.g. auditor or tax advisor).

Permanent deletion removes the members, roles, financial records and stored files of the unit and its subunits. User accounts are retained. Clubs belonging to a federation must be deleted or moved first. If references from other units prevent deletion, an error is shown and the data is retained. The deletion is recorded in the platform audit log and on the deletion list: if an older backup is restored later, HUBIplan deletes the unit again.

## New versions

Once a day HUBIplan asks GitHub whether a newer release is available. If so, you see the notice “A newer version of HUBIplan is available” at the top, with a link to the changes. None of your data goes to GitHub; GitHub only sees the server's IP address, and the platform's privacy policy mentions this. Whoever runs the server can switch the check off with `HUBIPLAN_UPDATE_CHECK=0` in the `.env`. Once the new release is running, the changes are listed under [News](/hilfe/neuigkeiten).

## Updating from HUBIplan (self-update)

Platform › Version shows which version is running and whether a newer release is available. If the operator has turned on self-update (`HUBIPLAN_SELBSTUPDATE=1`, see `docs/betrieb.md`), you can install the new release there with “Update to …”. This needs two-factor sign-in, and you enter your password again.

HUBIplan only leaves an order. A service on the server first backs up the database, checks the release signature and that it is newer than the running version, and then installs it. HUBIplan is unavailable for a few minutes meanwhile; the page checks back on its own and then shows the result. If anything fails, the previous version keeps running. Every order is recorded in the change log, and the operator receives a security email.

## Virus scanning

If no virus scanning is set up on the server, or it is switched off for sharing, a notice appears there: circular attachments and public documents then go out unscanned. With virus scanning (ClamAV) set up, HUBIplan shares such files only after scanning them.

If the virus scanner is briefly unreachable, HUBIplan still accepts uploaded documents, attachments and receipts, but locks them until the scanner has checked them (quarantine). Platform › Version shows how many files are waiting and whether malware was found in any of them; such files stay locked for good.

## Addresses per unit

In the **Addresses per unit** section of the platform settings you assign further addresses to a unit, for example `mitglieder.sv-musterstadt.example` to Schützenverein Musterstadt. Anyone opening HUBIplan via that address sees the unit's name, colours, coat of arms and icon on the sign-in page; after signing in, the unit is preselected. Unknown addresses and the main address show the instance. Links in the unit's emails (invitation, sign-in link, events, volunteer shifts, tasks, membership card, photo link, circulars) lead to its address, otherwise to that of the next higher unit with its own address; “Forgot password” sends the link for the address on which it was requested.

The unit uploads its own icon under Settings › Appearance; without one, HUBIplan uses its coat of arms. Sign-in applies per address. The address must point to the server via DNS. If the server has `HUBIPLAN_ADRESSEN_AUS_LISTE=1` set, it accepts listed addresses without further configuration and obtains the certificate on first access; otherwise the operator must allow them (`DJANGO_ALLOWED_HOSTS`, certificate). Nextcloud, the app connection and federation stay on the main address.

## Feedback on the help

Below every guide and page help you find “Did this help?”. The **Help** tab shows the answers per help text, most “No” first, with the sentence about what was missing. Only the help text, language, version, answer, sentence and day are stored, no person and no club. If a sentence does name someone, take it out with **Remove**; the answer still counts.

Below that, **Searches without results** lists what people searched for in the help without finding anything, with a counter. Entries with digits or email addresses are not stored.

## Security: browser reports

HUBIplan gives every browser rules for what the interface may load and run (Content Security Policy). If a page breaks them, for example because someone tried to inject a foreign script, the browser blocks the content and reports it to your own instance. The **Security** tab shows these reports: what was blocked, which rule applied, on which page, how often, and when first and last.

Only the rule, the blocked origin (without path), the page (without numbers and search words) and the day are stored, no person, no club and no address of the visitor. Nothing is sent to third-party services.

The reports are not authenticated. Browser extensions trigger them, and because the browser sends them without signing in, anyone can send one. HUBIplan discards reports from extensions as far as they can be recognised. How to read the list:

- A blocked script from a foreign address (marked “script”) deserves a look: which page was it on, and could someone have entered text containing code there? For the first such entry the operator receives a security email, at most one per day.
- The same report on many pages shortly after an update points to a bug in HUBIplan itself. Please report it to the project.
- Single entries with foreign addresses for images or fonts mostly come from extensions or translation services in the browser.

**Remove** takes out an entry you have clarified, **Remove all** empties the list. If a browser reports the same violation again, it appears again. The list holds at most 500 different entries; when it is full, new ones are only recorded again after you remove some.
