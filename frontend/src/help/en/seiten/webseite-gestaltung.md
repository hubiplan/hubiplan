---
key: page.website_design
titel: Website › Design
bereich: webseite
modul: website
rechte: [website.manage, website.content]
routen: [/webseite/gestaltung]
stichworte: [design, colours, logo, header image, banner, font, design package, export, import]
---

Under Design you choose the look, colours and logo of the website. The colours usually come from the unit's appearance and can be adjusted here.

With **Header image** you choose an image from the image library that appears at the top of the website instead of the coat of arms and club name, for example a banner with lettering. It should contain the club name and be wide, about 1200 × 300 pixels. Without a header image the coat of arms and name stay.

Under **Share design** you save a design as a ZIP file with **Save as package**. The package contains the styling, the layout of header, footer and home page and the colour defaults, but no coat of arms, texts or images.

Platform administrators can import a package under **Load design from package**. With a new **Short name** and **Name** it becomes an own design, for example a styling variant for your club only. **Check** lets HUBIplan check the package: no JavaScript, no content from other addresses, no imported HTML/Django templates. **Import** releases the design for this website; under **Imported designs** the release can be switched on and off for each website.

Design packages use maintained built-in layouts with custom CSS and colours. Imported HTML/Django templates are rejected. Legacy packages with such templates are quarantined and display Classic until replaced by a package without templates. Layout markup follows maintained components rather than freezing historic HTML.
