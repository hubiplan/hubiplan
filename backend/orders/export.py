"""Sammelbestellung als Excel: Summen je Artikel und Auswahl (für den Lieferanten) und die
einzelnen Bestellungen (für die Ausgabe)."""

from __future__ import annotations

import io

from django.utils.translation import gettext as _
from openpyxl import Workbook
from openpyxl.styles import Font

from core.i18n import language_of_org
from exchange.export import safe_cell

from . import services
from .models import MemberOrder, OrderCampaign


def _cells(row):
    return [safe_cell(v) if isinstance(v, str) else v for v in row]


def xlsx(campaign: OrderCampaign) -> bytes:
    with language_of_org(campaign.organization):
        return _xlsx(campaign)


def _xlsx(campaign: OrderCampaign) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = _("Summen")[:31]
    ws.append([safe_cell(campaign.title)])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append([])
    ws.append([_("Artikel"), _("Auswahl"), _("Menge"), _("Preis"), _("Betrag")])
    for cell in ws[3]:
        cell.font = Font(bold=True)
    prices = {a.pk: a.price for a in campaign.articles.all()}
    for row in services.sums(campaign):
        price = prices.get(row["article"])
        for v in row["variants"]:
            amount = price * v["quantity"] if price is not None else None
            ws.append(_cells([row["name"], v["variant"], v["quantity"], price, amount]))
    for col, width in zip("ABCDE", (30, 16, 8, 10, 12), strict=False):
        ws.column_dimensions[col].width = width

    ws2 = wb.create_sheet(_("Bestellungen")[:31])
    ws2.append(
        [
            _("Name"),
            _("Mitgliedsnummer"),
            _("Artikel"),
            _("Auswahl"),
            _("Menge"),
            _("Betrag"),
            _("Bemerkung"),
            _("Rechnung"),
            _("Ausgegeben"),
        ]
    )
    for cell in ws2[1]:
        cell.font = Font(bold=True)
    orders = (
        MemberOrder.objects.filter(campaign=campaign)
        .select_related("membership__person", "invoice")
        .prefetch_related("lines__article")
    )
    rows = sorted(
        orders, key=lambda o: (o.membership.person.last_name, o.membership.person.first_name)
    )
    for order in rows:
        data = services.order_data(order, admin=True)
        invoice = data["invoice"]["number"] if data["invoice"] else ""
        for index, line in enumerate(data["lines"]):
            ws2.append(
                _cells(
                    [
                        data["name"],
                        data["number"],
                        line["name"],
                        line["variant"],
                        line["quantity"],
                        float(line["amount"]) if line["amount"] else None,
                        data["note"] if index == 0 else "",
                        invoice if index == 0 else "",
                        (_("ja") if data["handed_out"] else "") if index == 0 else "",
                    ]
                )
            )
    for col, width in zip("ABCDEFGHI", (26, 12, 26, 12, 8, 10, 30, 14, 10), strict=False):
        ws2.column_dimensions[col].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
