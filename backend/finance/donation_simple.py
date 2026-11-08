"""Vereinfachter Zuwendungsnachweis für Spenden bis 300 € (Konzept vereinskasse-steuern, S8).

Für Zuwendungen bis 300 € genügt als Nachweis der Kontoauszug oder die Buchungsbestätigung
der Bank, wenn der Verein dazu einen Beleg bereitstellt, aus dem die Angaben über die
Steuerbegünstigung und die Art der Zuwendung hervorgehen (§ 50 Abs. 4 Satz 1 Nr. 2 EStDV).
Diesen Beleg gibt es als PDF zum Auslegen oder Mitschicken und als Text für die Webseite.
"""

from __future__ import annotations

import io
import re
from xml.sax.saxutils import escape, unescape

from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer

from letterhead.data import letter_data
from letterhead.pdf import LetterDocument, text_styles

from .donation_pdf import _notice_text
from .models import Account, DonationSettings

LIMIT = "300 €"


def _accounts(org) -> list[tuple[str, str]]:
    rows = Account.objects.filter(organization=org, is_active=True).exclude(iban="")
    return [(a.name, " ".join(a.iban[i : i + 4] for i in range(0, len(a.iban), 4))) for a in rows]


def paragraphs(org, cfg: DonationSettings) -> list[str]:
    """Absätze des Belegs (mit <b> für Hervorhebungen, sonst reiner Text)."""
    kind = (
        "Der Beleg gilt für Spenden und Mitgliedsbeiträge."
        if cfg.fees_allowed
        else "Der Beleg gilt für Spenden. Mitgliedsbeiträge sind nicht als Zuwendung abziehbar."
    )
    parts = [
        f"Für Zuwendungen bis {LIMIT} genügt als Nachweis für das Finanzamt der Kontoauszug "
        "oder die Buchungsbestätigung der Bank zusammen mit diesem Beleg "
        "(§ 50 Abs. 4 Satz 1 Nr. 2 EStDV).",
        f"Zuwendungsempfänger: <b>{escape(org.name)}</b>",
        _notice_text(cfg),
        "Die Zuwendung wird ausschließlich für die genannten steuerbegünstigten Zwecke verwendet.",
        kind,
    ]
    accounts = _accounts(org)
    if accounts:
        parts.append(
            "Konto für Zuwendungen: "
            + "; ".join(f"{escape(name)}, IBAN {iban}" for name, iban in accounts)
        )
    parts.append("Bitte diesen Beleg zusammen mit dem Kontoauszug aufbewahren.")
    return parts


def text(org, cfg: DonationSettings) -> str:
    """Derselbe Inhalt als reiner Text, etwa für die Webseite."""
    title = f"Vereinfachter Zuwendungsnachweis für Zuwendungen bis {LIMIT}"
    body = [re.sub(r"</?b>", "", p) for p in paragraphs(org, cfg)]
    return "\n\n".join([title, *[unescape(p) for p in body]])


def render(org, cfg: DonationSettings) -> bytes:
    data = letter_data(org)
    st = text_styles(data)
    parts: list = LetterDocument.start(data, [], [], True)
    parts.append(
        Paragraph(f"Vereinfachter Zuwendungsnachweis für Zuwendungen bis {LIMIT}", st["title"])
    )
    parts.append(Spacer(1, 3 * mm))
    for p in paragraphs(org, cfg):
        parts.append(Paragraph(p, st["body"]))
    parts.append(Spacer(1, 4 * mm))
    parts.append(
        Paragraph(
            "Ab einer Zuwendung über 300 € stellt der Verein eine Zuwendungsbestätigung nach "
            "amtlichem Muster aus.",
            st["small"],
        )
    )
    buf = io.BytesIO()
    LetterDocument(
        buf,
        [data],
        title="Vereinfachter Zuwendungsnachweis",
        author=org.name,
    ).build(parts)
    return buf.getvalue()
