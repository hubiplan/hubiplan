---
key: page.settings_api
titel: Settings › API accesses
modul: api
rechte: [api.manage]
routen: [/einstellungen/api]
stichworte:
  [
    API,
    interface,
    key,
    federation software,
    federation,
    other programs,
    data exchange,
    OpenAPI,
    personal data,
    legal basis,
    data processing,
    report to the association,
    webhook,
    notification,
    writing,
    scoring software,
    admission,
    attendance,
  ]
---

With an API access another program reads data of your unit, for example your umbrella association's software, a website of your own or a display board. Each access has its own key, may only do what you tick and expires by itself. If you wish, an access may also write, for example create events or enter results from scoring software.

An access only releases names, addresses and other personal data if you name the recipient and confirm the legal basis. Bank details are never included. An access can only change something if you give it a writing area, and even then only little, see below. Create a separate access for each program; then one can be deleted without disturbing the others.

The page only exists if the module “API for other programs” is switched on and your role has the additional right “Manage API accesses”. No role receives this right automatically.

## What an access may read

- Unit: name, address, contact, logo and the sub-units.
- Events: events with the visibility “public”, optionally also those for members. Board-only events and replies are never included.
- Member numbers: counts on a reference date by age, gender and sub-unit, no persons.
- Board and offices: roles with their functional address; names only if they appear on your public website.
- Results, posts, documents: only what your website publishes.

For clubs there are also the areas with personal data, see the next section.

An area only appears if its module is switched on. With **Applies to** you restrict an access to one sub-unit; it then only sees that unit's data.

## Personal data

These areas carry the mark “Personal data” and only exist for clubs:

- Report to the association: reported members on the reference date. Under **Report to the association** you choose “numbers only” (counts by active, passive and month of birth) or “by name” (plus name, date of birth, association number, member type and joining date).
- Members: always name, title, gender, date of birth and member number. Contact and address, membership and sub-units are only added if you tick them.
- Honours and qualifications: with the name of the person and the period. Qualifications for which only the inspection is recorded, such as a certificate of good conduct, are never released.

Bank details, notes, photos, custom fields and members whose data has been deleted after the retention period are never included. With **Current members only** and **Adults only** you restrict the access further.

For personal data HUBIplan requires three things:

- **Recipient (business partner)**: who receives the data. Create it beforehand under Administration › Business partners.
- **Legal basis**: processing on behalf if the recipient only works on your instructions, for example a service provider with a contract under Art. 28 GDPR. Transfer if the recipient decides about the data itself, for example the umbrella association under its statutes.
- The confirmation that the contract or the legal basis exists. It applies to exactly this recipient; if you choose another one, HUBIplan asks again.

With processing on behalf, the business partner receives the role processor and is therefore listed in the register under [Data protection tools](/dsgvo). Everyone with the right receives an email as soon as an access releases personal data. HUBIplan does not replace legal advice: the board decides whether passing the data on is permitted.

Every retrieval of personal data is logged for 90 days. The list shows for each access how many records were retrieved and when last.

## What an access may write

Writing areas are listed separately in the form under “What the access may write” and are never preselected. Only uncritical data is written, or a proposal or draft that someone on your side accepts. No access deletes anything, sends anything or writes to the cash book, invoices, roles or settings.

- Create and change events: single events, including cancelling them. An access can only change events it created itself, and never board-only events. It does not send invitations.
- Deliver competition results: values from scoring software into running competitions. The access creates missing starters, guests by name. Finished competitions accept nothing more.
- Enter training and attendance: create training sessions and record who was there, only for the sessions the access created itself.
- Propose changes to members: changed names and contact details arrive as a change notice. Only what you accept takes effect.
- Check membership cards: for a card code only the answer whether it is valid and the type of membership comes back, no name. Intended for admission or a locking system.
- Deliver circulars as drafts: subject and text are stored as a draft under circulars. You choose the recipients and send it yourselves.

Attendance, proposals for members and the card check are areas with personal data and require recipient and legal basis. For attendance and proposals, “Read members” is added, because the other program has to know the members.

What an access writes is recorded in the change log with “API access” and its name instead of a person. The list shows for each access how often it has written and when last. Everyone with the right receives an email as soon as an access may write.

## Notify on changes

If you enter an **Address for notifications**, HUBIplan tells the other program when a member is admitted or changed, leaves, or an event changes. The message only names the kind of change and an identifier, never content; the program then fetches the data with its key.

When you first save, HUBIplan shows a secret once. The other program uses it to check that the message really comes from HUBIplan. **Create new secret** replaces it, **Send test message** checks the connection.

If the address cannot be reached, HUBIplan tries again for up to three days. After seven days without success the notifications are paused and everyone with the right receives an email; **Switch notifications on again** puts them back into operation. The access itself remains valid.

## Key and security

The key is shown on the page exactly once: after creating the access and after **Create new key**. HUBIplan does not store it in readable form. Pass it on securely, not by unencrypted email. For both, HUBIplan asks for a fresh two-factor code, and likewise when an access newly releases personal data, may newly write or receives a different address for notifications.

After **Create new key** the previous key remains valid for seven more days, so the other program can be switched over without an outage. If a key has fallen into the wrong hands, delete the access: it stops working immediately.

Every access expires after one year at the latest; 30 days before, everyone with the right receives an email. Use **Edit** to extend it. If an access is not used for 90 days, HUBIplan switches it off; **Switch on again** puts it back into operation.

Under **Allowed addresses (optional)** you allow requests only from certain IP addresses. **Callable from other websites** is meant for data that is public anyway, because the key is then visible in the website's source code; it is therefore not possible together with member events, member numbers, personal data or writing areas.

Creating, changing, key changes and deleting are recorded in the change log. Each access allows 600 requests per hour, of which at most 60 may write.

## For developers

The address of the interface is shown at the top of the page, next to three links: “Read description” opens a readable overview of all calls, “Open OpenAPI description” the file for your own tools and “Guide for developers” the detailed guide on GitHub. The description and the file need no sign-in, so you can pass the links on to the developer of the other program. The key is sent as `Authorization: Bearer hpk_…`. Errors are returned as `application/problem+json` with a fixed `code`. When writing, the `Idempotency-Key` header prevents a repeated request from creating something twice; with `external_id` the other program gives a record its own identifier.
