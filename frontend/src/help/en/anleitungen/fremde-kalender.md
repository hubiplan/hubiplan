---
key: guide.event_external
titel: Show events from an external calendar
bereich: termine
modul: events
rechte: [events.manage]
routen: [/termine/fremde]
stichworte: [Vereinsplaner, iCal, federation, external events, subscription, token]
---

1. Ask the other club for a token from Vereinsplaner or a calendar subscription link (iCal).
2. Open [Events](/termine) and there the **External calendars** tab.
3. Choose the **Type**, enter a **Name** and add the token or link.
4. Choose category and visibility; “public” also shows the events on the website.
5. Click **Add and fetch**.

HUBIplan then fetches the events every hour; **Fetch now** fetches them at once. The events cannot be changed here. To drop an unsuitable event, open it in the calendar and click **Hide here**; you can show it again under **External calendars**.

![Starting point: Show events from an external calendar](bild:fremde-kalender)

External sources default to members-only visibility; making their copies public
requires a separate deliberate selection. A failed fetch retains the existing
copies unchanged. The source shows the error, last attempt and last successful
fetch. Legacy data and sources that never fetched successfully explicitly show an
unknown success time. There is no automatic deletion deadline for repeated fetch
failures: copies remain until the next successful sync or deliberate source
maintenance. A successful sync removes deleted, hidden or out-of-window events.
Disabling a source removes all copies immediately; an inactive new source does
not fetch anything. Deleting a source also deletes its copies and hidden-item
history. A strict automatic maximum age requires a separate policy decision and
is not an existing guarantee.
