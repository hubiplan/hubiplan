"""Steuerliche Auswertung als PDF und Excel (Vorlage für Steuererklärung und Beratung)."""

from __future__ import annotations

from decimal import Decimal
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer

from organizations.theme import effective_theme

from .project_report import _build, _xlsx
from .report import _euro, _styles, _table

STATUS_TEXT = {
    "ok": "unter der Grenze",
    "warn": "nahe an der Grenze (ab 80 %)",
    "over": "überschritten",
}


def _area_rows(areas: list[dict]) -> list[list]:
    return [[a["label"], a["income"], a["expense"], a["result"]] for a in areas]


def render_pdf(org, data: dict) -> bytes:
    st = _styles()
    r, rb = st["right"], st["right_bold"]
    primary = colors.HexColor(effective_theme(org.ancestors())["primary"])
    title = f"Steuerliche Auswertung {data['label']}"
    story: list = [
        Paragraph(f"<b>{escape(title)}</b>", st["title"]),
        Paragraph(
            f"{escape(org.name)} · Geschäftsjahr {data['start_date']:%d.%m.%Y} bis "
            f"{data['end_date']:%d.%m.%Y} · Veranlagungszeitraum {data['period']}",
            st["normal"],
        ),
        Paragraph(
            f"Stand vom {data['today']:%d.%m.%Y}. Stornos sind mit der stornierten Buchung "
            "verrechnet. Vorlage für die Steuererklärung, keine Steuerberatung.",
            st["small"],
        ),
        Spacer(1, 4 * mm),
    ]
    if not data["root"]["is_self"]:
        story.append(
            Paragraph(
                f"Diese Kasse zählt steuerlich bei {escape(data['root']['name'])} mit. "
                "Freigrenze und Kleinunternehmergrenze gelten für die Summe dort.",
                st["normal"],
            )
        )

    def area_table(areas):
        rows = [
            [
                Paragraph(f"<b>{h}</b>", st["normal"] if i == 0 else r)
                for i, h in enumerate(["Bereich", "Einnahmen", "Ausgaben", "Ergebnis"])
            ]
        ]
        for a in areas:
            rows.append(
                [
                    Paragraph(escape(a["label"]), st["normal"]),
                    Paragraph(_euro(a["income"]), r),
                    Paragraph(_euro(a["expense"]), r),
                    Paragraph(_euro(a["result"]), r),
                ]
            )
        return _table(rows, [80 * mm, 30 * mm, 30 * mm, 32 * mm], primary, total_row=False)

    story.append(Paragraph("<b>Nach steuerlichem Bereich</b>", st["h2"]))
    story.append(area_table(data["areas"]))
    if data["units"]:
        story.append(
            Paragraph(
                "Enthalten sind die Kassen der Untereinheiten (§ 64 Abs. 4 AO):",
                st["small"],
            )
        )
        rows = [
            [
                Paragraph("<b>Kasse</b>", st["normal"]),
                Paragraph("<b>Einnahmen wGB</b>", r),
                Paragraph("<b>Umsatz (Zweckbetrieb, wGB)</b>", r),
            ]
        ]
        rows.append(
            [
                Paragraph(escape(org.name), st["normal"]),
                Paragraph(_euro(_own(data, "business")), r),
                Paragraph(_euro(_own(data, "purpose") + _own(data, "business")), r),
            ]
        )
        for u in data["units"]:
            rows.append(
                [
                    Paragraph(escape(u["name"]), st["normal"]),
                    Paragraph(_euro(u["business_income"]), r),
                    Paragraph(_euro(u["turnover"]), r),
                ]
            )
        story.append(_table(rows, [80 * mm, 40 * mm, 52 * mm], primary, total_row=False))

    fl = data["free_limit"]
    story.append(Paragraph("<b>Freigrenze wirtschaftlicher Geschäftsbetrieb</b>", st["h2"]))
    story.append(
        Paragraph(
            f"Einnahmen einschließlich Umsatzsteuer: <b>{_euro(fl['income'])}</b> von "
            f"{_euro(fl['limit'])} ({fl['percent']} %), {STATUS_TEXT[fl['status']]} "
            f"(§ 64 Abs. 3 AO). Ergebnis des Bereichs: {_euro(data['business_result'])}.",
            st["normal"],
        )
    )
    rows = [
        [
            Paragraph("<b>Geschäftsjahr</b>", st["normal"]),
            Paragraph("<b>Einnahmen wGB</b>", r),
            Paragraph("<b>Ergebnis wGB</b>", r),
        ]
    ]
    for h in [*data["history"], None]:
        label = h["label"] if h else data["label"]
        income = h["income"] if h else fl["income"]
        result = h["result"] if h else data["business_result"]
        style = rb if h is None else r
        rows.append(
            [
                Paragraph(escape(label), st["normal"]),
                Paragraph(_euro(income), style),
                Paragraph(_euro(result), style),
            ]
        )
    story.append(_table(rows, [80 * mm, 40 * mm, 52 * mm], primary, total_row=False))

    sb = data["small_business"]
    if sb:
        story.append(Paragraph("<b>Kleinunternehmergrenze (§ 19 UStG)</b>", st["h2"]))
        story.append(
            Paragraph(
                f"Einnahmen aus Zweckbetrieb und wirtschaftlichem Geschäftsbetrieb im Vorjahr "
                f"{_euro(sb['previous'])} (Grenze {_euro(sb['previous_limit'])}), im laufenden "
                f"Jahr {_euro(sb['current'])} (Grenze {_euro(sb['current_limit'])}): "
                f"{STATUS_TEXT[sb['status']]}. Anhaltspunkt: Die Grenzen gelten netto, "
                "steuerfreie Umsätze und Vermietung sind gesondert zu prüfen.",
                st["normal"],
            )
        )

    notes = [w["text"] for w in data["warnings"]]
    if data["declaration"]:
        notes.append(data["declaration"]["text"])
    if notes:
        story.append(Paragraph("<b>Hinweise</b>", st["h2"]))
        for text in notes:
            story.append(Paragraph(f"• {escape(text)}", st["normal"]))
    return _build(org, title, story)


