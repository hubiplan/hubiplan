---
key: page.settings_nextcloud
titel: Settings › Nextcloud
bereich: einstellungen
rechte: [org.edit]
routen: [/einstellungen/nextcloud]
stichworte: [Nextcloud, sign-in, file storage]
---

Here you connect your club's Nextcloud with HUBIplan so members can sign in there with their HUBIplan account.

With **Disable accounts automatically**, HUBIplan switches the Nextcloud account off as soon as someone no longer has access with you, for example because their role ends. Sessions and sync apps are signed out; the files are kept. If the person gets a role again, the account is switched back on. This needs a separate service account with an app password in Nextcloud. Use **Check connection** to test it.

Under “Accounts via HUBIplan” you see who has already signed in via HUBIplan and what the next synchronisation would do. If the synchronisation stops because too many accounts would be affected at once, check the roles and then confirm with **Synchronise now**.
