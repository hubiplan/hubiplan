# Changes to HUBIplan

Changes per release, newest first. Versions are named `YYYY.MM.N` (year, month, running
number within the month), see [docs/releases.md](docs/releases.md) (German).
Deutsch: [CHANGELOG.md](CHANGELOG.md).

<!-- Neue Versionen hier einfügen (scripts/release.sh) -->

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

