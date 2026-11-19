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

An open event is laid out like this: at the top are when, where and the calendar, below them a bar with the buttons **Edit**, **Write a circular about it**, **Reminder to everyone without a reply** and **Add to my calendar** (.ics). The **Responses** card shows the number of acceptances, refusals and open replies, Excel and PDF for the participant list and, to expand, everyone who has not replied yet.

The **For this event** card shows one row for each thing that belongs to the event: circulars, meeting, volunteer duty roster, booked rooms and equipment, tasks, the music performance, equipment, the statement in the event finances and the attachments. The area is on the left, its state in the middle and the buttons on the right, for example **Open**, **Show** or + **Create**. **Delete** stands on its own at the very bottom. You only see areas whose module is switched on and for which you have the right. Events, meetings, volunteer duties and tasks are grouped together in the sidebar under “Planning”.

## Attachments

In the **Attachments** row you attach files: + **Add file** uploads a file (PDF, JPEG or PNG, at most 15 MB), and **From the document store** picks a document from your unit's document store. A linked document always shows its newest version; if you upload a new version in the document store, it applies to the event right away. Everyone who may see the event also sees its attachments, in the member area and in the app, even if the folder in the document store has narrower visibility; the dialog points this out before linking.

To link, you need the right to edit the event and to see the document store. If the document is in the trash, it disappears from the event and comes back when restored. **remove** only removes the link; the document stays in the document store. For recurring events, the attachments apply to all occurrences. For public events, each attachment has **show on the website**: only ticked attachments appear on the website in the event window; all others stay internal. If the event later becomes internal, they disappear there again.

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

## Waiting list and cancellation fees

Under **Waiting list and cancellation** in the registration settings there are further rules. With **Waiting list when all places are taken**, new registrations go on the waiting list once the event is full (in the members' area the button then reads **Join the waiting list**). When a place becomes free, the next registration that fits moves up automatically, becomes binding and receives the invoice by email; it can then cancel free of charge for 48 hours.

The waiting list ends when the event starts, and anyone still waiting is told. Cancellation fees follow tiers such as “less than 14 days before: 50 %”, optionally with a fixed handling fee. Before cancelling, HUBIplan shows the fee; it comes as a separate invoice, and anything already paid is offset against it where it fits. If someone moves up from the waiting list instead, there is no fee; the board can waive it in individual cases with a reason (**Waive cancellation fee**).

With several people, individual people can be cancelled too; the invoice is then cancelled and reissued for the rest. With **Substitute**, someone else takes the place at the same rate and price, and the invoice stays. If the event is cancelled, HUBIplan cancels all registrations and the waiting list without a fee and writes to everyone. Optionally, unpaid registrations expire a few days before the start; the place then goes to the waiting list.

## Schedule and information letters

The “Schedule or programme” field says what happens when. The programme appears in the event and is included in circulars about the event. For an event with registrations the button in the button bar reads **Information letter to registrants**: the circular then goes to the people who registered, including guests without a membership, optionally only to binding registrations, the waiting list, paid or unpaid ones. HUBIplan fills placeholders such as registration number, people and amount outstanding for each registration. With **Send the letter to later registrations too**, anyone who registers later or moves up from the waiting list also receives the information letters already sent.

## Extras and questions

Under **Extras and questions** in the registration settings you can offer extras such as a coach trip or a menu, per person or per registration, with a surcharge and a place limit. They appear as a separate item on the invoice and as a column in the list of participants; the count (say, 32 schnitzels) is shown with the extra. Additional questions without a price (text, yes/no or a choice) apply per person or per registration and can be required.

You may only ask about allergies and intolerances if there is food (**with catering** or an extra of the type food). The answer is voluntary and needs consent; only the administration sees it, it appears only in the **List with allergies (Excel)** and is deleted 14 days after the event. If the catering is removed, information already collected is deleted. With **Minors can take part** the registration always asks for the date of birth; for participants under 18, the name, phone number and email of a parent or guardian are required, and a second person can be added.

## Public registration for non-members

For events with the visibility “public”, **Public registration** › **Non-members can register too (form with link)** lets people without a membership register as well. After saving, the link to the form appears with the registrations, with **Copy link** for passing it on, for example on the website, in an invitation or on a poster. The form shows the event, the programme, the rates for guests, free places, the cancellation rule and the terms of participation.

Whoever submits it first receives an email with a confirmation link that is valid for 24 hours; only then is the registration binding, the place taken and the invoice on its way. HUBIplan deletes unconfirmed registrations after 24 hours. The confirmation contains a link with which the person can view their registration and cancel according to the event's rules. A puzzle solved in the background and a limit per hour keep spam out. As with guests, the details are anonymised six months after the event.

## Registration on the club website

On the club website such an event shows, in the event window, the state of registration, the current prices with the deadline of the price tier, places left and the “Register now” button. The event gets a page of its own under “For this event” › **Website** › **Create**: this creates an event page as a draft under Website › Texts.

Date, place, directions, programme, prices, cancellation rule, terms of participation and documents come from the event; you maintain the text and further sections there like on any text page. With **Publish** the page appears at `/veranstaltung/<address>/` with a menu item that you can move under Website › Menu and pages, for example below “Events”. On the day after the end the menu item disappears by itself; the page stays as a look back unless you tick **Remove from the website after the event has ended** there.

## Tickets and admission

Every binding registration has **Tickets** as a PDF, one ticket per person with a QR code. The code contains no names, only a verified identifier. For free events the tickets come with the registration confirmation, otherwise with the payment confirmation; they are also in the members' area, behind the “view registration” link and, for the administration, with each registration under **Tickets**. On site, **Admission** opens the list of everyone registered with their payment status. With a hand scanner you scan the ticket into the **Ticket code** field; where the browser can read QR codes, **Scan with the camera** works too.

Without a ticket, tick the person off in the list with **Admit**. HUBIplan tells you if someone has already been admitted, the ticket belongs to another event, the person has cancelled or has not paid yet. **Undo** reverses an admission. Whoever may edit invoices sees **Take cash** for unpaid registrations: it opens the invoice, where you book the cash payment, with a signed receipt if you like (box office). In the HUBIplan app, admission is under Administration › Events with a camera scanner and box office; the list stays readable without a network.

For on site and afterwards: **Name badges (PDF)** prints ten badges per A4 page in business card format (85 × 54 mm) with event, name and club. **Certificates of attendance (PDF)** creates one page per person on your letterhead. Participants are those checked in at the entrance; if you did not use check-in, everyone registered counts. With the Qualifications module switched on, **Record qualification** adds the chosen record to all participating members after a course, dated the last day of the event and with the usual validity. Guests without membership are skipped and duplicates avoided.

## Group registration with the umbrella association

Group registration with the umbrella association: When an umbrella association sets up registration, it can switch on under **Group registration** that clubs register their members as a group. The clubs see the event in their calendar; whoever in the club may edit registrations and see members finds **Club group registration** there, picks members and tariff and registers them (binding).

The invoice goes to the club, not to the individual members. The club only sees its own registrations and can cancel people until the registration deadline. The club needs the Registrations module for this. Under Entries, **Group registrations with the umbrella association** lists all upcoming events of the umbrella association with group registration and how many members the club has registered for each.
