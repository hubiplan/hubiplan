---
key: page.music
titel: Music
bereich: termine
modul: music
rechte: [music.view]
routen: [/musik]
stichworte: [Musik, Instrument, Auftritt, Besetzung]
---

# Music and performances

**Performance overview** combines staffing, pending responses, known conflicts,
sheet music requirements and permitted settlement issues. Select a period and choose
**Update overview** when needed. Each issue links to staffing, the programme or the
performance settlement. “Prepared” refers only to information you can access; it does not
confirm attendance. Missing planning details remain open. Finance issues require
cashbook read access. Cancelled performances are marked separately. Each page shows
twelve performances.

The platform enables Music per organization. Roles need music viewing or editing permission. Performances also require calendar viewing permission.

Section navigation remains visible on every music page: **Performances**, **Musicians**, **Sheet music library**, **Rehearsals and sheet music checkout**, **Availability** and **Instrumentation templates**. Under **Performances**, switch between performances, required instrumentation and assignments; under **Musicians**, switch between profiles and instrumental skills. The active section is marked. Navigation and form fields stack on smaller screens.

Use **Search entries** to filter the current performance or musician view, for example by name, instrument or performance. **Search sheet music** filters the current library view. Empty lists and searches without matches show a message. Performance cards group programme, instrumentation, settlement, tasks and calendar links; detail pages show the associated performance above the heading. Totals and programme durations appear in labelled summaries. Responses and availability conflicts use consistent text badges, including in the member area.

Create a musician from an existing member or enter a guest name and contact details. The member record links to the musician workspace. Record instruments and sections or parts under **Instrumental skills**, marking the main instrument. Deactivate guests when no longer needed.

Create an individual event in your own calendar, then select it under **Performances**. Add customer, meeting time and place, setup, uniform, formation and notes. Performance times and location remain in the calendar. Use individual events for recurring performances. Open **Performance tasks** to manage tasks through the existing task workspace.

Record required player counts per instrument and part, then assign musicians with matching skills. Each musician can be assigned once per performance. The overview counts accepted and missing players per position.

Members can accept or decline their assignments under **My area**. Calendar cancellations remain visible. Calendar access restrictions also apply to performance administration.

For guests, open **Plan instrumentation** → **Manage guest invitation**, create a personal link and share it confidentially. Guests need no account and see only their own assignment, meeting details, setup, uniform, formation and programme. They can accept or decline; known conflicts prevent acceptance. Other musicians, contact information and settlements remain hidden. Links expire seven days after the performance, with a maximum lifetime of 180 days. **Revoke invitation link** blocks access immediately; **Create new invitation link** replaces the previous link. Changing the guest email address revokes existing links.

To send an invitation, enter the musician's **Email address for guest invitations** and explicitly choose **Send guest invitation**. This also enables change notices and reminders while access remains active. Creating or copying a link alone does not enable automatic email. Personal links are redacted in the outbox; reopen guest management to share them again. If delivery fails, retry or share the link confidentially.

Active members with enabled member access receive neutral outbox notices for new performance assignments, changes to dates, meeting details, instrumentation positions or programmes, and cancellations. The background service checks every five minutes and combines intermediate changes. Messages contain only the member-area link. Existing assignments do not generate another initial invitation when the feature is introduced. Guests receive automatic notices only after an explicit guest invitation is sent.

For each performance, **Reminder days before (0 = off)** sets the reminder window for pending responses (0 to 30 days, default 3). It uses the earliest meeting, setup or performance time. Each current information version receives at most one reminder, no earlier than one day after an invitation or change. Accepted or declined assignments and past or cancelled performances are not reminded. Failed deliveries are retried; failed attempts remain visible in the outbox.

## Fee templates and partial payouts

Under **Performance settlement** → **Musician remuneration**, finance editors can **Manage fee templates**. Templates contain fee and allowance amounts in EUR. Archiving prevents new use; existing remuneration retains its copied amounts.

For a batch settlement, select an active template and assignments without existing remuneration. **Select all without remuneration** selects assignments without confirming attendance. Confirm attendance separately for each musician. **Create remuneration drafts** creates drafts with expenses set to zero. Add actual expenses and check attendance individually, then approve after the performance as usual. Invalid selections are rejected together. Existing remuneration is never overwritten.

You can assign multiple recorded payouts from Finance to an approved remuneration claim. Each booking is used fully and only once and must not exceed the outstanding amount. **Partially paid**, **Paid** and **Outstanding remuneration** also show the current balance in the member's own area. An active partial payment prevents approval reversal. Reversing the booking in Finance increases the outstanding amount again. Assigning a booking does not initiate a bank transfer.

## Instrumentation templates and batch assignment

Under **Instrumentation templates**, use **Create template** to store instruments, parts and required player counts. Each part may appear only once. Clear **Active** to archive a template. Editing requires music editing permission; read-only users can view templates.

Open **Plan instrumentation** for a performance, select an active template and review its positions. **Apply template** adds missing parts and increases required counts if needed. Other positions and existing assignments and responses are preserved. Resolve ambiguous duplicate positions first. **Save performance instrumentation as template** copies the required positions into a new template without musicians or responses. Template changes affect performances only when applied again.

