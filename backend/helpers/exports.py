"""Dienstplan drucken: Aushang je Dienst (PDF) und Gesamtliste (Excel)."""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from django.utils import timezone
from django.utils.translation import gettext as _
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table

from core.i18n import date_text, language_of_org
from exchange.export import safe_cell
from finance.report import _styles
from organizations.theme import effective_theme

from .models import HelperPlan, ShiftAssignment


def _when(shift) -> str:
    start = timezone.localtime(shift.starts_at)
    end = timezone.localtime(shift.ends_at)
    return f"{date_text(start)} {start:%H:%M}–{end:%H:%M}"


def _people(shift) -> list[ShiftAssignment]:
    return [a for a in shift.assignments.all() if a.status == ShiftAssignment.Status.ACTIVE]


def _duties(plan: HelperPlan):
    return plan.duties.prefetch_related("shifts__assignments")


def pdf(plan: HelperPlan, *, with_phone: bool) -> bytes:
    with language_of_org(plan.organization):
        return _pdf(plan, with_phone=with_phone)


def _pdf(plan: HelperPlan, *, with_phone: bool) -> bytes:
    st = _styles()
    primary = colors.HexColor(effective_theme(plan.organization.ancestors())["primary"])
    story: list = []
    duties = list(_duties(plan))
    for i, duty in enumerate(duties):
        if i:
            story.append(PageBreak())
        story.append(Paragraph(f"<b>{escape(duty.name)}</b>", st["title"]))
        sub = " · ".join(p for p in (plan.title, duty.location, duty.description) if p)
        story.append(Paragraph(escape(sub), st["normal"]))
        story.append(Spacer(1, 4 * mm))
        for shift in duty.shifts.all():
            people = _people(shift)
            head = _("{when} · {taken} von {needed}").format(
                when=_when(shift), taken=len(people), needed=shift.needed
            )
            story.append(Paragraph(f"<b>{escape(head)}</b>", st["h2"]))
            if shift.note:
                story.append(Paragraph(escape(shift.note), st["small"]))
            rows = []
            for a in people:
                row = [Paragraph(escape(a.name), st["normal"])]
                if with_phone:
                    row.append(Paragraph(escape(a.phone), st["normal"]))
                rows.append(row)
            for _free in range(max(shift.needed - len(people), 0)):
                rows.append([Paragraph("", st["normal"])] + ([""] if with_phone else []))
            if rows:
                widths = [110 * mm, 50 * mm] if with_phone else [160 * mm]
                story.append(
                    Table(
                        rows,
                        colWidths=widths,
                        rowHeights=[7 * mm] * len(rows),
                        hAlign="LEFT",
                        style=[
                            ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                            ("LINEBELOW", (0, -1), (-1, -1), 0.8, primary),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ],
                    )
                )
    if not duties:
        story.append(Paragraph(escape(plan.title), st["title"]))
        story.append(Paragraph(escape(_("Noch keine Dienste angelegt.")), st["normal"]))
    buf = io.BytesIO()
    SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        title=plan.title,
    ).build(story)
    return buf.getvalue()


def xlsx(plan: HelperPlan, *, with_phone: bool) -> bytes:
    with language_of_org(plan.organization):
        return _xlsx(plan, with_phone=with_phone)


def _xlsx(plan: HelperPlan, *, with_phone: bool) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = _("Dienstplan")[:31]
    ws.append([safe_cell(plan.title)])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append([])
    head = [_("Dienst"), _("Ort"), _("Beginn"), _("Ende"), _("Bedarf"), _("Name")]
    if with_phone:
        head.append(_("Telefon"))
    ws.append(head)
    for cell in ws[3]:
        cell.font = Font(bold=True)
    for duty in _duties(plan):
        for shift in duty.shifts.all():
            people = _people(shift)
            start = timezone.localtime(shift.starts_at).replace(tzinfo=None)
            end = timezone.localtime(shift.ends_at).replace(tzinfo=None)
            names = [(a.name, a.phone) for a in people] or [("", "")]
            names += [("", "")] * max(shift.needed - len(people), 0) if people else []
            for name, phone in names:
                row = [duty.name, duty.location, start, end, shift.needed, name]
                if with_phone:
                    row.append(phone)
                ws.append([safe_cell(v) if isinstance(v, str) else v for v in row])
    for col, width in zip("ABCDEFG", (24, 18, 17, 17, 8, 28, 18), strict=False):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=4, min_col=3, max_col=4):
        for cell in row:
            cell.number_format = "DD.MM.YYYY HH:MM"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
