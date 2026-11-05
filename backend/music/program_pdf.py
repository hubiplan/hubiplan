"""Printable programme and preparation lists from the same data as CSV exports."""

import io
from xml.sax.saxutils import escape

from django.utils import timezone
from django.utils.translation import gettext
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from organizations.theme import effective_theme


def render(performance, data, kind):
    org, event = performance.organization, performance.event
    primary = colors.HexColor(effective_theme(org.ancestors())["primary"])
    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "music-body", parent=styles["Normal"], fontSize=9, leading=12, spaceAfter=3
    )
    heading = ParagraphStyle("music-heading", parent=styles["Heading2"], textColor=primary)
    small = ParagraphStyle("music-small", parent=normal, fontSize=8, leading=10)
    title = gettext("Programmliste") if kind == "program" else gettext("Stimmenliste")
    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=title,
        author=org.name,
    )

    def p(value, style=normal):
        return Paragraph(
            escape(str(value if value is not None else "")).replace("\n", "<br/>"), style
        )

    def table(headers, rows, widths):
        content = [
            [p(h, small) for h in headers],
            *[[p(cell, small) for cell in row] for row in rows],
        ]
        result = Table(
            content, colWidths=[w * mm for w in widths], repeatRows=1, hAlign="LEFT", splitInRow=1
        )
        result.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3f3")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.6, primary),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#dddddd")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return result

    printed = timezone.localtime().strftime("%d.%m.%Y %H:%M")

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#595959"))
        canvas.drawString(18 * mm, 11 * mm, gettext("Stand: {date}").format(date=printed))
        canvas.drawRightString(
            192 * mm, 11 * mm, gettext("Seite {number}").format(number=document.page)
        )
        canvas.restoreState()

    def later_page(canvas, document):
        footer(canvas, document)
        header = p(f"{org.name} · {title}", small)
        _, height = header.wrap(174 * mm, 12 * mm)
        header.drawOn(canvas, 18 * mm, A4[1] - 6 * mm - height)

    story = [
        p(org.name, heading),
        p(title, styles["Title"]),
        p(event.title, heading),
        p(f"{timezone.localtime(event.starts_at):%d.%m.%Y %H:%M} · {event.location}"),
        Spacer(1, 5 * mm),
    ]
    if event.is_cancelled:
        story.append(p(gettext("Auftritt abgesagt"), heading))
    if kind == "program":
        labels = {"piece": gettext("Stück"), "pause": gettext("Pause"), "encore": gettext("Zugabe")}
        rows = []
        for entry in data["entries"]:
            seconds = entry["effective_seconds"]
            duration = (
                f"{seconds // 60}:{seconds % 60:02}" if seconds else gettext("Dauer unbekannt")
            )
            rows.append(
                [
                    entry["position"],
                    entry["title"] or labels[entry["kind"]],
                    entry["arrangement_name"],
                    labels[entry["kind"]],
                    duration,
                    entry["note"],
                ]
            )
        story.append(
            table(
                [
                    gettext("Nr."),
                    gettext("Titel"),
                    gettext("Arrangement"),
                    gettext("Art"),
                    gettext("Dauer"),
                    gettext("Hinweis"),
                ],
                rows,
                [13, 50, 38, 21, 18, 34],
            )
        )
        story.append(Spacer(1, 4 * mm))
        for label, key in [
            (gettext("Reguläre Dauer"), "regular_seconds"),
            (gettext("Zugaben"), "encore_seconds"),
            (gettext("Gesamtdauer"), "total_seconds"),
        ]:
            seconds = data[key]
            story.append(p(f"{label}: {seconds // 60}:{seconds % 60:02}"))
    else:
        for item in data["preparation"]:
            story.extend(
                [
                    p(f"{item['title']} · {item['name']}", heading),
                    p(
                        gettext("Konzertformat")
                        if item["paper_format"] == "concert"
                        else gettext("Marschformat")
                    ),
                ]
            )
            if not item["active"]:
                story.append(p(gettext("Dieses Arrangement ist archiviert.")))
            if item["missing_specification"]:
                story.append(p(gettext("Besetzungsangaben fehlen.")))
            rows = [
                [
                    v["instrument"]
                    + " "
                    + v["register"]
                    + (" (" + gettext("Partitur") + ")" if v["kind"] == "score" else ""),
                    v["needed_copies"],
                    v["available"],
                    v["held"],
                    v["missing_copies"],
                    v["missing_players"],
                    ", ".join(v["locations"]),
                ]
                for v in item["voices"]
            ]
            story.append(
                table(
                    [
                        gettext("Instrument / Stimme"),
                        gettext("Benötigt"),
                        gettext("Frei"),
                        gettext("Bei Eingeteilten"),
                        gettext("Fehlend"),
                        gettext("Fehlende Musiker"),
                        gettext("Lagerort"),
                    ],
                    rows,
                    [43, 18, 17, 22, 20, 19, 35],
                )
            )
            if item["license_note"]:
                story.append(p(gettext("Lizenzhinweise") + ": " + item["license_note"], small))
            story.append(Spacer(1, 4 * mm))
    if (kind == "program" and not data["entries"]) or (kind == "parts" and not data["preparation"]):
        story.append(p(gettext("Noch keine Programmpunkte vorhanden.")))
    doc.build(story, onFirstPage=footer, onLaterPages=later_page)
    return output.getvalue()
