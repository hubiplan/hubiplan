---
key: page.website_social
titel: Website › Social media
modul: website
rechte: [website.manage, website.content]
routen: [/webseite/beitraege]
siehe: [guide.mcp_tasks]
stichworte: [Instagram, Facebook, post, social media]
---

Here you connect Instagram or Facebook and show selected posts on the website. HUBIplan stores the posts so the website works without third-party services.

Drafts for posts: if an AI assistant has prepared a post, it appears here with text and images. **Copy text** puts the text on the clipboard; clicking an image opens it for saving. You post in your own Instagram or Facebook account, then **Mark as done**. HUBIplan never publishes drafts itself.

At the top you manage the club’s social media channels, i.e. the profile links shown in the website header and in letter templates. They used to be under Settings › Organisation.

**Fetch now** schedules a background fetch. Repeated requests are coalesced; manual and periodic fetches of the same channel never run concurrently. Reload later to see the results. The web process does not wait for Meta or image downloads.

## Redirect URI

Each channel shows the exact address to enter in your Meta app as redirect URI, with a **Copy** button, and the app domain below it. If your unit has its own club address (e.g. `verein.musterverein.example`), Meta sends you back there. Sign in at that address to connect. Channels connected before keep their old address; **Use club address** switches over, then enter the new address in the Meta app.

## Likes and comments

With **Show likes and number of comments** each post on the website shows the number of likes (on Facebook all reactions) and comments. Albums appear on the website with all their images.

**Show comments** is off at first, because comments come from other people. With “only after approval”, new comments appear only after **Approve comment**; you can hide any comment again with **Hide comment**. After switching it on, connect the channel once via **Reconnect** so that Meta allows reading the comments. Names of Facebook users are shortened (“Erika M.”); on Instagram the public user name is shown. Switching off deletes all stored comments.
