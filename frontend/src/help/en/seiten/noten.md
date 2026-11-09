---
key: page.scores
titel: Sheet music
modul: scores
rechte: [scores.view]
routen: [/noten]
stichworte: [Noten, Notenarchiv, Notenbestand, Chor, Arrangement, Stimme]
---

# Sheet music

The sheet music archive manages pieces, arrangements, parts and digital scores. Without the Music module, for example in a choir without performance planning, it appears as its own **Sheet music** entry in the sidebar; with Music you find it under Music › Sheet music library.

Anyone with the right “Maintain sheet music library” may edit it. Roles with music rights can read the inventory so that programmes and rehearsals can pick arrangements.

**Import sheet music catalogue** takes over an existing catalogue from a CSV file. Upload digital scores in the document storage and link them to an arrangement under **Sheet music documents**.

## Music folders for the app

Under **Music folders** you create fixed folders such as a **March book** or the **Repertoire**. Each folder holds arrangements in a fixed order, optionally with a number (“No. 27”). Use ↑ and ↓ to change the order.

Musicians find the folders in the “HUBIplan” app under **Sheet music** and can search by title, composer or number there. Everyone only sees the parts for their own voice, and only files that the document storage shares with members. Without a selection under **Visible to**, all musicians see the folder; otherwise only members of the chosen sub-units.

If a piece has several files for one voice (for example page 1 and 2 as images), **Order when there are several files** under **Sheet music documents** sets the order in which they are shown.

## Music files: PDF, images, MusicXML and MIDI

Upload sheet music in the document storage. Besides PDF, JPEG and PNG, HUBIplan understands **MusicXML** (`.musicxml`, `.mxl`, `.xml`) and the open formats **MEI** and **ABC**. MuseScore, Capella, Sibelius and Finale export MusicXML (usually under “Export” or “Save as”).

- From a MusicXML score, each musician only gets their own part. HUBIplan picks the part by the instrument and register of the link. If that is not unambiguous, enter the part’s name as it appears in the file under **Sheet music documents** in **Part in the MusicXML score**.
- In the browser, MusicXML music opens as a PDF. In the app it is engraved to fit the screen and can be transposed.
- Link **MIDI files** (`.mid`) as listening examples. For MusicXML music, HUBIplan creates the listening example itself.