Under **Batch assignment**, select multiple matching active members or guests. Choose one position for multi-instrumentalists; each musician profile is assigned only once. Pending and accepted assignments reserve places. Already assigned musicians and existing declines are not offered again; edit their existing assignment individually.

**Request selected musicians** creates pending assignments. If the selection exceeds available places, contains invalid references, lacks skills or has known availability conflicts, nothing from the request is saved. Retries create no duplicate assignments. Existing calendar permissions apply to performances. General exports include templates.

## Availability and replacements

Under **Availability**, manage absences for active members and guests. Members can manage **My absences** in their own area. Only start and end are recorded, without reasons. Adjacent periods do not overlap. Other known performances including meeting and setup time, rehearsal series and accepted calendar events in the same association are considered. Individual declines and moved occurrences take effect immediately. Other associations and private calendars without an association response are not checked; plan travel and buffer time yourself.

Planning shows **Absent**, **Scheduling conflict**, **Declined this event** or **No known conflict**, without revealing private calendar content. Assignment and acceptance check again before saving. No known conflict does not constitute acceptance. Later changes highlight conflicts for existing assignments without automatically changing responses or remuneration. Decline the assignment separately if needed.

For a declined assignment, open **Find replacement** under **Plan instrumentation**. Conflict-free musicians with matching parts are offered, with matching primary instruments first. Select and request a replacement; the earlier decline remains. **Show all candidates** exits the filter; **Reset selection** discards an unsaved selection. General exports include absences.

## Performance settlement

Open **Performance settlement** from the performance. Music and calendar viewing permissions and the enabled cash book with finance viewing permission are required. Editing requires finance editing permission. Record the agreed fee, travel costs and additional services as gross amounts in EUR. With invoice editing permission, create a draft in the existing e-invoice editor. The customer and total gross amount must match the agreement. Enter net amounts, tax categories and invoice details explicitly, then validate, issue, send and manage receipts using the invoice workspace. Each performance links one customer invoice.

Record fees, allowances and documented expenses per assignment. Confirm attendance after the performance, then approve remuneration. Approved amounts are locked. Before payment, void approval and reopen the draft for corrections. Members see only their own approved remuneration in their personal area. Finance administrators handle guest remuneration.

Record payments with receipts as expenses in the cash book first. Search the booking text and link each matching booking in full. Each remuneration permits multiple partial payments up to the outstanding balance. Link other performance expenses in the same way. Each booking can be used once. Linking does not initiate a bank transfer.

Reverse incorrect payments in the cash book. The original link remains visible, while the outstanding balance increases and can be linked to a corrected payment. The overview distinguishes agreed and invoiced amounts, actual income and expenses and their cash result. Approved remuneration is shown separately and does not indicate a completed payment.

General exports and financial audit exports include agreements, remuneration and booking links. Financial retention and anonymization include settlement notes.

Use **Replace cancelled invoice** after fully cancelling the customer invoice. Then correct the agreement and create a replacement invoice. Previous invoices remain linked and traceable in the audit export.

## Sheet music and programmes

Use **Import sheet music catalogue** to select a UTF-8 CSV up to 2 MB with at most 1000 data rows. The **Download CSV template** lists all columns; `title` and `arrangement` are required. Use semicolons or commas as separators. Each row describes an arrangement and optionally stock for an instrumental part. Without an instrument, only the arrangement is created. **Preview import** shows new pieces, arrangements, stock and errors without saving anything. **Import reviewed sheet music catalogue** explicitly imports the reviewed data together. Identical entries are skipped; conflicting details, changed stock counts or ambiguous existing entries must be resolved first. Existing details and archived arrangements are not overwritten or reactivated. Create a new preview if the file or catalogue changes; previews expire after 30 minutes. Add digital sheet music through the existing document library.

For each performance, **Programme list as PDF** and **Parts list as PDF** complement the existing CSV exports. Printouts include performance, location, creation timestamp and page numbers. The programme lists order, breaks, encores and durations; the parts list shows format, available and missing copies, copies held by assigned musicians, missing musicians, storage locations and licence notes. Check current stock and usage rights before printing.

Open **Music** → **Sheet music library**. Create pieces with composers, then editions/arrangements with arrangers, publishers, duration in seconds, difficulty, instrumentation and licence notes. Archive unused arrangements. Record required musicians, copy counts, storage locations and concert or march book format for each instrument and part. Record full scores separately. Stocks at multiple locations are added together for the same part; the highest player requirement applies.

Upload digital files in the existing document library, then link them to an arrangement and optionally a part under **Sheet music documents**. Document viewing permission is also required to link and open files. Access changes and deletions apply immediately. Music permissions do not extend document access. Record licence and usage notes; a stock count or file does not grant copying or performance rights.

