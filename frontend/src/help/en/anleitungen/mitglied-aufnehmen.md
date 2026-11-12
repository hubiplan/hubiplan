---
key: guide.member_admit
titel: Admit a new member
modul: members
rechte: [members.edit]
routen: [/mitglieder]
reihe: 10
stichworte: [admission, joining, new, join, create, organisation, company, supporting member]
---

Before you start: there is at least one membership type (Members › Setup › Membership types).

1. In the [member list](/mitglieder), click **Admit member**.
2. Enter surname, first name and date of birth and click **Next**. HUBIplan checks whether the
   person already exists, for example from another club. The date of birth is optional; without
   it, HUBIplan only looks for members of your own club with the same name, and age-based fee
   levels, birthdays and ages are left out for this person.
3. If there are **Possible matches**, choose the right person or **None of these – create a new person**.
4. Choose the **Membership type** and the **Joining date**. The membership number is
   optional: if you leave it empty, HUBIplan assigns the next free number (the highest existing
   number in the club plus 1, including former members; numbers with letters do not count).
5. Add contact details and address and click **Admit**. For a person who already exists, the
   existing shared contact details stay as they are; your entries only fill empty fields. You can
   change them afterwards in the member record.

![The “Admit member” form](bild:mitglieder-aufnehmen)

Required fields are marked “(required)”. If something is missing, “Please fill in this field.” appears below the field and the cursor moves to the first empty required field.

If sub-units cannot be loaded, a message offers **Reload**. You can retrieve the choices again without losing names or other details you have already entered.

Admission has two stages: **1. Person** and **2. Membership and contact**. After **Next**, keyboard focus moves to the new heading or **Possible matches**. **change** returns to the retained personal details. Optional sub-units form a named selection group; a group error is described and receives focus there.

![Second stage with membership, sub-units and contact details](bild:mitglieder-aufnehmen-details)

## An organisation as a member

A company, another club, a town or a public body can also be a member. In the first stage, under
**The member is**, choose **an organisation (company, association, public body …)**.
Instead of surname, first name and date of birth, fill in **Name of the organisation**,
optionally a **Name addition** (such as a branch) and the **Legal form (optional)**.
HUBIplan then checks whether an organisation with this name already exists. In the second stage
you can add the register, VAT ID and website; the address is the organisation's address.

Organisations have no age bands for fees: the amount of the membership type applies, for example
a separate type “Supporting member (company)”. Birthdays and the age and gender statistics leave
organisations out, and only a person can hold an office.
