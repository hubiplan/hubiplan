---
key: page.orders
titel: Orders
modul: orders
rechte: [orders.view, orders.edit]
routen: [/bestellungen]
stichworte:
  [
    Order,
    Group order,
    Club clothing,
    Commemorative booklet,
    Uniform,
    Sizes,
    Size survey,
    Supplier,
    Hand-out,
  ]
---

Under **Orders** you collect members' orders, for example for club clothing, a commemorative
booklet or uniform items. Members order in the member area or in the app until the deadline and
can change or withdraw their order until then. You see the totals per item and size for the
order with your supplier.

## Creating a group order

With **New group order** you enter a title, a deadline and, if you like, a description. Under
**Who may order?** you choose all members or only one unit. Each item has:

- **Price in euros (optional)**: empty means no price. This turns it into a plain survey, for example of
  sizes for new jackets.
- **Sizes or variants (optional)**, separated by commas, such as “S, M, L, XL”, and a heading for
  them such as “Size”.
- **At most per member (optional)** and **At most in total (optional)**, for example when there are only 50 booklets.

**The club pays** hides the prices from members; then no invoices are created. With **Approve**
members see the group order; a push notification to the apps is optional.

## After the deadline

After the deadline members can no longer order. You can still enter, change or delete orders,
for example from a paper list, with **Enter order**. **Close now** closes early, **Reopen** opens
again as long as the deadline has not passed.

**Totals for the supplier** shows the quantities per item and size. **As Excel** downloads totals
and orders. When handing out, tick **handed out** for each order.

## Invoices (optional)

With a price and the invoicing right, **Create invoices** creates an invoice to the member for
every order without one. Members with a direct debit mandate appear in the next direct debit
run, the others pay by bank transfer. The invoices are under Finance › Invoices and in the member
area. An order with an invoice can only be changed after cancelling the invoice.

## Rights and clean-up

The **Orders** right under Settings › Roles controls viewing and editing. Roles with invoices,
material or registrations have it from the start. The module can be switched on and off under
Settings › Modules. Two years after the deadline HUBIplan deletes the group order and its orders;
invoices stay in the finances.
