"""Vor Ort und danach (Anmeldung A6, Konzept 3.11): Namensschilder, Teilnahmebescheinigungen
und Qualifikationen für Teilnehmende eintragen.

„Teilgenommen“ heißt: beim Einlass abgehakt. Hat der Verein den Einlass nicht genutzt
(niemand abgehakt), gelten alle Personen verbindlicher Anmeldungen.
"""

from __future__ import annotations

import datetime
import io
from xml.sax.saxutils import escape

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Participant, Registration


def active(setup) -> list[Participant]:
    """Alle Personen verbindlicher Anmeldungen, nach Namen."""
    rows = list(
        Participant.objects.filter(
            registration__setup=setup,
            registration__status=Registration.Status.REGISTERED,
            status=Participant.Status.ACTIVE,
        ).select_related("registration__club", "membership__organization", "membership__person")
    )
    rows.sort(key=lambda p: (p.name.casefold(), p.pk))
    return rows


def present(setup) -> tuple[list[Participant], bool]:
    """(Teilnehmende, ob nach Einlass gefiltert)."""
    rows = active(setup)
    if any(p.checked_in_at for p in rows):
        return [p for p in rows if p.checked_in_at], True
    return rows, False


def _days(event) -> tuple[datetime.date, datetime.date]:
    start = timezone.localtime(event.starts_at).date()
    end = timezone.localtime(event.ends_at).date() if event.ends_at else start
    return start, max(start, end)


def last_day(event) -> datetime.date:
    return _days(event)[1]


def when_text(event) -> str:
    from core.i18n import date_text

    start, end = _days(event)
    if start == end:
        return _("am {date}").format(date=date_text(start))
    return _("vom {start} bis {end}").format(start=date_text(start), end=date_text(end))


def _place(event) -> str:
    return ", ".join(x for x in (event.location, event.address.replace("\n", ", ")) if x)


# --- Namensschilder und Aufkleber ---

# Format: (Breite mm, Höhe mm, Spalten, Zeilen) je A4-Seite
FORMATS = {
    "badge": (85, 54, 2, 5),  # Visitenkartenformat für übliche Namensschildhüllen
    "label24": (70, 37, 3, 8),  # Aufkleber 70 × 37 mm, 24 je Bogen
    "label8": (105, 74, 2, 4),  # große Aufkleber 105 × 74 mm, 8 je Bogen
}
# Angaben, die sich drucken lassen; dazu „q<Frage>“ für Antworten auf Zusatzfragen
FIELDS = ("event", "name", "club", "price", "addons", "number", "qr")
DEFAULT_FIELDS = ("event", "name", "club")
BADGE_W, BADGE_H = 85, 54
COLS, ROWS = 2, 5


def label_options(setup) -> dict:
    """Was sich auf Namensschildern und Aufklebern drucken lässt."""
    from . import extras as ex

    questions = [q for q in ex.active_questions(setup) if q.kind != q.Kind.HEALTH]
    return {
        "formats": list(FORMATS),
        "fields": list(FIELDS),
        "questions": [{"id": q.pk, "text": q.text} for q in questions],
        "default_fields": list(DEFAULT_FIELDS),
    }


def clean_fields(raw: str, setup) -> list[str]:
    from . import extras as ex

    allowed = set(FIELDS) | {
        f"q{q.pk}" for q in ex.active_questions(setup) if q.kind != q.Kind.HEALTH
    }
    out = [f for f in (raw or "").split(",") if f in allowed]
    return list(dict.fromkeys(out)) or list(DEFAULT_FIELDS)


def _club(p: Participant) -> str:
    if p.membership_id:
        return p.membership.organization.name
    if p.registration.club_id:
        return p.registration.club.name
    return ""


def _answer(p: Participant, q) -> str:
    from . import extras as ex

    answers = p.answers if q.per == "person" else p.registration.answers
    rows = ex.answer_lines([q], answers or {})
    return rows[0]["answer"] if rows else ""