Open **Musical programme** on a performance. Add pieces and encores with an arrangement, and breaks with their own duration. A blank duration uses the arrangement duration; an explicit value overrides it. Edit, remove and move items up/down. Regular duration includes breaks; encore and total durations are shown separately. Zero indicates an unknown duration and is highlighted.

Preparation compares required instruments and parts against planned instrumentation and active musicians who accepted assignments. Names are compared without case sensitivity or surrounding whitespace; different instrument names remain distinct. Missing musicians, planned counts and missing copies in the chosen format are visible. Copies in the other format do not count. Repeated pieces need one set per format. Missing instrumentation is highlighted. Changes to stock and arrangement duration affect existing programmes.

Download programme and part lists as CSV. Use **Sheet music preparation tasks** to create preparation tasks linked to the event in the existing task workspace. Programmes require music and calendar viewing permissions; editing requires music editing permission. General exports include the catalogue and programmes. Digital files remain in the existing document export.

## Instruments and uniforms

When the inventory module and inventory viewing permission are also enabled, **Instruments and uniforms** appears. Editing requires both music and inventory editing permissions. **Link inventory item as music equipment** selects an existing inventory item; create items and maintain photos, documents and tasks in inventory management. Inventory number and condition remain shared. Use **Edit equipment details** for type, instrument, size/specification and the next maintenance date.

**Issue equipment** assigns an item to an active musician with a return deadline and handover note. Issuing equipment to members also requires member viewing permission. The inventory location changes to that member. For guests, the location is marked for review with a reference to the music issue; the guest assignment appears in Music. Items already issued, defective or retired cannot be issued again. Overdue returns are marked.

**Record equipment return** confirms condition and destination: explicitly restore the previous storage location or enter a complete new address. Inaccessible member locations must be replaced with a valid destination. **Record maintenance** saves completed maintenance with date, condition, note and next due date. Schedule planned maintenance in equipment details. The last 100 issues and maintenance entries are displayed; general exports retain all records. Correct issues and returns through these workflows rather than Undo in inventory history. An outstanding issue prevents deletion. The inventory record links back to music equipment when music viewing permission is available.

## Rehearsals and personal sheet music

Open **Rehearsals and sheet music checkout** and link events or series from your own calendar. Dates, location, recurrence and cancellations remain in the existing calendar. Rehearsal focus and pieces form the shared series template. Assign musicians and deactivate assignments no longer required. Administrators record guest responses.

Under **Upcoming rehearsals**, open **Edit rehearsal programme** for an occurrence. **This occurrence only** saves its own focus and pieces, including an empty programme. **Entire series** loads and changes the shared template; occurrences with their own programmes keep their contents. **Use series programme** removes the override and inherits the current template again. Rehearsal planning and rehearsal pieces continue to edit the template. Moved occurrences keep their programmes. After a recurrence rule change, programmes without a matching original start need to be planned again. Programme changes preserve attendance responses.

The overview covers the past 14 days and next 90 days. Each response belongs to the original occurrence start from the calendar rule, including moved occurrences. Changing the series rule requires new responses. Cancelled or started rehearsals cannot be answered. Missing responses are visible.

Current members with an active musician profile see their own rehearsals and performances with their effective programmes and focus under **My area**. **Sheet music for this rehearsal** shows matching permitted files. Downloads still require the document library’s member permissions and a matching part or skill. Removed pieces no longer grant access unless another own event needs them. Rehearsals use the displayed past 14 and next 90 days; cancelled rehearsals and declined invitations grant no sheet music access. Restricted, deleted and unrelated files remain inaccessible.

Record musician, part, quantity and return date for checkouts. Each checkout reduces available stock. Partial returns are recorded with timestamps. Outstanding checkouts prevent reducing or repurposing stock. Overdue returns are highlighted; members see their own outstanding quantities. Preparation distinguishes available copies from copies already held by assigned musicians.

New rehearsal assignments and upcoming pending responses generate neutral notices through the existing outbox. The hourly job reminds once per occurrence within the configured number of days; 0 disables reminders. Notices link to the member area and contain no sheet music attachments or confidential event details. Guests without member access do not receive these notices. Preparation tasks and other calendar communication remain in the existing task/calendar workspace.

General exports include rehearsal, response and checkout data. The additive migration includes tables, RLS and quantity constraints; export the new history before rolling back.

After an inventory item with closed issues is deleted, the existing 30-day trash period applies; its music links are then removed. Items with an outstanding issue are excluded from permanent cleanup.

## Batch payouts

In **Batch payouts**, select approved outstanding remuneration, a bank account
and an execution date. Check each holder, IBAN and optional BIC. Saving a run for
review reserves claims and freezes amounts and recipient details.
Download the SEPA file (pain.001.001.09, EUR), check it and approve it at your bank.
Repeated downloads contain the same instruction; do not submit the file twice.
Export does not execute transfers or mark claims paid. The file requests individual
bank entries. Assign each actual expense in the performance settlement; bank account
and amount must match. Reversed bookings reopen reconciliation.
Cancelling a run releases claims; submitted transfers must also be stopped at the bank.
Finance read access permits inspection; edit access is required to prepare, export or cancel.
