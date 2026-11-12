"""Mitgliedsantrag als PDF mit Briefkopf: zum Unterschreiben oder mit Unterschrift."""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from django.utils import timezone, translation
from django.utils.translation import gettext
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table

from letterhead.data import letter_data
from letterhead.pdf import LetterDocument, text_styles

from . import services
from .models import Application


def render(app: Application) -> bytes:
    from finance import signature as signature_mod

    org = app.organization
    with translation.override(app.language):
        data = letter_data(org)
        st = text_styles(data)
        parts: list = LetterDocument.start(data, [], [], True)
        parts.append(
            Paragraph(
                escape(gettext("Mitgliedsantrag {number}").format(number=app.number)), st["title"]
            )
        )
        parts.append(
            Paragraph(
                escape(
                    gettext("Hiermit beantrage ich die Aufnahme als Mitglied in {org}.").format(
                        org=org.name
                    )
                ),
                st["body"],
            )
        )
        parts.append(Spacer(1, 2 * mm))
        for line in services.summary_lines(app):
            parts.append(Paragraph(escape(line), st["normal"]))
        parts.append(Spacer(1, 3 * mm))
        for c in app.consents or []:
            mark = "[x]" if c.get("given") else "[ ]"
            text = c.get("label", "")
            if c.get("version"):
                text += " " + gettext("(Fassung vom {date})").format(
                    date=services._date(c["version"])
                )
            parts.append(Paragraph(escape(f"{mark} {text}"), st["normal"]))
            if c.get("key") == services.CONFIRM_MANDATE and c.get("text"):
                parts.append(Paragraph(escape(c["text"]), st["small"]))
        parts.append(Spacer(1, 10 * mm))
        place = gettext("Ort, Datum")
        who = (
            gettext("Unterschrift (bei Minderjährigen: Erziehungsberechtigte)")
            if app.guardians
            else gettext("Unterschrift")
        )
        if app.signature:
            when = timezone.localtime(app.signed_at or app.created_at).strftime("%d.%m.%Y %H:%M")
            sig = signature_mod.drawing(app.signature, 70 * mm, 22 * mm)
            row = [[Paragraph(escape(when), st["normal"]), sig]]
            parts.append(Table(row, colWidths=[60 * mm, 80 * mm]))
            parts.append(Paragraph(escape(f"{place}    {who}"), st["small"]))
        else:
            parts.append(Spacer(1, 12 * mm))
            parts.append(Paragraph("_" * 30 + "      " + "_" * 45, st["normal"]))
            parts.append(
                Paragraph(escape(f"{place}                                   {who}"), st["small"])
            )
            parts.append(Spacer(1, 6 * mm))
            parts.append(
                Paragraph(
                    escape(
                        gettext("Bitte unterschreiben und an den Verein schicken oder abgeben.")
                    ),
                    st["small"],
                )
            )
        buf = io.BytesIO()
        LetterDocument(buf, [data], title=gettext("Mitgliedsantrag"), author=org.name).build(parts)
    return buf.getvalue()
