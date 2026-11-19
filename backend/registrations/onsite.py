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


# --- Namensschilder ---

BADGE_W, BADGE_H = 85, 54  # mm, Visitenkartenformat für übliche Namensschildhüllen
COLS, ROWS = 2, 5


def badges_pdf(setup) -> bytes:
    """Namensschilder aller Personen verbindlicher Anmeldungen, zehn je A4-Seite."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    from letterhead.data import letter_data
    from letterhead.pdf import fit, fonts

    event = setup.event
    data = letter_data(setup.organization)
    regular, bold = fonts(data.font)
    _hr, heading = fonts(data.heading_font)
    primary = colors.HexColor(data.primary)
    page_w, page_h = A4
    left = (page_w - COLS * BADGE_W * mm) / 2
    top = (page_h - ROWS * BADGE_H * mm) / 2
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(_("Namensschilder: {title}").format(title=event.title))
    rows = active(setup)
    per_page = COLS * ROWS
    for i, p in enumerate(rows):
        if i and i % per_page == 0:
            c.showPage()
        slot = i % per_page
        x = left + (slot % COLS) * BADGE_W * mm
        y = page_h - top - (slot // COLS + 1) * BADGE_H * mm
        w, h = BADGE_W * mm, BADGE_H * mm
        pad = 5 * mm
        # Schnittlinie
        c.setStrokeColor(colors.lightgrey)
        c.setLineWidth(0.3)
        c.rect(x, y, w, h)
        # Kopf: Veranstaltung in Vereinsfarbe
        c.setFillColor(primary)
        c.rect(x, y + h - 9 * mm, w, 9 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        size = fit(c, event.title, heading, 10, w - 2 * pad)
        c.setFont(heading, size)
        c.drawString(x + pad, y + h - 6 * mm, event.title)
        # Name groß, Verein darunter
        c.setFillColor(colors.black)
        size = fit(c, p.name, bold, 20, w - 2 * pad)
        c.setFont(bold, size)
        c.drawCentredString(x + w / 2, y + h / 2 - 4 * mm, p.name)
        club = p.membership.organization.name if p.membership_id else ""
        if club:
            c.setFillColor(colors.dimgrey)
            size = fit(c, club, regular, 10, w - 2 * pad)
            c.setFont(regular, size)
            c.drawCentredString(x + w / 2, y + h / 2 - 11 * mm, club)
    if not rows:
        c.setFont(regular, 11)
        c.drawString(left, page_h - top, _("Keine Personen angemeldet."))
    c.showPage()
    c.save()
    return buf.getvalue()


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
