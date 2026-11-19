"""Eintrittskarten und Einlass (Anmeldung A6, Konzept 3.11).

Je teilnehmender Person ein QR-Code mit einem signierten Kennzeichen ohne Personendaten
(``T<nummer>:<signatur>``). Beim Einlass prüft HUBIplan das Kennzeichen, zeigt Name, Tarif und
ob bezahlt ist, und hakt die Person ab; ein zweites Scannen meldet „schon eingelassen“.
"""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from django.core import signing
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Participant, Registration

SALT = "registrations.ticket"
PREFIX = "T"


def code(participant: Participant) -> str:
    """Inhalt des QR-Codes einer Eintrittskarte."""
    return signing.Signer(salt=SALT).sign(f"{PREFIX}{participant.pk}")


def participant_of(value: str) -> int | None:
    """Nummer der Person aus einem gescannten Code; None bei fremden oder falschen Codes."""
    value = (value or "").strip()
    if not value or len(value) > 120:
        return None
    try:
        raw = signing.Signer(salt=SALT).unsign(value)
    except signing.BadSignature:
        return None
    if not raw.startswith(PREFIX) or not raw[len(PREFIX) :].isdigit():
        return None
    return int(raw[len(PREFIX) :])


def has_tickets(reg: Registration) -> bool:
    """Eintrittskarten gibt es für verbindliche Anmeldungen mit aktiven Personen."""
    return reg.status == Registration.Status.REGISTERED and any(
        p.status == Participant.Status.ACTIVE for p in reg.participants.all()
    )


def filename(reg: Registration) -> str:
    return f"eintrittskarten-{reg.display_number}.pdf".replace("/", "-")


def pdf(reg: Registration) -> bytes:
    """Eintrittskarten einer Anmeldung als PDF, eine Karte je aktiver Person."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table

    from billing.pdf import qr_drawing
    from core.i18n import date_text, datetime_text

    from . import services

    event = reg.setup.event
    base = getSampleStyleSheet()
    normal = ParagraphStyle("n", parent=base["Normal"], fontSize=10, leading=13)
    small = ParagraphStyle("s", parent=normal, fontSize=8, leading=10, textColor=colors.grey)
    title = ParagraphStyle("t", parent=normal, fontSize=14, leading=18, spaceAfter=2)
    when = (
        date_text(timezone.localtime(event.starts_at).date())
        if event.all_day
        else datetime_text(timezone.localtime(event.starts_at))
    )
    place = ", ".join(x for x in (event.location, event.address) if x)
    paid = services.paid_state(reg)
    note = {
        "paid": _("bezahlt"),
        "free": _("kostenlos"),
    }.get(paid, _("Zahlung offen"))
    story = []
    for p in reg.participants.all():
        if p.status != Participant.Status.ACTIVE:
            continue
        text = [
            Paragraph(escape(reg.organization.name), small),
            Paragraph(escape(event.title), title),
            Paragraph(escape(when), normal),
        ]
        if place:
            text.append(Paragraph(escape(place), normal))
        text += [
            Spacer(1, 3 * mm),
            Paragraph(f"<b>{escape(p.name)}</b>", normal),
            Paragraph(escape(p.price_name or ""), normal),
            Spacer(1, 2 * mm),
            Paragraph(
                escape(
                    _("Anmeldung {number} · {state}").format(number=reg.display_number, state=note)
                ),
                small,
            ),
            Paragraph(escape(_("Eintrittskarte, bitte beim Einlass zeigen.")), small),
        ]
        card = Table(
            [[text, qr_drawing(code(p), 38 * mm)]],
            colWidths=[120 * mm, 45 * mm],
            style=[
                ("BOX", (0, 0), (-1, -1), 0.8, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 5 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5 * mm),
            ],
        )
        story += [KeepTogether(card), Spacer(1, 8 * mm)]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=_("Eintrittskarten: {title}").format(title=event.title),
    )
    doc.build(story or [Paragraph(escape(_("Keine Eintrittskarten.")), normal)])
    return buf.getvalue()


# --- Einlass ---


def entry_data(p: Participant, paid: str) -> dict:
    reg = p.registration
    return {
        "id": p.pk,
        "name": p.name,
        "price_name": p.price_name,
        "registration_id": reg.pk,
        "number": reg.display_number,
        "contact": reg.name,
        "paid_state": paid,
        # Abendkasse (A6/A7): offene Rechnung der Anmeldung, bar zu kassieren
        "invoice_id": reg.invoice_id,
        "invoice_number": reg.invoice.display_number if reg.invoice_id else "",
        "outstanding": str(reg.invoice.outstanding) if reg.invoice_id else "0.00",
        "checked_in_at": p.checked_in_at,
        # über welchen Scan-Link eingelassen (leer: in der Verwaltung)
        "checked_in_via": p.checked_in_via,
        "minor": bool(p.guardians),
        # gebuchte Zusatzleistungen und wann sie eingelöst wurden (Scan-Links)
        "bookings": [
            {"name": b.name, "redeemed_at": _redeemed_at(b)}
            for b in reg.bookings.all()
            if b.participant_id in (None, p.pk)
        ],
    }


def _redeemed_at(booking):
    from .models import Redemption

    try:
        return booking.redemption.at
    except Redemption.DoesNotExist:
        return None


def entries(setup) -> list[dict]:
    """Alle Personen verbindlicher Anmeldungen, nach Namen."""
    from . import services

    regs = (
        Registration.objects.filter(setup=setup, status=Registration.Status.REGISTERED)
        .select_related("invoice")
        .prefetch_related("participants", "bookings__redemption")
    )
    rows = []
    for reg in regs:
        paid = services.paid_state(reg)
        for p in reg.participants.all():
            if p.status == Participant.Status.ACTIVE:
                p.registration = reg
                rows.append(entry_data(p, paid))
    rows.sort(key=lambda r: (r["name"].casefold(), r["id"]))
    return rows


def check_in(setup, *, participant: int | None, scanned: str = "", user=None, undo=False):
    """Person einlassen (oder zurücknehmen). Liefert (Ergebnis, Daten der Person oder None).

    Ergebnis: ``ok``, ``already`` (schon eingelassen), ``undone``, ``unknown`` (Code passt
    nicht), ``other`` (Karte für einen anderen Termin), ``cancelled`` (abgemeldet)."""
    from . import services

    pk = participant if participant is not None else participant_of(scanned)
    if pk is None:
        return "unknown", None
    p = (
        Participant.objects.select_for_update(of=("self",))
        .select_related("registration__invoice")
        .filter(pk=pk)
        .first()
    )
    if p is None:
        return "unknown", None
    reg = p.registration
    if reg.setup_id != setup.pk:
        return "other", None
    paid = services.paid_state(reg)
    if p.status != Participant.Status.ACTIVE or reg.status != Registration.Status.REGISTERED:
        return "cancelled", entry_data(p, paid)
    if undo:
        p.checked_in_at = None
        p.checked_in_by = None
        p.checked_in_via = ""
        p.save(update_fields=["checked_in_at", "checked_in_by", "checked_in_via"])
        return "undone", entry_data(p, paid)
    if p.checked_in_at is not None:
        return "already", entry_data(p, paid)
    p.checked_in_at = timezone.now()
    p.checked_in_by = user
    p.checked_in_via = ""
    p.save(update_fields=["checked_in_at", "checked_in_by", "checked_in_via"])
    return "ok", entry_data(p, paid)
