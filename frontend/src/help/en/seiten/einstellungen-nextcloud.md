---
key: page.settings_nextcloud
titel: Settings › Nextcloud
rechte: [org.edit]
routen: [/einstellungen/nextcloud]
stichworte: [Nextcloud, sign-in, file storage]
---

Here you connect your club's Nextcloud with HUBIplan so members can sign in there with their HUBIplan account.

With **Disable accounts automatically**, HUBIplan switches the Nextcloud account off as soon as someone no longer has access with you, for example because their role ends. Sessions and sync apps are signed out; the files are kept. If the person gets a role again, the account is switched back on. This needs a separate service account with an app password in Nextcloud. Use **Check connection** to test it.

Under “Accounts via HUBIplan” you see who has already signed in via HUBIplan and what the next synchronisation would do. If the synchronisation stops because too many accounts would be affected at once, check the roles and then confirm with **Synchronise now**.

Under **Adjust groups for individual roles** you choose which Nextcloud groups a role is put in, for example “1st treasurer” and “2nd treasurer” both in “Treasurer”. Separate several groups with commas. Without an entry, the group has the same name as the role. If you rename a role, the assignment stays.

Nextcloud itself decides how long a sign-in lasts: usually up to 24 hours without activity and up to 15 days with “stay logged in”; sync apps stay connected permanently. If access ends in HUBIplan without automatic disabling, only the next sign-in fails. Running sessions and sync apps only end when the account is disabled, automatically or by hand in Nextcloud.

“Only with PKCE (S256)” is switched on from the start and protects the login code. The Nextcloud app “user_oidc” uses PKCE by itself. You only need to switch it off for older applications that cannot do PKCE.
