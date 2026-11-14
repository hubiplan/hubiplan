---
key: page.events
titel: Events
modul: events
routen: [/termine]
stichworte: [calendar, event, accept, decline, subscription]
---

The calendar shows the unit's events. With the right to do so, you create events, including recurring ones, and invite members who accept or decline. With the calendar subscription the events appear in your own calendar on phone or PC. Under Events › Setup you manage categories, external calendars, sharing with other units and the website link. Under “External calendars” the calendar imports other calendars’ events every hour, e.g. the federation’s from Vereinsplaner.

Each entry names its unit and, where applicable, its external calendar, so you can distinguish events with the same title before opening them. In the month view, a multi-day event starts with its start time; subsequent days show “Continued”, and the last day shows, for example, “Continued until 01:05”. An end exactly at midnight is shown on the preceding day as 24:00, without an extra entry on the new day. All-day events remain labelled as such. The list and accessible names include the complete date and time range; the list is the default view on small screens.

You can tell an event’s category not only by its colour: every event has a light background and a stripe on the left in its category colour, and the category name appears below the title. On small screens the month view shows a short code instead of the name (e.g. “Mee” for Meeting). The legend above the month explains the colours and codes of all categories in that month. Screen readers announce the category too.

![Calendar with units and continuation past midnight](bild:kalender-kontext)

In an open event, the block **For this event** shows what belongs to it: the meeting, volunteer duty rosters, booked rooms and equipment, tasks and the music performance. From there you also create a duty roster or a booking for the event. You only see areas whose module is switched on and for which you have the right. Events, meetings, volunteer duties and tasks are grouped together in the sidebar under “Planning”.

Under **Attachments** in the open event you attach files: the field **Add attachment (PDF, JPEG or PNG, at most 15 MB)** uploads a file, and **Link a document from the document store** picks a document from your unit's document store. A linked document always shows its newest version; if you upload a new version in the document store, it applies to the event right away. Everyone who may see the event also sees its attachments, in the member area and in the app, even if the folder in the document store has narrower visibility; the dialog points this out before linking. To link, you need the right to edit the event and to see the document store. If the document is in the trash, it disappears from the event and comes back when restored. **remove** only removes the link; the document stays in the document store. For recurring events, the attachments apply to all occurrences. For public events, each attachment has **show on the website**: only ticked attachments appear on the website in the event window; all others stay internal. If the event later becomes internal, they disappear there again.

**Write a circular about it** creates a draft to those invited. It contains title, time, place, description and the reply deadline, and the event's PDF attachments go along as attachments. In the circular you can pick only those invited with **no reply yet**, **accepted** or **declined**, for example for a reminder. All circulars for the event are then listed in the block. **Reminder to everyone without a reply** creates such a draft right away to everyone who has not replied yet (and, if “Maybe” is allowed, to those as well). You see the replies in the event's participant list.

The event dialog first asks for title, time and place, then category and **Who sees the event?**. Rarely used options are folded under **More settings**: **Pass on upwards**, **Pass on downwards** and **Hide end time on the website**. If one of them is set, the section is open. The header and the save bar stay in place while you scroll in the dialog.

Under **Directions** you enter notes such as parking or the entrance. Without further details the links **Route in OpenStreetMap** and **Route in Google Maps** lead to the address. If the address is not enough (marquee, shooting range in the woods), enter **Latitude** and **Longitude** or paste a link from OpenStreetMap or Google Maps under **Take point from map link**. Directions and route links appear in the event, in the emails, on the reply page and in the calendar subscription; no map is embedded. If you pick a saved place, the event copies its address, directions and point.

When creating or editing an event, enable **Hide end time on the website** to show only the start time publicly. The internal calendar and calendar subscription keep the end time. For recurring events, the setting applies to all occurrences.

After successfully accepting, declining or withdrawing your response, a confirmation is provided as a status message for screen readers. Focus stays at the action when accepting or declining; after withdrawal it moves to **Accept**. An error produces no success confirmation; you can retry your response.

For replies to an event you can switch on **Allow “Maybe” as an answer**. “Maybe” does not count against the maximum number, but the reminder before the event also goes to these members. **Allow a comment** is on by default; with **Own question for the comment (optional)** (e.g. “Meal preference?”) it appears above the field instead of “Comment”. The participant list and the export show “Maybe” and the comments.

Every email about the event (invitation, reminder, circular about the event) contains a personal link “Accept or decline (without login)” for each member. It opens a page with time, place, description and attachments; there the member chooses “I am coming”, “Maybe” or “I am not coming” and saves. Just opening the link saves nothing. The same link lets them change the answer until the deadline, as do the member area and the app. The invitation carries the event's attachments directly as email attachments (up to 5 files, 10 MB each); larger ones are on the page behind the link.

Create a personal calendar-subscription link for your own calendar app. Keep it private. Creating a new link invalidates the previous link. A status confirms when your link is ready.

![Create a personal calendar subscription](bild:kalender-abo)
