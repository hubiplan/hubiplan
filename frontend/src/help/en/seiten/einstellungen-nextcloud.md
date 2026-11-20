---
key: page.settings_nextcloud
titel: Settings › Nextcloud
rechte: [org.edit]
routen: [/einstellungen/nextcloud]
siehe: [guide.account_create]
stichworte: [Nextcloud, sign-in, file storage, calendar, CalDAV]
---

Here you connect your club's Nextcloud with HUBIplan so members can sign in there with their HUBIplan account.

With **Disable accounts automatically**, HUBIplan switches the Nextcloud account off as soon as someone no longer has access with you, for example because their role ends. Sessions and sync apps are signed out; the files are kept. If the person gets a role again, the account is switched back on. This needs a separate service account with an app password in Nextcloud. Use **Check connection** to test it.

Under “Accounts via HUBIplan” you see who has already signed in via HUBIplan and what the next synchronisation would do. If the synchronisation stops because too many accounts would be affected at once, check the roles and then confirm with **Synchronise now**.

## Events in the Nextcloud calendar

Under **Events in the Nextcloud calendar**, HUBIplan writes your events into the Nextcloud calendar. There are two calendars: **Events for members** with everything every member sees, and **“Board only” events**. Each calendar is shared read-only with one group, by default “Mitglieder” and “Vorstand”. Members of the group see it in the Nextcloud calendar app and on their phone.

Events are still edited in HUBIplan. Every 15 minutes HUBIplan writes changes across; **Synchronise calendars now** does it straight away. This needs the service account and app password. If you switch a calendar off, it also disappears from Nextcloud. Please share the board calendar only with a group that contains just the board.

## In detail

Under **Adjust groups for individual roles** you choose which Nextcloud groups a role is put in, for example “1st treasurer” and “2nd treasurer” both in “Treasurer”. Separate several groups with commas. Without an entry, the group has the same name as the role. If you rename a role, the assignment stays.

Nextcloud itself decides how long a sign-in lasts: usually up to 24 hours without activity and up to 15 days with “stay logged in”; sync apps stay connected permanently. If access ends in HUBIplan without automatic disabling, only the next sign-in fails. Running sessions and sync apps only end when the account is disabled, automatically or by hand in Nextcloud.

“Only with PKCE (S256)” is switched on from the start and protects the login code. The Nextcloud app “user_oidc” uses PKCE by itself. You only need to switch it off for older applications that cannot do PKCE.

The accounts “admin”, “root”, “administrator” and the service account can never be assigned, not even via “Existing user names in the Nextcloud”. If such a line is already there, the page shows it in red; it has no effect and should be removed. Changes to user names and groups for roles require a fresh confirmation with the second factor, and everyone allowed to manage roles gets a notice by email.
