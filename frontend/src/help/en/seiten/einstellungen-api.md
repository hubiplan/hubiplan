---
key: page.settings_api
titel: Settings › API accesses
modul: api
rechte: [api.manage]
routen: [/einstellungen/api]
stichworte:
  [API, interface, key, federation software, federation, other programs, data exchange, OpenAPI]
---

With an API access another program reads data of your unit, for example your umbrella association's software, a website of your own or a display board. Each access has its own key, may only read what you tick and expires by itself.

These accesses never provide names, addresses or bank details of individual members, and an access cannot change anything. Create a separate access for each program; then one can be deleted without disturbing the others.

The page only exists if the module “API for other programs” is switched on and your role has the additional right “Manage API accesses”. No role receives this right automatically.

## What an access may read

- Unit: name, address, contact, logo and the sub-units.
- Events: events with the visibility “public”, optionally also those for members. Board-only events and replies are never included.
- Member numbers: counts on a reference date by age, gender and sub-unit, no persons.
- Board and offices: roles with their functional address; names only if they appear on your public website.
- Results, posts, documents: only what your website publishes.

An area only appears if its module is switched on. With **Applies to** you restrict an access to one sub-unit; it then only sees that unit's data.

## Key and security

The key is shown on the page exactly once: after creating the access and after **Create new key**. HUBIplan does not store it in readable form. Pass it on securely, not by unencrypted email. For both, HUBIplan asks for a fresh two-factor code.

After **Create new key** the previous key remains valid for seven more days, so the other program can be switched over without an outage. If a key has fallen into the wrong hands, delete the access: it stops working immediately.

Every access expires after one year at the latest; 30 days before, everyone with the right receives an email. Use **Edit** to extend it. If an access is not used for 90 days, HUBIplan switches it off; **Switch on again** puts it back into operation.

Under **Allowed addresses (optional)** you allow requests only from certain IP addresses. **Callable from other websites** is meant for data that is public anyway, because the key is then visible in the website's source code; it is therefore not possible together with member events or member numbers.

Creating, changing, key changes and deleting are recorded in the change log. Each access allows 600 requests per hour.

## For developers

The address of the interface and its description (OpenAPI) are shown at the top of the page. The key is sent as `Authorization: Bearer hpk_…`. Errors are returned as `application/problem+json` with a fixed `code`.