def _own(data: dict, area: str):
    for a in data["own_areas"]:
        if a["area"] == area:
            return a["income"]
    return Decimal("0")


def render_xlsx(org, data: dict) -> bytes:
    head = ["Bereich", "Einnahmen", "Ausgaben", "Ergebnis"]
    fl = data["free_limit"]
    sheets = [
        ("Steuerliche Bereiche", [head, *_area_rows(data["areas"])]),
        (
            "Freigrenze wGB",
            [
                ["Geschäftsjahr", "Einnahmen wGB", "Ergebnis wGB", "Freigrenze"],
                *[[h["label"], h["income"], h["result"], ""] for h in data["history"]],
                [data["label"], fl["income"], data["business_result"], fl["limit"]],
            ],
        ),
    ]
    if data["units"]:
        sheets.append(
            (
                "Kassen",
                [
                    ["Kasse", "Einnahmen wGB", "Umsatz (Zweckbetrieb, wGB)"],
                    [
                        org.name,
                        _own(data, "business"),
                        _own(data, "purpose") + _own(data, "business"),
                    ],
                    *[[u["name"], u["business_income"], u["turnover"]] for u in data["units"]],
                ],
            )
        )
    sb = data["small_business"]
    if sb:
        sheets.append(
            (
                "Kleinunternehmer",
                [
                    ["Zeitraum", "Umsatz (Anhaltspunkt)", "Grenze"],
                    ["Vorjahr", sb["previous"], sb["previous_limit"]],
                    ["laufendes Jahr", sb["current"], sb["current_limit"]],
                ],
            )
        )
    return _xlsx(org, sheets)
