---
key: page.music
titel: Music › Performances
modul: music
rechte: [music.view]
routen: [/musik]
stichworte: [Music, performance, staffing, guest, fee, settlement, programme]
---

Plan performances here: staffing, programme, guests and settlement. The other music items are in the sidebar: Overview, Availability, Musicians, Rehearsals and sheet music checkout, Sheet music library and Instrumentation templates. Changes to existing entries save automatically; create new entries with **Save**.

## Create a performance

Create an individual event in your own calendar, then select it under **Performances**. Add customer, meeting time and place, setup, uniform, formation and notes. Performance times and location remain in the calendar. Use individual events for recurring performances. Open **Performance tasks** to manage tasks through the existing task workspace.

The search field is named after the view, for example **Search performances** or **Search musicians**, and filters it, for example by name, instrument or performance. Add new items with the matching button, such as **New performance**; an empty view explains what belongs there and offers the same button. **Search sheet music** filters the current library view. Empty lists and searches without matches show a message. Performance cards group programme, instrumentation, settlement, tasks and calendar links; detail pages show the associated performance above the heading. Totals and programme durations appear in labelled summaries. Responses and availability conflicts use consistent text badges, including in the member area.

## Staffing and assignments

Record required player counts per instrument and part, then assign musicians with matching skills. Each musician can be assigned once per performance. The overview counts accepted and missing players per position.

Open **Plan instrumentation** for a performance, select an active template and review its positions. **Apply template** adds missing parts and increases required counts if needed. Other positions and existing assignments and responses are preserved. Resolve ambiguous duplicate positions first. **Save performance instrumentation as template** copies the required positions into a new template without musicians or responses. Template changes affect performances only when applied again.

Under **Batch assignment**, select multiple matching active members or guests. Choose one position for multi-instrumentalists; each musician profile is assigned only once. Pending and accepted assignments reserve places. Already assigned musicians and existing declines are not offered again; edit their existing assignment individually.

**Request selected musicians** creates pending assignments. If the selection exceeds available places, contains invalid references, lacks skills or has known availability conflicts, nothing from the request is saved. Retries create no duplicate assignments. Existing calendar permissions apply to performances. General exports include templates.

## Replacements

For a declined assignment, open **Find replacement** under **Plan instrumentation**. Conflict-free musicians with matching parts are offered, with matching primary instruments first. Select and request a replacement; the earlier decline remains. **Show all candidates** exits the filter; **Reset selection** discards an unsaved selection. General exports include absences.

## Responses and reminders

Members can accept or decline their assignments under **My area**. Calendar cancellations remain visible. Calendar access restrictions also apply to performance administration.

Active members with enabled member access receive neutral outbox notices for new performance assignments, changes to dates, meeting details, instrumentation positions or programmes, and cancellations. The background service checks every five minutes and combines intermediate changes. Messages contain only the member-area link. Existing assignments do not generate another initial invitation when the feature is introduced. Guests receive automatic notices only after an explicit guest invitation is sent.

For each performance, **Reminder days before (0 = off)** sets the reminder window for pending responses (0 to 30 days, default 3). It uses the earliest meeting, setup or performance time. Each current information version receives at most one reminder, no earlier than one day after an invitation or change. Accepted or declined assignments and past or cancelled performances are not reminded. Failed deliveries are retried; failed attempts remain visible in the outbox.

## Invite guests

For guests, open **Plan instrumentation** → **Manage guest invitation**, create a personal link and share it confidentially. Guests need no account and see only their own assignment, meeting details, setup, uniform, formation and programme. They can accept or decline; known conflicts prevent acceptance. Other musicians, contact information and settlements remain hidden. Links expire seven days after the performance, with a maximum lifetime of 180 days. **Revoke invitation link** blocks access immediately; **Create new invitation link** replaces the previous link. Changing the guest email address revokes existing links.

To send an invitation, enter the musician's **Email address for guest invitations** and explicitly choose **Send guest invitation**. This also enables change notices and reminders while access remains active. Creating or copying a link alone does not enable automatic email. Personal links are redacted in the outbox; reopen guest management to share them again. If delivery fails, retry or share the link confidentially.

## Musical programme

Open **Musical programme** on a performance. Add pieces and encores with an arrangement, and breaks with their own duration. A blank duration uses the arrangement duration; an explicit value overrides it. Edit, remove and move items up/down. Regular duration includes breaks; encore and total durations are shown separately. Zero indicates an unknown duration and is highlighted.

