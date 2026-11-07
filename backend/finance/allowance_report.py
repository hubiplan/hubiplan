"""Erklärung des Empfängers zu Übungsleiterfreibetrag und Ehrenamtspauschale (PDF)."""

from __future__ import annotations

from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer

from organizations.theme import effective_theme

from .allowances import TRAINER
from .project_report import _build
from .report import _euro, _styles, _table

TITLE = {
    TRAINER: "Erklärung zum Übungsleiterfreibetrag (§ 3 Nr. 26 EStG)",
    "volunteer": "Erklärung zur Ehrenamtspauschale (§ 3 Nr. 26a EStG)",
}
ACTIVITY = {
    TRAINER: "als Übungsleiter, Ausbilder, Betreuer, Dirigent oder in vergleichbarer Tätigkeit",
    "volunteer": "ehrenamtlich, z. B. im Vorstand, als Kassierer, Platzwart oder Helfer",
}
PARAGRAPH = {TRAINER: "§ 3 Nr. 26 EStG", "volunteer": "§ 3 Nr. 26a EStG"}


def render_declaration(org, data: dict, person: dict) -> bytes:
    st = _styles()
    r, rb = st["right"], st["right_bold"]
    primary = colors.HexColor(effective_theme(org.ancestors())["primary"])
    year = data["year"]
    story: list = []
    for i, kind in enumerate(person["kinds"]):
        k = kind["kind"]
        if i:
            story.append(Spacer(1, 12 * mm))
        story += [
            Paragraph(f"<b>{escape(TITLE[k])}</b>", st["title"]),
            Paragraph(f"{escape(org.name)} · Kalenderjahr {year}", st["normal"]),
            Spacer(1, 4 * mm),
            Paragraph(
                f"Ich, <b>{escape(person['name'])}</b>, bin im Kalenderjahr {year} für "
                f"{escape(org.name)} nebenberuflich {ACTIVITY[k]} tätig.",
                st["normal"],
            ),
            Spacer(1, 2 * mm),
            Paragraph(
                f"Ich erkläre, dass ich die Steuerbefreiung nach {PARAGRAPH[k]} für das Jahr "
                f"{year} bis zur Höhe von {_euro(kind['limit'])} nicht bereits in einem anderen "
                "Dienst- oder Auftragsverhältnis in Anspruch nehme. Nehme ich sie dort teilweise "
                "in Anspruch, betrifft das folgenden Betrag: ____________ €. Ändert sich etwas, "
                "teile ich es dem Verein sofort mit.",
                st["normal"],
            ),
            Spacer(1, 4 * mm),
        ]
        rows = [
            [
                Paragraph("<b>Datum</b>", st["normal"]),
                Paragraph("<b>Buchung</b>", st["normal"]),
                Paragraph("<b>Betrag</b>", r),
            ]
        ]
        for b in person["bookings"]:
            if b["allowance"] != k:
                continue
            rows.append(
                [
                    Paragraph(f"{b['date']:%d.%m.%Y}", st["normal"]),
                    Paragraph(escape(b["display_number"]), st["normal"]),
                    Paragraph(_euro(b["amount"]), r),
                ]
            )
        rows.append(
            [
                Paragraph("<b>Summe</b>", st["normal"]),
                Paragraph("", st["normal"]),
                Paragraph(_euro(kind["total"]), rb),
            ]
        )
        story.append(_table(rows, [40 * mm, 60 * mm, 40 * mm], primary))
        story += [
            Spacer(1, 16 * mm),
            Paragraph(
                "_______________________________&nbsp;&nbsp;&nbsp;&nbsp;"
                "_______________________________",
                st["normal"],
            ),
            Paragraph(
                "Ort, Datum" + "&nbsp;" * 50 + "Unterschrift",
                st["small"],
            ),
        ]
    story.append(Spacer(1, 6 * mm))
    story.append(
        Paragraph(
            "Die Erklärung gehört zu den Belegen der Kasse. Freibetrag und Pauschale gelten je "
            "Person und Kalenderjahr über alle Auftraggeber zusammen.",
            st["small"],
        )
    )
    return _build(org, f"Erklärung Aufwandsvergütung {year}", story)
