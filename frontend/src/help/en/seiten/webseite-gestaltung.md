---
key: page.website_design
titel: Website › Design
modul: website
rechte: [website.manage, website.content]
routen: [/webseite/gestaltung]
stichworte:
  [
    design,
    colours,
    logo,
    header image,
    banner,
    font,
    fine-tuning,
    style settings,
    corners,
    width,
    menu,
    footer,
    design package,
    export,
    import,
  ]
---

Under Design you choose the look, colours and logo of the website. The colours usually come from the unit's appearance and can be adjusted here.

Under **Fine-tuning** you adjust the chosen design without any programming. The settings are in six collapsible groups: font, page, cards/images/buttons, header and menu, home page and footer. Each setting has two or three fixed levels, for example corners “square”, “slight” or “round”; yes/no questions are switches. If no field is chosen, the website shows what the design provides. A second click on the chosen field resets the setting, **Reset** resets all of them. Whatever a design sets itself (such as the position of the coat of arms in the sidebar design) is greyed out. The coat of arms and the club name cannot both be hidden. The fonts are stored on the website itself (free licences); nothing is loaded from other servers. Check the result in the preview.

With **Header and menu › Background: Header image** you choose an image from the image library that appears at the top of the website instead of the coat of arms and club name, for example a banner with lettering. It should contain the club name and be wide, about 1200 × 300 pixels. Without a header image, or with the background “white” or “coloured”, the coat of arms and name stay.

In the browser tab and on the phone home screen the website shows the unit's own icon, otherwise its coat of arms (square, with a transparent border). You set both under Settings › Appearance. Without an icon or coat of arms the website shows no icon of its own. Browsers often keep an old icon for a while; reloading the page helps.

Under **Share design** you save a design as a ZIP file with **Save as package**. The package contains the styling, the layout of header, footer and home page and the colour defaults, but no coat of arms, texts or images.

Platform administrators can import a package under **Load design from package**. With a new **Short name** and **Name** it becomes an own design, for example a styling variant for your club only. **Check** lets HUBIplan check the package: no JavaScript, no content from other addresses, no imported HTML/Django templates. **Import** releases the design for this website; under **Imported designs** the release can be switched on and off for each website.

Design packages use maintained built-in layouts with custom CSS and colours. Imported HTML/Django templates are rejected. Legacy packages with such templates are quarantined and display Classic until replaced by a package without templates. Layout markup follows maintained components rather than freezing historic HTML.