Preparation compares required instruments and parts against planned instrumentation and active musicians who accepted assignments. Names are compared without case sensitivity or surrounding whitespace; different instrument names remain distinct. Missing musicians, planned counts and missing copies in the chosen format are visible. Copies in the other format do not count. Repeated pieces need one set per format. Missing instrumentation is highlighted. Changes to stock and arrangement duration affect existing programmes.

For each performance, **Programme list as PDF** and **Parts list as PDF** complement the existing CSV exports. Printouts include performance, location, creation timestamp and page numbers. The programme lists order, breaks, encores and durations; the parts list shows format, available and missing copies, copies held by assigned musicians, missing musicians, storage locations and licence notes. Check current stock and usage rights before printing.

Download programme and part lists as CSV. Use **Sheet music preparation tasks** to create preparation tasks linked to the event in the existing task workspace. Programmes require music and calendar viewing permissions; editing requires music editing permission. General exports include the catalogue and programmes. Digital files remain in the existing document export.

## Performance settlement

Open **Performance settlement** from the performance. Music and calendar viewing permissions and the enabled cash book with finance viewing permission are required. Editing requires finance editing permission. Record the agreed fee, travel costs and additional services as gross amounts in EUR. With invoice editing permission, create a draft in the existing e-invoice editor. The customer and total gross amount must match the agreement. Enter net amounts, tax categories and invoice details explicitly, then validate, issue, send and manage receipts using the invoice workspace. Each performance links one customer invoice.

Record fees, allowances and documented expenses per assignment. Confirm attendance after the performance, then approve remuneration. Approved amounts are locked. Before payment, void approval and reopen the draft for corrections. Members see only their own approved remuneration in their personal area. Finance administrators handle guest remuneration.

Record payments with receipts as expenses in the cash book first. Search the booking text and link each matching booking in full. Each remuneration permits multiple partial payments up to the outstanding balance. Link other performance expenses in the same way. Each booking can be used once. Linking does not initiate a bank transfer.

Reverse incorrect payments in the cash book. The original link remains visible, while the outstanding balance increases and can be linked to a corrected payment. The overview distinguishes agreed and invoiced amounts, actual income and expenses and their cash result. Approved remuneration is shown separately and does not indicate a completed payment.

Use **Replace cancelled invoice** after fully cancelling the customer invoice. Then correct the agreement and create a replacement invoice. Previous invoices remain linked and traceable in the audit export.

General exports and financial audit exports include agreements, remuneration and booking links. Financial retention and anonymization include settlement notes.

## Fee templates and partial payouts

Under **Performance settlement** → **Musician remuneration**, finance editors can **Manage fee templates**. Templates contain fee and allowance amounts in EUR. Archiving prevents new use; existing remuneration retains its copied amounts.

For a batch settlement, select an active template and assignments without existing remuneration. **Select all without remuneration** selects assignments without confirming attendance. Confirm attendance separately for each musician. **Create remuneration drafts** creates drafts with expenses set to zero. Add actual expenses and check attendance individually, then approve after the performance as usual. Invalid selections are rejected together. Existing remuneration is never overwritten.

You can assign multiple recorded payouts from Finance to an approved remuneration claim. Each booking is used fully and only once and must not exceed the outstanding amount. **Partially paid**, **Paid** and **Outstanding remuneration** also show the current balance in the member's own area. An active partial payment prevents approval reversal. Reversing the booking in Finance increases the outstanding amount again. Assigning a booking does not initiate a bank transfer.

## Offers and confirmations

Open **Offers and confirmations** from a performance settlement. First complete the customer address and gross amounts. Check expiry date and agreements before issuing the offer PDF. Issued PDFs and checksums preserve their original content. A new offer supersedes a pending offer. Invoice numbering is separate. Issuing does not send mail. Record the customer's actual acceptance with evidence, then issue an order confirmation. Repeated issuance returns the same confirmation. Firm confirmation locks agreed amounts and performance details. Record cancellation with a reason before making changes and issuing a new offer. Original PDFs remain as evidence after cancellation. Calendar changes do not alter archived documents. These documents are not invoices. Finance readers can inspect documents; issuance and status changes require finance and music edit rights. PDFs use the existing letterhead.

## Who may do what?

The platform enables Music per organization. Roles need music viewing or editing permission. Performances also require calendar viewing permission.
