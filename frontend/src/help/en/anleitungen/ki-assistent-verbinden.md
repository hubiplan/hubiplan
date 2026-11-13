---
key: guide.mcp_connect
titel: Connect AI assistants to HUBIplan
routen: [/mein-konto/app]
reihe: 50
stichworte:
  [
    design,
    menu,
    upload images,
    alternative text,
    Instagram,
    Facebook,
    AI,
    Claude,
    ChatGPT,
    MCP,
    assistant,
    website,
    draft,
    write texts,
  ]
---

An AI assistant such as Claude or ChatGPT can read your unit's website and edit it as a draft: texts, home page, design and menu. Publishing happens only in HUBIplan, by a person. The assistant may never do more than you yourself; member data, emails and payments are not available through it.

Once beforehand (board or role management):

1. Switch on the “AI assistants” module under [Settings › Modules](/einstellungen/module). It needs the website.
2. Under [Settings › Roles and permissions](/einstellungen/rollen), give the suitable role the extra permission “Connect AI assistants”.
3. Anyone who wants to connect needs two-factor sign-in (My account › Sign-in & security).

Connecting:

1. Open [My account › App & other instances](/mein-konto/app) and copy the address under “AI assistants”, e.g. `https://verein.example.org/api/mcp/verein/`.
2. Enter it in the assistant as a new connection (depending on the assistant “connector”, “integration” or “MCP server”).
3. The assistant opens HUBIplan in the browser. Sign in with password and code, choose the unit and click **Allow**.

Before allowing, check the address under “Access goes to”: that is where your rights go. Anyone can give an assistant any name. If HUBIplan warns that the address does not belong to any known assistant, only allow it if you have just set up the connection yourself. If the link came by email or message, click **Decline**.

Then you can write to the assistant, for example: “Revise the ‘About us’ text on our website and make it friendlier.” The assistant saves the draft and gives you a link to the preview. If you like the result, you publish it in HUBIplan under Website. Every change appears in the change log with “KI-Assistent” and can be undone.

What else the assistant can do:

- Design, menu and home page: choose design, colours, fine-tuning, header image and header image for phones, arrange the menu (headings, external links, button) and add, move or hide custom home page sections. This needs the “Manage website” permission and goes into the draft. Switching blocks on or off is only possible in HUBIplan.
- Title image and image carousel: the assistant can set the large image at the top of the home page (image or image carousel of the greeting) and the image at the top of a text page, for example “Use the new photo of the parade as the title image”. This also goes into the draft. If the image has no alternative text, it points this out.
- Upload images: write, for example, “I want to upload photos from the summer festival”. The assistant gives you a link that is valid for 30 minutes and up to 20 images. Open it on your phone or PC and choose the photos; they go straight to HUBIplan, not through the chat, and end up under Website › Images.
- Describe images: the assistant sees the images in a small size and suggests alternative text and caption. For images already on the website it only fills in missing texts; you change existing ones yourself. It does not recognise or name people.
- Images by address: HUBIplan fetches an image itself from servers you approve under [Website › Web address](/webseite/domain) at “Images for AI assistants” (such as the club’s Nextcloud). The source goes into the caption. Without an entry this is not possible.
- Appearance: change colours with names and use, further colours, gradients, colour roles and the logo (from an image under Website › Images). This applies immediately to HUBIplan and the website, there is no draft; the assistant asks first. Any change can be taken back in the change log with “Undo”. It needs the permission for the appearance, and connections made before this change must be connected once more.
- Posts for Instagram or Facebook: the assistant stores text and images as a draft under [Website › Social media](/webseite/beitraege). There you copy the text, save the images and post yourself; HUBIplan publishes nothing on Meta.

New images only become public once they are in a published text or section.

You get an email for every new connection. A connection is valid for at most 30 days and ends after 14 days without use, and also when you change your password or lose the permission. You can disconnect it at any time under [My account › App & other instances](/mein-konto/app) with **Disconnect**.

What you write to the assistant and what it reads goes to its provider. Do not put confidential data there. Without signing in, an assistant can only read the HUBIplan help at `/api/mcp/`.
