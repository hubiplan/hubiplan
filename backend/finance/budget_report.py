"""Haushaltsplan als PDF und Excel, etwa als Vorlage für die Mitgliederversammlung.

Spalten: Plan des Jahres, Ist des Jahres (nicht bei einem künftigen Jahr), Plan und Ist
des Vorjahres.
"""

from __future__ import annotations

from decimal import Decimal
from xml.sax.saxutils import escape

from django.utils import timezone
from django.utils.translation import gettext as _
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer

from organizations.theme import effective_theme

from .project_report import _build, _xlsx
from .report import _euro, _styles, _table

ZERO = Decimal("0.00")


def _name(line: dict) -> str:
    if line.get("department_name"):
        return f"{line['category_name']} ({line['department_name']})"
    return line["category_name"]


def _columns(data: dict) -> list[tuple[str, str]]:
    """(Überschrift, Schlüssel) der Betragsspalten."""
    cols = [(_("Plan {year}").format(year=data["label"]), "amount")]
    if data["phase"] != "future":
        cols.append((_("Ist {year}").format(year=data["label"]), "actual"))
    if data["phase"] == "current":
        cols.append((_("Hochrechnung"), "forecast"))
    cols.append((_("Plan {year}").format(year=data["previous_label"]), "previous_plan"))
    cols.append((_("Ist {year}").format(year=data["previous_label"]), "previous_actual"))
    return cols


TOTAL_KEYS = {
    "amount": "plan",
    "actual": "actual",
    "forecast": "forecast",
    "previous_plan": "previous_plan",
    "previous_actual": "previous_actual",
}


def _sections(data: dict):
    """Je Art: Überschrift, Zeilen (Name, Werte) und Summe."""
    cols = _columns(data)
    out = []
    for kind, title in (("income", _("Einnahmen")), ("expense", _("Ausgaben"))):
        rows = []
        for line in data["lines"]:
            if line["kind"] == kind:
                rows.append((_name(line), [line.get(key) for _h, key in cols]))
        for line in data["unplanned"]:
            if line["kind"] == kind:
                values = [line["actual"] if key == "actual" else None for _h, key in cols]
                rows.append((_name(line) + " – " + _("nicht geplant"), values))
        total = data["totals"][kind]
        out.append((title, rows, [total.get(TOTAL_KEYS[key]) for _h, key in cols]))
    result = data["totals"]["result"]
    return cols, out, [result.get(TOTAL_KEYS[key]) for _h, key in cols]


def render_pdf(org, data: dict) -> bytes:
    st = _styles()
    r, rb, n = st["right"], st["right_bold"], st["normal"]
    primary = colors.HexColor(effective_theme(org.ancestors())["primary"])
    cols, sections, result = _sections(data)
    title = _("Haushaltsplan {year}").format(year=data["label"])
    plan = data["budget"]
    if plan and plan["status"] == "adopted":
        state = _("beschlossen am {date}").format(date=f"{plan['adopted_on']:%d.%m.%Y}")
        if plan["adopted_by"]:
            state += f" ({escape(plan['adopted_by'])})"
    else:
        state = _("Entwurf")
    story: list = [
        Paragraph(f"<b>{escape(title)}</b>", st["title"]),
        Paragraph(
            f"{escape(org.name)} · "
            + _("Geschäftsjahr {start} bis {end}").format(
                start=f"{data['start_date']:%d.%m.%Y}", end=f"{data['end_date']:%d.%m.%Y}"
            ),
            n,
        ),
        Paragraph(
            f"{state} · " + _("Stand {date}").format(date=f"{timezone.localdate():%d.%m.%Y}"),
            st["small"],
        ),
        Spacer(1, 4 * mm),
    ]
    first = 170 - 22 * len(cols)
    widths = [max(first, 50) * mm] + [22 * mm] * len(cols)

    def amount(value, style):
        return Paragraph("" if value is None else _euro(value), style)

    for heading, rows, total in sections:
        story.append(Paragraph(f"<b>{escape(heading)}</b>", st["h2"]))
        table = [
            [Paragraph(f"<b>{escape(_('Kategorie'))}</b>", n)]
            + [Paragraph(f"<b>{escape(h)}</b>", r) for h, _k in cols]
        ]
        for name, values in rows:
            table.append([Paragraph(escape(name), n)] + [amount(v, r) for v in values])
        table.append(
            [Paragraph(f"<b>{escape(_('Summe'))}</b>", n)] + [amount(v, rb) for v in total]
        )
        story.append(_table(table, widths, primary))
    story.append(Paragraph(f"<b>{escape(_('Ergebnis'))}</b>", st["h2"]))
    story.append(
        _table(
            [
                [Paragraph("", n)] + [Paragraph(f"<b>{escape(h)}</b>", r) for h, _k in cols],
                [Paragraph(f"<b>{escape(_('Einnahmen minus Ausgaben'))}</b>", n)]
                + [amount(v, rb) for v in result],
            ],
            widths,
            primary,
        )
    )
    if plan and plan["note"]:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(escape(plan["note"]).replace("\n", "<br/>"), n))
    return _build(org, title, story)


def render_xlsx(org, data: dict) -> bytes:
    cols, sections, result = _sections(data)
    head = [_("Art"), _("Kategorie")] + [h for h, _k in cols]
    table = [head]
    for heading, rows, total in sections:
        for name, values in rows:
            table.append([heading, name, *values])
        table.append([heading, _("Summe"), *total])
    table.append([_("Ergebnis"), _("Einnahmen minus Ausgaben"), *result])
    clean = [[("" if v is None else v) for v in row] for row in table]
    return _xlsx(org, [(_("Haushaltsplan {year}").format(year=data["label"]), clean)])
