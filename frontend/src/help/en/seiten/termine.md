---
key: page.events
titel: Events
modul: events
routen: [/termine]
stichworte: [calendar, event, accept, decline, subscription]
---

The calendar shows the unit's events. With the right to do so, you create events, including recurring ones, and invite members who accept or decline. With the calendar subscription the events appear in your own calendar on phone or PC. Under Events › Setup you manage categories, external calendars, sharing with other units and the website link. Under “External calendars” the calendar imports other calendars’ events every hour, e.g. the federation’s from Vereinsplaner.

## Reading the calendar

Each entry names its unit and, where applicable, its external calendar, so you can distinguish events with the same title before opening them. In the month view, a multi-day event starts with its start time; subsequent days show “Continued”, and the last day shows, for example, “Continued until 01:05”. An end exactly at midnight is shown on the preceding day as 24:00, without an extra entry on the new day. All-day events remain labelled as such. The list and accessible names include the complete date and time range; the list is the default view on small screens.

You can tell an event’s category not only by its colour: every event has a light background and a stripe on the left in its category colour, and the category name appears below the title. On small screens the month view shows a short code instead of the name (e.g. “Mee” for Meeting). The legend above the month explains the colours and codes of all categories in that month. Screen readers announce the category too.

![Calendar with units and continuation past midnight](bild:kalender-kontext)

## The open event

An open event is laid out like this: at the top are when, where and the calendar, below them a bar with the buttons **Edit**, **Write a circular about it**, **Reminder to everyone without a reply** and **Add to my calendar** (.ics). The **Responses** card shows the number of acceptances, refusals and open replies, Excel and PDF for the participant list and, to expand, everyone who has not replied yet. The **For this event** card shows one row for each thing that belongs to the event: circulars, meeting, volunteer duty roster, booked rooms and equipment, tasks, the music performance, equipment, the statement in the event finances and the attachments. The area is on the left, its state in the middle and the buttons on the right, for example **Open**, **Show** or + **Create**. **Delete** stands on its own at the very bottom. You only see areas whose module is switched on and for which you have the right. Events, meetings, volunteer duties and tasks are grouped together in the sidebar under “Planning”.

## Attachments

In the **Attachments** row you attach files: + **Add file** uploads a file (PDF, JPEG or PNG, at most 15 MB), and **From the document store** picks a document from your unit's document store. A linked document always shows its newest version; if you upload a new version in the document store, it applies to the event right away. Everyone who may see the event also sees its attachments, in the member area and in the app, even if the folder in the document store has narrower visibility; the dialog points this out before linking. To link, you need the right to edit the event and to see the document store. If the document is in the trash, it disappears from the event and comes back when restored. **remove** only removes the link; the document stays in the document store. For recurring events, the attachments apply to all occurrences. For public events, each attachment has **show on the website**: only ticked attachments appear on the website in the event window; all others stay internal. If the event later becomes internal, they disappear there again.

## Circular for the event

**Write a circular about it** in the button bar creates a draft to those invited. It contains title, time, place, description and the reply deadline, and the event's PDF attachments go along as attachments. In the circular you can pick only those invited with **no reply yet**, **accepted** or **declined**, for example for a reminder. All circulars for the event are then listed in the **Circulars** row. **Reminder to everyone without a reply** creates such a draft right away to everyone who has not replied yet (and, if “Maybe” is allowed, to those as well). You see the replies in the event's participant list.

## Create and edit an event

The event dialog first asks for title, time and place, then category and **Who sees the event?**. Rarely used options are folded under **More settings**: **Pass on upwards**, **Pass on downwards** and **Hide end time on the website**. If one of them is set, the section is open. The header and the save bar stay in place while you scroll in the dialog. “public” means visible on the website and without signing in. Inside HUBIplan the members of the level that creates the event see it; other units only see it if it is passed on upwards or downwards.

Under **Directions** you enter notes such as parking or the entrance. Without further details the links **Route in OpenStreetMap** and **Route in Google Maps** lead to the address. If the address is not enough (meadow, hut in the woods), enter **Latitude** and **Longitude** or paste a link from OpenStreetMap or Google Maps under **Take point from map link**. Directions and route links appear in the event, in the emails, on the reply page and in the calendar subscription; no map is embedded. If you pick a saved place, the event copies its address, directions and point.

When creating or editing an event, enable **Hide end time on the website** to show only the start time publicly. The internal calendar and calendar subscription keep the end time. For recurring events, the setting applies to all occurrences.

## Accepting and declining

After successfully accepting, declining or withdrawing your response, a confirmation is provided as a status message for screen readers. Focus stays at the action when accepting or declining; after withdrawal it moves to **Accept**. An error produces no success confirmation; you can retry your response.

For replies to an event you can switch on **Allow “Maybe” as an answer**. “Maybe” does not count against the maximum number, but the reminder before the event also goes to these members. **Allow a comment** is on by default; with **Own question for the comment (optional)** (e.g. “Meal preference?”) it appears above the field instead of “Comment”. The participant list and the export show “Maybe” and the comments.

Every email about the event (invitation, reminder, circular about the event) contains a personal link “Accept or decline (without login)” for each member. It opens a page with time, place, description and attachments; there the member chooses “I am coming”, “Maybe” or “I am not coming” and saves. Just opening the link saves nothing. The same link lets them change the answer until the deadline, as do the member area and the app. The invitation carries the event's attachments directly as email attachments (up to 5 files, 10 MB each); larger ones are on the page behind the link.

## Binding registration with participation fee

With the Registrations module (under Settings › Modules, needs events and invoices) an event gets binding registration instead of accepting and declining. An event has one or the other. In the open event you set it up with **Set up binding registration**: registration opens (optional), registration deadline (until then members can also cancel themselves), places, people per registration, whether members may register guests too, payment term, category in the accounts and terms of participation.

Every rate (e.g. members, guests, children aged 6 to 13) has one price or several price tiers that apply one after another, such as “early bird” until a date or for the first 50 people; the last tier applies until the registration deadline. Whoever has registered keeps their price. Prices are set by whoever may edit invoices; without that permission only free rates are possible. On first saving, an event is created under Finance to which the income is assigned.

Members register for the event in the members' area, if they like together with their family and with guests. For age-based rates HUBIplan asks for the date of birth. After **Register with obligation to pay** a registration confirmation arrives by email with the invoice as a PDF and the event for their own calendar. When the payment arrives (also via the bank statement), a payment confirmation follows. Anyone who cancels or is cancelled receives a confirmation with a cancellation invoice; the club refunds anything already paid.

The board sees all registrations with their payment status, uses **Add registration** to record registrations by phone or on paper (for members or guests with an address) and downloads the **List of participants (Excel)**. Guest data is anonymised six months after the event. An event with registrations cannot be deleted, only cancelled.
