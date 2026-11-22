# Changes to HUBIplan

Changes per release, newest first. Versions are named `YYYY.MM.N` (year, month, running
number within the month), see [docs/releases.md](docs/releases.md) (German).
Deutsch: [CHANGELOG.md](CHANGELOG.md).

<!-- Neue Versionen hier einfügen (scripts/release.sh) -->

## 2026.11.1 (2026-11-22)

The second release sums up almost three weeks of development since 2026.11.0 (562 pull requests).
The main changes are listed here by area; every single change is described in its pull request on
GitHub.

### New

- **New interface:** seven areas with a common page header (path, title, main action top right),
  quick search (Ctrl+K), a start page that shows what needs doing first, and freely chosen quick
  actions and tiles. Members who also help run the club switch between "My club" and the
  administration at the top. On phones the most important areas sit in a bar at the bottom;
  members get a dark mode.
- **Tasks:** personal and shared tasks with assignees, due dates, reminders by email and push,
  attachments, recurring series and tasks across several units.
- **Registrations with fees:** price tiers, waiting list, cancellation stages, extras,
  registration for non-members, tickets with QR code, admission and box office by phone, name
  badges and certificates of attendance, bulk registration through the umbrella association and
  an event page on the website.
- **More modules:** polls and opinion surveys, training with attendance and shooting record,
  group orders, notice board, deadline calendar, qualifications with expiry date, equipment and
  facilities with booking calendar, rental price and invoice, volunteer shifts, chronicle as its
  own module.
- **Music clubs:** musicians and guests, performances with line-ups, quotes and settlement, sheet
  music archive with parts, folders and MusicXML, rehearsals with programmes, absences.
- **Members:** organisations as members (with contact persons, a vote at meetings, business
  direct debit and graded fees), households, separate billing address, academic title, automatic
  membership number, online membership application, cancellation in the member area, membership
  card in Google Wallet and Apple Wallet, reference-date statistics as a report file,
  congratulations on birthdays and anniversaries.
- **Finance:** fetch transactions directly from the bank (FinTS), business partners, incoming
  invoices with an invoice mailbox, XRechnung for services and for members with a routing ID,
  cancellation invoices, split bookings, volunteer allowances, asset register, cash audit, artists'
  social insurance levy, statement of assets, reserves, budget, tax report, simplified donation
  receipt, earmarked donations, expense reimbursement, reduced fees with proof, work hours with
  substitute fee, pro-rata fee on joining.
- **Club website:** start page and text pages built from sections with many new section types
  (including countdown, FAQ, partners), gallery with albums, header images, title photo as a stage,
  fine-tuning by page area, new fonts, changes as drafts with versions, image credits, booking
  display.
- **Events:** places with rooms, attachments and documents on events, circulars to everyone
  invited, create events from Outlook, Thunderbird or the phone, board calendar feed, sync with
  the Nextcloud calendar.
- **Meetings:** attendance by QR code, sub-items in the agenda, take over an election result
  directly into the office.
- **Connections:** sign in with a passkey (web and apps), AI assistants (e.g. Claude) with sign-in
  via `/api/mcp/` for help, website, branding and chronicle, a public API for other programs with
  read and write access, deeper Nextcloud integration (groups, files, video room) and data
  protection tools under Administration › GDPR.
- **Apps:** board members decide on applications and booking requests and run meetings in the
  app; look up business partners; range access for range officers.
- **Help:** news for every version under Help › What's new, many new guides and learning aids,
  "Did this help?" under every help text.
- **Self-hosting:** own name, colours, logo and icon for the installation, own addresses per club,
  notice of new releases and updating from the platform administration.

### Improved

- Member record, finance, the event dialog, monthly calendar and competitions are laid out more
  clearly; buttons, fields and confirmations are consistent everywhere.
- Meeting details and many dialogs save automatically.
- Member list, member search, calendar and calendar feeds are much faster for large clubs; HUBIplan
  loads faster when first opened.
- Modules can be enabled per club and sub-unit; disabled modules disappear from menus, roles and
  settings.
- Date of birth is optional. Many small improvements from the usability review.

### Fixed

- The English interface is translated more completely.
- Background jobs such as sending mail start reliably; large attachments also arrive through the
  federation.
- Data protection: the Art. 15 GDPR access report is complete, objection to public naming applies
  everywhere, deletion and anonymisation also cover SEPA mandates and Nextcloud accounts.
- Further fixes on the start page, tasks, umbrella association export and calendar, financial
  reports and display.

### Security

- Every administrative permission requires two-factor sign-in; sensitive steps such as full
  exports, assigning roles or permanent deletion require a fresh code. Notification mails on
  changes to sign-in and password.
- Names and further personal data are additionally stored encrypted; data keys can be rotated per
  club.
- Locked bookings, receipts and cash locks are also protected in the database; cash auditors get a
  weekly checksum.
- Secret ballots and anonymous polls are stored so that answers cannot be linked to anyone.
- Sign-in lockouts only affect the attacker; protection against takeover through a second email
  address and against intercepted app codes; AI assistants are more tightly limited.
- Uploaded files, imports and exports are hardened against manipulated content; if the virus
  scanner is unavailable, files are held instead of rejected.

### For operators

- Updates without database changes run without interruption. Self-update from the platform
  administration (off by default); the daily release notice can be turned off with
  `HUBIPLAN_UPDATE_CHECK=0`. Release tags are signed.
- Daily background jobs run at fixed night times, with an email if one is missed.
- The technical admin area `/admin/` is off by default (`DJANGO_ADMIN_ENABLED`).
- Behind your own proxy, `HUBIPLAN_PROXY_HOSTS` must be set.
- Clubs are deleted in two stages (first suspended, permanently at the earliest 30 days later).
- The backup reads the database with its own read-only account; restic can also back up the
  mailboxes. Deployment checks that the source code is public.
- The apps check the minimum version separately for Android and iOS.

Database migrations: 298


## 2026.11.0 (2026-11-03)

First release of HUBIplan. It sums up the state after publication as free software (AGPL);
from here on, each release lists its changes in this file.

### New

- Membership management with memberships, membership types, custom fields, honours,
  anniversaries, titles and offices with history, membership card, import and export
- Roles with freely chosen permissions per unit (areas with “no access”, “read”, “edit”),
  “view as role”, two-factor login, login to the club's Nextcloud
- Fees, invoices, SEPA direct debit, GoBD-compliant cash book with bank statements and
  digital receipts, donation receipts, annual closing
- Events with RSVPs, calendar subscription and external calendars (Vereinsplaner, iCal)
- Competitions and entries, range mode, target catalogue, live tables
- Circulars, mailing lists, letter templates, document storage, statutes
- Club website content with a timeline chronicle, design packages and preview
- API for the Android app, interface in German and English, help and learning aids
- The running version is shown on the “Licences” page

### For operators

- Deployment with a way back (`deploy/zurueck.sh`), lock against parallel runs and a
  rollout log; versions and releases see `docs/releases.md`
- Data encrypted per club, daily backup with restore test

