"""Schießnachweis als PDF und Auswertung der Anwesenheit als Excel.

Das PDF listet die bestätigten Schießtermine eines Mitglieds im gewählten Zeitraum und den
Stand nach § 14 Abs. 3 und 4 WaffG. Der vertretungsberechtigte Vorstand (§ 26 BGB) unterschreibt
und stempelt es; es ist die Anlage zum Antrag beim Verband, nicht dessen Formular.
"""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from django.utils import timezone
from django.utils.translation import gettext as _
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table

from exchange.export import safe_cell
from finance.project_report import _build
from finance.report import _styles, _table
from organizations.theme import effective_theme

from . import services


def _d(value) -> str:
    return f"{value:%d.%m.%Y}" if value else ""


def _yes(ok: bool) -> str:
    return _("erfüllt") if ok else _("nicht erfüllt")


def proof_pdf(org, membership, start, end, wclass: str = "") -> bytes:
    st = _styles()
    n, small = st["normal"], st["small"]
    primary = colors.HexColor(effective_theme(org.ancestors())["primary"])
    person = membership.person
    entries = list(services.entries_for(membership, start, end, wclass))
    state = services.evaluate(membership, end)
    title = _("Bestätigung der Schießtermine")
    address = ", ".join(
        x for x in (org.street, " ".join(y for y in (org.postal_code, org.city) if y)) if x
    )
    info = [
        [_("Verein"), org.name + (f", {address}" if address else "")],
        [_("Mitglied"), services.person_name(membership)],
    ]
    if person.birth_date:
        info.append([_("Geburtsdatum"), _d(person.birth_date)])
    if membership.club_number:
        info.append([_("Mitgliedsnummer"), membership.club_number])
    if state["member_since"]:
        info.append([_("Mitglied seit"), _d(state["member_since"])])
    period = _("{start} bis {end}").format(start=_d(start), end=_d(end))
    if wclass:
        period += " · " + str(dict(services.WeaponClass.choices)[wclass])
    info.append([_("Zeitraum"), period])
    story: list = [
        Paragraph(f"<b>{escape(title)}</b>", st["title"]),
        Paragraph(escape(_("Nachweis des regelmäßigen Schießens nach § 14 WaffG")), small),
        Spacer(1, 4 * mm),
        Table(
            [[Paragraph(f"<b>{escape(k)}</b>", n), Paragraph(escape(v), n)] for k, v in info],
            colWidths=[38 * mm, 132 * mm],
            hAlign="LEFT",
            style=[("VALIGN", (0, 0), (-1, -1), "TOP")],
        ),
        Spacer(1, 4 * mm),
    ]
    head = [
        _("Nr."),
        _("Datum"),
        _("Disziplin"),
        _("Waffe"),
        _("Kaliber"),
        _("Schießstand"),
        _("Art"),
    ]
    rows = [[Paragraph(f"<b>{escape(h)}</b>", n) for h in head]]
    for i, e in enumerate(entries, start=1):
        kind = []
        if e.competition:
            kind.append(_("Wettkampf"))
        else:
            kind.append(_("Training"))
        if not e.permit_required:
            kind.append(_("erlaubnisfrei"))
        rows.append(
            [
                Paragraph(str(i), n),
                Paragraph(_d(e.date), n),
                Paragraph(escape(e.discipline), n),
                Paragraph(escape(e.get_weapon_class_display()), n),
                Paragraph(escape(e.caliber), n),
                Paragraph(escape(e.place or org.name), n),
                Paragraph(escape(", ".join(kind)), n),
            ]
        )
    if not entries:
        rows.append(
            [Paragraph(escape(_("Keine bestätigten Schießtermine im Zeitraum.")), n)] + [""] * 6
        )
    story.append(
        _table(
            rows,
            [10 * mm, 20 * mm, 36 * mm, 20 * mm, 22 * mm, 40 * mm, 22 * mm],
            primary,
            total_row=False,
        )
    )
    story.append(Spacer(1, 4 * mm))
    acq = state["acquisition"]
    lines = [
        _(
            "§ 14 Abs. 3 WaffG (letzte 12 Monate bis {end}): {state}. {count} Schießtermine mit "
            "erlaubnispflichtigen Waffen, in jedem Monat: {months}."
        ).format(
            end=_d(end),
            state=_yes(acq["ok"]),
            count=acq["count"],
            months=_("ja") if acq["by_months"] else _("nein"),
        )
    ]
    for item in state["possession"]:
        lines.append(
            _(
                "§ 14 Abs. 4 WaffG, {label} (letzte 24 Monate): {state}. Jedes Quartal: {q}, "
                "sechsmal je 12 Monate: {six}."
            ).format(
                label=item["label"],
                state=_yes(item["ok"]),
                q=_("ja") if item["by_quarters"] else _("nein"),
                six=_("ja") if item["by_six"] else _("nein"),
            )
        )
    for line in lines:
        story.append(Paragraph(escape(line), small))
    story.append(Spacer(1, 6 * mm))
    confirm = _(
        "Der Verein bestätigt, dass {name} Mitglied ist und an den oben aufgeführten Tagen den "
        "Schießsport ausgeübt hat."
    ).format(name=services.person_name(membership))
    signature = Table(
        [
            ["", "", ""],
            [
                Paragraph(escape(_("Ort, Datum")), small),
                Paragraph(
                    escape(_("Unterschrift vertretungsberechtigter Vorstand (§ 26 BGB)")), small
                ),
                Paragraph(escape(_("Vereinsstempel")), small),
            ],
        ],
        colWidths=[50 * mm, 75 * mm, 45 * mm],
        rowHeights=[16 * mm, None],
        hAlign="LEFT",
        style=[
            ("LINEBELOW", (0, 0), (1, 0), 0.6, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ],
    )
    story.append(
        KeepTogether(
            [
                Paragraph(escape(confirm), n),
                Spacer(1, 2 * mm),
                signature,
                Spacer(1, 4 * mm),
                Paragraph(
                    escape(
                        _(
                            "Erstellt mit HUBIplan am {date}. Anlage zum Antrag beim Verband; "
                            "es zählen nur vom Verein bestätigte Termine."
                        ).format(date=_d(timezone.localdate()))
                    ),
                    small,
                ),
            ]
        )
    )
    return _build(org, title, story)


def report_xlsx(org, data: dict) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    fill = PatternFill("solid", fgColor="DDE7E3")
    sheets = [
        (
            _("Teilnahmen je Mitglied"),
            [[_("Name"), _("Teilnahmen"), _("Anteil in Prozent")]]
            + [[r["name"], r["count"], r["share"]] for r in data["members"]],
        ),
        (
            _("Termine"),
            [[_("Datum"), _("Bezeichnung"), _("Art"), _("Leitung"), _("Stunden"), _("Anwesend")]]
            + [
                [
                    s["date"],
                    s["title"],
                    s["kind_label"],
                    s["leader"],
                    s["hours"] if s["hours"] is not None else "",
                    s["count"],
                ]
                for s in data["sessions"]
            ],
        ),
    ]
    for title, table in sheets:
        ws = wb.create_sheet(str(title)[:31])
        for row in table:
            ws.append([safe_cell(v) for v in row])
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = fill
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if hasattr(cell.value, "year"):
                    cell.number_format = "DD.MM.YYYY"
        for i in range(1, ws.max_column + 1):
            width = max(len(str(r[i - 1])) if i <= len(r) else 0 for r in table[:200]) + 2
            ws.column_dimensions[get_column_letter(i)].width = min(max(width, 10), 50)
        ws.freeze_panes = "A2"
    wb.properties.creator = f"HUBIplan – {org.name}"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
