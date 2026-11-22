---
key: guide.api_access_create
titel: Give another program an API access
modul: api
rechte: [api.manage]
routen: [/einstellungen/api]
stichworte:
  [API, key, federation software, federation, interface, own website, data exchange, writing]
---

1. Open [Settings › API accesses](/einstellungen/api) and click **Create access**.
2. Enter a **Name**, ideally that of the program, and fill in **Recipient** and **Purpose**.
3. If the access should only see one sub-unit, choose it under **Applies to**.
4. Under **What the access may read**, tick only what the program really needs.
5. Check the date **Valid until** and click **Create access**.
6. Confirm with a two-factor code if HUBIplan asks for it.
7. Click **Copy key** and pass the key on to the recipient securely.

The key is shown on the page only now. If it gets lost, **Create new key** helps; the previous one then remains valid for seven more days. The recipient also needs the address of the interface, shown at the top of the page.

If the program should read members, honours, qualifications or the report to the association by name, you also choose the **Recipient (business partner)** and the **Legal basis** and confirm it. Create the recipient beforehand under [Administration › Business partners](/geschaeftspartner). If the program should learn about changes, enter an **Address for notifications**; like the key, the secret for it is shown on the page only once.

If the program should also write, for example create events or enter results, tick the area under **What the access may write**. What it writes is recorded in the change log; changes to members only arrive as a proposal.

If the menu item is missing, the module “API for other programs” is switched off under [Settings › Modules](/einstellungen/module) or your role lacks the additional right “Manage API accesses” ([Roles and permissions](/einstellungen/rollen)).
