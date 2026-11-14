"""Ergebnis einer Umfrage als PDF und Excel (z. B. Essenswahl für den Wirt).

Mit Namen nur, wenn die Umfrage nicht anonym ist; anonym nur Zahlen und Texte.
"""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

from core.i18n import datetime_text, language_of_org
from exchange.export import safe_cell
from finance.report import _styles

from . import services
from .models import Survey

VALUE_LABELS = {
    "yes": gettext_lazy("Ja"),
    "no": gettext_lazy("Nein"),
    "abstain": gettext_lazy("Enthaltung"),
}


def _rows(survey: Survey) -> tuple[dict, list[tuple[str, list[tuple[str, str, str]]]]]:
    """Ergebnis und je Frage Zeilen (Antwort, Zahl, Namen)."""
    data = services.result_data(survey, with_names=True)
    out = []
    for q in data.get("questions") or []:
        rows: list[tuple[str, str, str]] = []
        if q["kind"] == "yesno":
            for key, label in VALUE_LABELS.items():
                v = q["values"][key]
                rows.append((str(label), str(v["count"]), ", ".join(v["names"])))
        elif q["kind"] == "text":
            for t in q["texts"]:
                rows.append((t["text"], "", t["name"]))
        else:
            for o in q["options"]:
                count = str(o["count"])
                if q["kind"] == "dates" and o.get("maybe"):
                    count += " " + _("(+{n} vielleicht)").format(n=o["maybe"])
                if o.get("capacity"):
                    count += f" / {o['capacity']}"
                rows.append((o["label"], count, ", ".join(o.get("names") or [])))
        out.append((q["text"], rows))
    return data, out


def _head(survey: Survey, data: dict) -> str:
    parts = [_("{n} Teilnahmen").format(n=data.get("participants", 0))]
    if survey.closes_at:
        parts.append(_("Ende: {when}").format(when=datetime_text(survey.closes_at)))
    if survey.anonymous:
        parts.append(_("anonym"))
    return " · ".join(parts)


def pdf(survey: Survey) -> bytes:
    with language_of_org(survey.organization):
        return _pdf(survey)


def _pdf(survey: Survey) -> bytes:
    st = _styles()
    data, questions = _rows(survey)
    story: list = [
        Paragraph(f"<b>{escape(survey.title)}</b>", st["title"]),
        Paragraph(escape(_head(survey, data)), st["normal"]),
        Paragraph(escape(_("Meinungsbild, kein Beschluss.")), st["small"]),
        Spacer(1, 4 * mm),
    ]
    if data.get("hidden"):
        story.append(
            Paragraph(escape(_("Zu wenige Antworten für ein anonymes Ergebnis.")), st["normal"])
        )
    for text, rows in questions:
        story.append(Paragraph(f"<b>{escape(text)}</b>", st["h2"]))
        if not rows:
            story.append(Paragraph("–", st["normal"]))
            continue
        table = [
            [
                Paragraph(escape(a), st["normal"]),
                Paragraph(escape(b), st["normal"]),
                Paragraph(escape(c), st["small"]),
            ]
            for a, b, c in rows
        ]
        story.append(
            Table(
                table,
                colWidths=[60 * mm, 25 * mm, 85 * mm],
                hAlign="LEFT",
                style=[
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ],
            )
        )
        story.append(Spacer(1, 3 * mm))
    buf = io.BytesIO()
    SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        title=survey.title,
    ).build(story)
    return buf.getvalue()


def xlsx(survey: Survey) -> bytes:
    with language_of_org(survey.organization):
        return _xlsx(survey)


def _xlsx(survey: Survey) -> bytes:
    data, questions = _rows(survey)
    wb = Workbook()
    ws = wb.active
    ws.title = _("Umfrage")[:31]
    ws.append([safe_cell(survey.title)])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append([safe_cell(_head(survey, data))])
    ws.append([])
    ws.append([_("Frage"), _("Antwort"), _("Anzahl"), _("Namen")])
    for cell in ws[4]:
        cell.font = Font(bold=True)
    for text, rows in questions:
        for a, b, c in rows or [("", "", "")]:
            ws.append([safe_cell(text), safe_cell(a), safe_cell(b), safe_cell(c)])
    for col, width in zip("ABCD", (36, 30, 14, 60), strict=False):
        ws.column_dimensions[col].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
