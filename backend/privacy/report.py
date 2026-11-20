"""Verzeichnis der Verarbeitungstätigkeiten und Protokoll einer Datenpanne als PDF."""

from __future__ import annotations

from xml.sax.saxutils import escape

from django.utils import timezone
from django.utils.translation import gettext as _
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table

from finance.project_report import _build
from finance.report import _styles
from organizations.theme import effective_theme

from . import services


def _text(value: str) -> str:
    return escape(value or "–").replace("\n", "<br/>")


def _fields(rows, st, primary):
    data = [
        [Paragraph(f"<b>{escape(label)}</b>", st["normal"]), Paragraph(_text(value), st["normal"])]
        for label, value in rows
    ]
    return Table(
        data,
        colWidths=[45 * mm, 125 * mm],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("LINEABOVE", (0, 0), (-1, 0), 0.8, primary),
        ],
        hAlign="LEFT",
    )


def _when(value) -> str:
    return f"{timezone.localtime(value):%d.%m.%Y %H:%M}" if value else ""


def register_pdf(org, settings) -> bytes:
    st = _styles()
    primary = colors.HexColor(effective_theme(org.ancestors())["primary"])
    title = _("Verzeichnis von Verarbeitungstätigkeiten")
    c = services.controller(org)
    story: list = [
        Paragraph(f"<b>{escape(title)}</b>", st["title"]),
        Paragraph(
            escape(_("nach Art. 30 Abs. 1 DSGVO"))
            + " · "
            + escape(_("Stand {date}").format(date=f"{timezone.localdate():%d.%m.%Y}")),
            st["small"],
        ),
        Spacer(1, 4 * mm),
        Paragraph(f"<b>{escape(_('Verantwortlicher'))}</b>", st["h2"]),
        _fields(
            [
                (_("Name"), c["name"]),
                (_("Anschrift"), c["address"]),
                (_("Vertreten durch"), c["representatives"]),
                (_("Kontakt"), c["contact"]),
                (
                    _("Datenschutzbeauftragte/r"),
                    " · ".join(p for p in (settings.dpo_name, settings.dpo_contact) if p)
                    or _("nicht benannt"),
                ),
            ],
            st,
            primary,
        ),
    ]
    for i, a in enumerate(services.activities(org, settings, with_hidden=False), start=1):
        story.append(
            KeepTogether(
                [
                    Paragraph(f"<b>{i}. {escape(a['title'])}</b>", st["h2"]),
                    _fields(
                        [
                            (_("Zweck"), a["purpose"]),
                            (_("Rechtsgrundlage"), a["legal_basis"]),
                            (_("Betroffene"), a["subjects"]),
                            (_("Datenkategorien"), a["categories"]),
                            (_("Empfänger"), a["recipients"]),
                            (_("Übermittlung in Drittländer"), a["third_country"]),
                            (_("Löschfrist"), a["retention"]),
                        ],
                        st,
                        primary,
                    ),
                ]
            )
        )
    procs = services.processors(org)
    lines = [settings.hoster] if settings.hoster else []
    for p in procs:
        a = p["agreement"]
        lines.append(
            p["name"]
            + " – "
            + (
                _("Vertrag zur Auftragsverarbeitung seit {date}").format(
                    date=a["start"][8:10] + "." + a["start"][5:7] + "." + a["start"][:4]
                )
                if a
                else _("kein Vertrag zur Auftragsverarbeitung hinterlegt")
            )
        )
    story += [
        Paragraph(f"<b>{escape(_('Auftragsverarbeiter'))}</b>", st["h2"]),
        Paragraph(_text("\n".join(lines) or _("keine")), st["normal"]),
        Paragraph(
            f"<b>{escape(_('Technische und organisatorische Maßnahmen (Art. 32 DSGVO)'))}</b>",
            st["h2"],
        ),
        Paragraph(_text(settings.toms), st["normal"]),
    ]
    return _build(org, title, story)


def breach_pdf(org, b) -> bytes:
    st = _styles()
    primary = colors.HexColor(effective_theme(org.ancestors())["primary"])
    title = _("Datenpanne: {title}").format(title=b.title)
    if b.reported_at:
        report = _("am {date}").format(date=_when(b.reported_at))
        if b.report_reference:
            report += f" ({b.report_reference})"
    else:
        report = _("nicht gemeldet")
    story: list = [
        Paragraph(f"<b>{escape(title)}</b>", st["title"]),
        Paragraph(
            escape(_("Dokumentation nach Art. 33 Abs. 5 DSGVO")) + " · " + escape(org.name),
            st["small"],
        ),
        Spacer(1, 4 * mm),
        _fields(
            [
                (_("Bekannt geworden"), _when(b.discovered_at)),
                (_("Zeitpunkt der Panne"), b.occurred),
                (_("Was ist passiert?"), b.description),
                (_("Betroffene Daten"), b.categories),
                (_("Betroffene Personen"), b.affected),
                (_("Wahrscheinliche Folgen"), b.consequences),
                (_("Einschätzung"), str(b.get_risk_display())),
                (_("Ergriffene Maßnahmen"), b.measures),
                (_("Frist für die Meldung"), _when(b.report_deadline)),
                (_("Meldung an die Aufsichtsbehörde"), report),
                (_("Begründung"), b.no_report_reason),
                (_("Betroffene benachrichtigt"), _when(b.notified_at) or _("nein")),
                (_("Abgeschlossen"), _when(b.closed_at) or _("offen")),
            ],
            st,
            primary,
        ),
    ]
    return _build(org, title, story)
