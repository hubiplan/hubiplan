---
key: page.bookings
titel: Bookings and booking calendars
rechte: [bookings.view, bookings.edit, infrastructure.view, material.view]
routen: [/belegung]
stichworte: [Booking, Booking calendar, Reservation, Request, Approval, Set-up time, Hall]
---

Planning › **Bookings** shows when facilities and material with a booking calendar are in use. The week
view has one row per item. At the top you switch between **Week**, **Month** and **Year** and move
on with the buttons next to it. The month view shows every day of the month side by side (the full
text appears as a tooltip), the year view shows the number of booked days per month; click it to
open that month.

Switch on a booking calendar: On the detail page of a facility or a material item, the
managers switch on booking under **Booking calendar**. There you also decide whether bookings
need approval, how much set-up time stays free before and after, and how far ahead
people may book.

## In detail

Book: Choose **Book**, then the item, the purpose and the time. A booking can repeat
weekly, monthly or yearly. Instead of a time you can choose an event or a competition;
the booking then follows it when it is moved or cancelled. Booking a whole building also books
all of its areas.

## For members and guests

Booking for a member: Under **For a member (optional)** you look up a member (this needs the
permission to view members). You don't enter contact details again; they are in the member record.
The booking shows the name in Bookings, appears in the member record under **Bookings** and in the
member's members area. For guests without membership there is still
**External booking (optional)** with name, email and phone.

Charging rent: In an item's booking calendar you enter a rental price, per booking, per started
day or per hour. On a confirmed one-off booking for a member, **Create invoice** creates a draft
invoice to that member with the rental price as a suggestion. This also works if the member's
fee is otherwise paid through a unit's collective invoice. Finalise and send the draft under
Finance › Invoices like any other invoice; the booking then shows the invoice number. You need
the permission to edit invoices.

If you cancel a booking that has an invoice, the invoice remains; HUBIplan points this out
beforehand and at the booking. Delete a draft under Finance › Invoices, or cancel an issued
invoice there.

## Overlaps and approval

Overlaps: If the item, including set-up time, is already booked, HUBIplan refuses the
booking and shows the booked time. If a linked event later moves onto a booked time, the
booking is marked **check**.

Requests and approval: If an item needs approval, your booking starts as a request and does
not block anything yet. People with the permission “Book for others and approve bookings”, or with edit permission
on the item, see **Open requests** and approve or reject them. You can cancel your own request
or booking yourself.

Visibility: With **Only the managers see the purpose**, other members only see "Booked".
Cancel a single date of a series with **Cancel this date only**.

Lending material: For one-off bookings of material, the managers use **Confirm hand-out** in
the booking and later **Confirm return**. Only if you tick
**Record the item's condition on return** does HUBIplan change the item's condition and note; the change then appears in the
item's history.

Booking from a demand: If a material item with a booking calendar is assigned to an event, its
detail page shows **Book firmly**. This opens a booking for that event; for "This occurrence only"
exactly that date is booked.

On the website: Under **Booking calendar** you choose per item whether the “Bookings” section of the website shows nothing, only booked times or, for public bookings, also the purpose. Switch the section on under Website › Menu and pages.

Requests from the members' area: With **Members may send requests from the members' area** an
item appears in My area on the Bookings tile. Such requests always need approval. Whoever made a
request or booking receives an email when someone else confirms, rejects or cancels it.