def labels_pdf(setup, fmt: str = "badge", fields: list[str] | None = None) -> bytes:
    """Namensschilder oder Aufkleber aller Personen verbindlicher Anmeldungen, mit den
    gewählten Angaben (A6)."""
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    from letterhead.data import letter_data
    from letterhead.pdf import fit, fonts

    from . import tickets
    from .models import Booking, Question

    fields = fields or list(DEFAULT_FIELDS)
    width, height, cols, rows_per = FORMATS.get(fmt, FORMATS["badge"])
    event = setup.event
    data = letter_data(setup.organization)
    regular, bold = fonts(data.font)
    _hr, heading = fonts(data.heading_font)
    primary = colors.HexColor(data.primary)
    questions = {
        f"q{q.pk}": q for q in Question.objects.filter(setup=setup, pk__in=_question_ids(fields))
    }
    bookings: dict[int, list] = {}
    for b in Booking.objects.filter(registration__setup=setup).order_by("pk"):
        bookings.setdefault(b.registration_id, []).append(b)
    page_w, page_h = A4
    left = (page_w - cols * width * mm) / 2
    top = (page_h - rows_per * height * mm) / 2
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(_("Namensschilder: {title}").format(title=event.title))
    people = active(setup)
    per_page = cols * rows_per
    w, h = width * mm, height * mm
    pad = 4 * mm
    for i, p in enumerate(people):
        if i and i % per_page == 0:
            c.showPage()
        slot = i % per_page
        x = left + (slot % cols) * w
        y = page_h - top - (slot // cols + 1) * h
        # Schnittlinie (bei Aufklebern gibt der Bogen sie vor)
        if fmt == "badge":
            c.setStrokeColor(colors.lightgrey)
            c.setLineWidth(0.3)
            c.rect(x, y, w, h)
        inner_top = y + h
        if "event" in fields:
            band = min(9 * mm, h * 0.2)
            c.setFillColor(primary)
            c.rect(x, y + h - band, w, band, stroke=0, fill=1)
            c.setFillColor(colors.white)
            size = fit(c, event.title, heading, 10, w - 2 * pad)
            c.setFont(heading, size)
            c.drawString(x + pad, y + h - band + (band - size) / 2 + 1, event.title)
            inner_top = y + h - band
        qr_size = 0
        if "qr" in fields:
            qr_size = min(h * 0.42, 24 * mm)
            widget = QrCodeWidget(tickets.code(p))
            bx0, by0, bx1, by1 = widget.getBounds()
            drawing = Drawing(
                qr_size,
                qr_size,
                transform=[qr_size / (bx1 - bx0), 0, 0, qr_size / (by1 - by0), 0, 0],
            )
            drawing.add(widget)
            renderPDF.draw(drawing, c, x + w - qr_size - 2 * mm, y + 2 * mm)
        # Zeilen unter dem Namen
        lines: list[str] = []
        for f in fields:
            if f == "club":
                lines.append(_club(p))
            elif f == "price":
                lines.append(p.price_name)
            elif f == "number":
                lines.append(p.registration.display_number)
            elif f == "addons":
                names = [
                    b.name
                    for b in bookings.get(p.registration_id, [])
                    if b.participant_id in (None, p.pk)
                ]
                lines.append(", ".join(names))
            elif f in questions:
                lines.append(_answer(p, questions[f]))
        lines = [line for line in lines if line]
        text_w = w - 2 * pad - (qr_size + 2 * mm if qr_size else 0)
        center = x + pad + text_w / 2
        avail = inner_top - y
        name_size = min(20, max(9, avail / mm * 0.45))
        block = name_size + len(lines) * (name_size * 0.55 + 2)
        cursor = y + avail / 2 + block / 2 - name_size
        if "name" in fields:
            c.setFillColor(colors.black)
            size = fit(c, p.name, bold, name_size, text_w)
            c.setFont(bold, size)
            c.drawCentredString(center, cursor, p.name)
            cursor -= name_size * 0.55 + 4
        c.setFillColor(colors.dimgrey)
        for line in lines:
            size = fit(c, line, regular, max(7, name_size * 0.5), text_w)
            c.setFont(regular, size)
            c.drawCentredString(center, cursor, line)
            cursor -= size + 2
    if not people:
        c.setFont(regular, 11)
        c.drawString(left, page_h - top, _("Keine Personen angemeldet."))
    c.showPage()
    c.save()
    return buf.getvalue()


def _question_ids(fields: list[str]) -> list[int]:
    return [int(f[1:]) for f in fields if f.startswith("q") and f[1:].isdigit()]


def badges_pdf(setup) -> bytes:
    """Namensschilder mit Veranstaltung, Name und Verein, zehn je A4-Seite."""
    return labels_pdf(setup, "badge", list(DEFAULT_FIELDS))


# --- Teilnahmebescheinigungen ---


def certificates_pdf(setup, user=None) -> bytes:
    """Teilnahmebescheinigungen im Briefbogen der Einheit, eine Seite je teilnehmender Person."""
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, Spacer

    from core.i18n import date_text
    from letterhead.data import letter_data
    from letterhead.pdf import LetterDocument, text_styles

    event = setup.event
    org = setup.organization
    data = letter_data(org)
    st = text_styles(data)
    rows, _filtered = present(setup)
    today = timezone.localdate()
    place = _place(event)
    story: list = []
    for i, p in enumerate(rows):
        info = [(_("Datum"), date_text(today))]
        story += LetterDocument.start(data, [p.name], info, i == 0)
        story.append(Paragraph(escape(_("Teilnahmebescheinigung")), st["title"]))
        story.append(Spacer(1, 4 * mm))
        born = (
            _(", geboren am {date},").format(date=date_text(p.birth_date)) if p.birth_date else ""
        )
        text = _(
            "Hiermit bestätigen wir, dass {name}{born} {when} an der Veranstaltung "
            "„{title}“ teilgenommen hat."
        ).format(name=p.name, born=born, when=when_text(event), title=event.title)
        story.append(Paragraph(escape(text), st["body"]))
        if place:
            story.append(Paragraph(escape(_("Ort: {place}").format(place=place)), st["body"]))
        if p.price_name:
            story.append(
                Paragraph(
                    escape(_("Teilnahme als: {price}").format(price=p.price_name)), st["body"]
                )
            )
        story.append(Spacer(1, 12 * mm))
        story.append(
            KeepTogether(
                [
                    Spacer(1, 14 * mm),
                    Paragraph("_" * 36, st["normal"]),
                    Paragraph(escape(_("Unterschrift")), st["small"]),
                    Paragraph(escape(org.name), st["normal"]),
                ]
            )
        )
    if not rows:
        story += LetterDocument.start(data, [], [], True)
        story.append(Paragraph(escape(_("Keine Teilnehmenden.")), st["body"]))
    buf = io.BytesIO()
    LetterDocument(
        buf,
        [data],
        title=_("Teilnahmebescheinigungen: {title}").format(title=event.title),
        author=data.name,
    ).build(story)
    return buf.getvalue()


# --- Qualifikationen ---


def qualification_kinds(org) -> list:
    from qualifications import services as qs
    from qualifications.models import QualificationType

    if not org.keeps_members or not qs.module_on(org):
        return []
    return list(
        QualificationType.objects.filter(organization=org, is_archived=False).order_by(
            "sort_order", "name"
        )
    )


def add_qualification(setup, kind, user, acquired_on: datetime.date | None = None) -> dict:
    """Qualifikation für alle teilnehmenden Mitglieder eintragen. Gäste ohne Mitgliedschaft und
    Personen mit demselben Nachweis am selben Tag werden übersprungen."""
    from audit.log import diff, record, snapshot
    from qualifications import services as qs
    from qualifications.models import Qualification

    org = setup.organization
    acquired_on = acquired_on or _days(setup.event)[1]
    rows, filtered = present(setup)
    members = [p for p in rows if p.membership_id and p.membership.organization_id == org.pk]
    guests = len(rows) - len(members)
    have = set(
        Qualification.objects.filter(
            organization=org,
            kind=kind,
            acquired_on=acquired_on,
            person_id__in=[p.membership.person_id for p in members],
        ).values_list("person_id", flat=True)
    )
    valid_until = qs.add_months(acquired_on, kind.validity_months) if kind.validity_months else None
    created = 0
    with transaction.atomic():
        for p in members:
            person = p.membership.person_id
            if person in have:
                continue
            have.add(person)
            q = Qualification.objects.create(
                organization=org,
                person_id=person,
                kind=kind,
                acquired_on=acquired_on,
                valid_until=valid_until,
                note=_("Teilnahme: {title}").format(title=setup.event.title)[:200]
                if not kind.inspection_only
                else "",
                created_by=user,
            )
            record(org, user, "create", q, diff({}, snapshot(q)), person=p.membership.person)
            created += 1
    return {
        "created": created,
        "existing": len(members) - created,
        "guests": guests,
        "checked_in_only": filtered,
    }
