---
key: page.website_design
titel: Website › Design and colours
modul: website
rechte: [website.manage, website.content]
routen: [/webseite/gestaltung]
stichworte: [design, colours, gradient, logo, draft, preview, publish, design package, icon]
---

Under **Design and colours** you choose the look, colours and logo of the website. The colours usually come from the unit's appearance and can be adjusted here. Design has its own items in the sidebar: **Design and colours**, **Fine-tuning**, **Areas** and **Versions**; you put together the home page under Website › Home.

When assigning colours you choose a palette colour, white or dark for each place of the design (header, menu, decorative lines, footer, colour bands, date box). The header, footer, colour bands and decorative lines can also get a gradient from the appearance settings instead of a colour; the menu, buttons and date box stay single-coloured, and rounded edges show the first colour of the gradient. Below, under **Text, surfaces and background**, you set the colour of body text, secondary text, surfaces (cards, table rows) and the page background. “Default” takes the colour ticked under **Used for** in Settings › Appearance, otherwise the design stays as it is; table rows then alternate with the surface colour; a chosen page background takes precedence over the “Background” control of the fine-tuning. If text on surfaces or background becomes hard to read (below 4.5 : 1), a notice appears.

Changes to design, colours, fine-tuning, header image, areas and home page are a draft first: visitors keep seeing the previous version. At the top of each of these pages you then see “Unpublished changes”. **Publish** makes the draft public, **Discard** undoes all changes. On a wide screen, a preview on the right shows the real website with the draft; it reloads after every change. At the top you choose **Phone**, **Tablet** or **Desktop**, **Reload** reconnects the preview, **In a new window** opens it full size. On narrow screens the **Preview** button opens the website in a new window. Anyone you gave a preview link can see the draft as well.

In the browser tab and on the phone home screen the website shows the unit's own icon, otherwise its coat of arms (square, with a transparent border). You set both under Settings › Appearance. Without an icon or coat of arms the website shows no icon of its own. Browsers often keep an old icon for a while; reloading the page helps.

Under **Share design** you save a design as a ZIP file with **Save as package**. The package contains the styling, the layout of header, footer and home page and the colour defaults, but no coat of arms, texts or images.

Platform administrators can import a package under **Load design from package**. With a new **Short name** and **Name** it becomes an own design, for example a styling variant for your club only. **Check** lets HUBIplan check the package: no JavaScript, no content from other addresses, no imported HTML/Django templates. **Import** releases the design for this website; under **Imported designs** the release can be switched on and off for each website.

Design packages use maintained built-in layouts with custom CSS and colours. Imported HTML/Django templates are rejected. Legacy packages with such templates are quarantined and display Classic until replaced by a package without templates. Layout markup follows maintained components rather than freezing historic HTML.
