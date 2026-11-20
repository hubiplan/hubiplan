---
key: page.settings_nextcloud
titel: Settings › Nextcloud
rechte: [org.edit]
routen: [/einstellungen/nextcloud]
siehe: [guide.account_create]
stichworte: [Nextcloud, sign-in, file storage, calendar, CalDAV, groups, group folders]
---

Here you connect your club's Nextcloud with HUBIplan so members can sign in there with their HUBIplan account.

With **Disable accounts automatically**, HUBIplan switches the Nextcloud account off as soon as someone no longer has access with you, for example because their role ends. Sessions and sync apps are signed out; the files are kept. If the person gets a role again, the account is switched back on. This needs a separate service account with an app password in Nextcloud. Use **Check connection** to test it.

Under “Accounts via HUBIplan” you see who has already signed in via HUBIplan and what the next synchronisation would do. If the synchronisation stops because too many accounts would be affected at once, check the roles and then confirm with **Synchronise now**.

## Keep groups in sync

Otherwise Nextcloud only takes over groups at sign-in. Sync apps on phones and computers never sign in again: someone who gives up a role but keeps an account would keep the group, such as “Kassierer”, with all its group folders. With **Keep groups in sync**, HUBIplan sets the groups right after every change to roles, offices or units, and every night.

Under **Groups HUBIplan keeps in sync**, enter which groups HUBIplan may set and remove, for example “Vorstand, Mitglieder, Kassierer”. The group of accounts via HUBIplan is always included. HUBIplan never touches groups you maintain by hand, or “admin”. The service account must be group admin of each of these groups in Nextcloud.

**Compare groups** shows beforehand who joins which group and who drops out of which; it does not change anything yet. If more than three accounts would lose groups at once, synchronisation stops and everyone who manages roles gets an email. Then check the roles and confirm with **Synchronise groups now**. Files are never lost, only access to the group's folders.

## Files in Nextcloud

With **Save to Nextcloud**, a **Save to Nextcloud** button appears next to the cash report, tax evaluation, cash count, minutes, resolution book and documents. The file goes into a folder of the service account: “Vorstand”, “Kasse” or “Mitglieder” inside the **Folder in the service account** (by default “HUBIplan”). Each folder is shared read-only with one group, by default “Vorstand”, “Kassierer” and “Mitglieder”. Nothing is overwritten; if the name exists, HUBIplan adds a number.

Each file gets a type when it is saved, and the type decides how long it stays in Nextcloud: resolutions and foundations as well as planning and statistics without personal data permanently, accounting and tax records 10 years and reports to associations 6 years after year end, lists with personal data 3 months, everything else 2 years. Under **Adjust periods per type** you can change this. When the period ends, HUBIplan deletes the file into the service account's trash. HUBIplan saves lists with personal data only after explicit confirmation and never in the “Mitglieder” folder.

Keep in mind: HUBIplan's encryption, permissions and log do not apply in Nextcloud. Anyone using a sync app also has the files on their device.

With **Folder to take files from**, a **From Nextcloud** button appears when uploading documents, website images, attachments to events and circulars, and receipts. In Nextcloud, share a folder with the service account, for example “An HUBIplan”, and enter its name here. HUBIplan fetches a copy and checks it like any uploaded file; nothing changes in Nextcloud. Anyone who may upload files in HUBIplan sees everything in this folder.

## Events in the Nextcloud calendar

Under **Events in the Nextcloud calendar**, HUBIplan writes your events into the Nextcloud calendar. There are two calendars: **Events for members** with everything every member sees, and **“Board only” events**. Each calendar is shared read-only with one group, by default “Mitglieder” and “Vorstand”. Members of the group see it in the Nextcloud calendar app and on their phone.

Events are still edited in HUBIplan. Every 15 minutes HUBIplan writes changes across; **Synchronise calendars now** does it straight away. This needs the service account and app password. If you switch a calendar off, it also disappears from Nextcloud. Please share the board calendar only with a group that contains just the board.

## Video room for events

With **Video room for events**, every event you may edit gets a **Create video room** button. HUBIplan then creates a Talk conversation in the service account, with link and password. Everyone who can see the event sees both: in HUBIplan, in the member area, in the apps, in the invitation and reminder and in the Nextcloud calendar. The public website and calendar subscriptions never show the video room. This needs Talk in Nextcloud and a service account with app password.

After **Delete room after … days** (7 by default, counted from the end of the event, for series from the end of the recurrence) HUBIplan deletes the conversation and its chat in Nextcloud; the same happens when the event is deleted. Without a dedicated video backend for Nextcloud, video works well only with a few participants; with more people it helps to leave cameras off. If a general meeting should also take place online, the statutes or the notice of meeting must provide for it.

## In detail

Under **Adjust groups for individual roles** you choose which Nextcloud groups a role is put in, for example “1st treasurer” and “2nd treasurer” both in “Treasurer”. Separate several groups with commas. Without an entry, the group has the same name as the role. If you rename a role, the assignment stays.

Nextcloud itself decides how long a sign-in lasts: usually up to 24 hours without activity and up to 15 days with “stay logged in”; sync apps stay connected permanently. If access ends in HUBIplan without automatic disabling, only the next sign-in fails. Running sessions and sync apps only end when the account is disabled, automatically or by hand in Nextcloud.

“Only with PKCE (S256)” is switched on from the start and protects the login code. The Nextcloud app “user_oidc” uses PKCE by itself. You only need to switch it off for older applications that cannot do PKCE.

The accounts “admin”, “root”, “administrator” and the service account can never be assigned, not even via “Existing user names in the Nextcloud”. If such a line is already there, the page shows it in red; it has no effect and should be removed. Changes to user names and groups for roles require a fresh confirmation with the second factor, and everyone allowed to manage roles gets a notice by email.
