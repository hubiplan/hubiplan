"""Protokoll freigeben, als PDF erzeugen und ablegen (Schritt V4).

Leitung und Protokollführung bestätigen das Protokoll. Mit der zweiten Bestätigung ist es
freigegeben: Die Beschlüsse bekommen ihre Nummer im Beschlussbuch, das PDF wird mit
Prüfsumme gespeichert und, wenn die Dokumentenablage eingeschaltet ist, im Ordner
„Protokolle“ der Einheit abgelegt. Danach ändert sich das Protokoll nicht mehr.
"""

from __future__ import annotations

import hashlib
import io
from xml.sax.saxutils import escape

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.translation import gettext as _
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

from access.modules import module_on
from core.i18n import date_text, language_of_org
from finance.report import _styles
from organizations.theme import effective_theme

from .models import Meeting, MinutesVersion, Resolution


def user_name(user) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.email


def _text(value: str) -> str:
    return escape(value).replace("\n", "<br/>")


def _votes(r: Resolution) -> str:
    if r.unanimous:
        return _("einstimmig")
    if r.votes_yes is None and r.votes_no is None and r.votes_abstain is None:
        return ""
    return _("Ja {yes}, Nein {no}, Enthaltung {abstain}").format(
        yes=r.votes_yes or 0, no=r.votes_no or 0, abstain=r.votes_abstain or 0
    )


def _result(r: Resolution) -> str:
    if r.kind == Resolution.Kind.ELECTION:
        return _("gewählt") if r.result == Resolution.Result.ACCEPTED else _("nicht gewählt")
    return _("angenommen") if r.result == Resolution.Result.ACCEPTED else _("abgelehnt")


def _attendance_line(meeting: Meeting) -> str:
    from .services import quorum

    records = list(meeting.attendance.all())
    if not records:
        return ""
    voters = [r for r in records if r.voter]
    present = sum(1 for r in voters if r.status in ("present", "delegate"))
    represented = sum(1 for r in voters if r.status == "represented")
    guests = sum(1 for r in records if not r.voter and r.status == "present")
    line = _(
        "{present} Stimmberechtigte anwesend, {represented} vertreten, {guests} Gäste."
    ).format(present=present, represented=represented, guests=guests)
    delegates = [
        f"{r.name} ({r.delegate_name})"
        for r in voters
        if r.status == "delegate" and r.delegate_name
    ]
    if delegates:
        line += " " + _("Durch Vertreter anwesend: {x}.").format(x=", ".join(delegates))
    from .services import voters as eligible

    q = quorum(meeting, eligible(meeting).count(), present + represented)
    if q["rule"]:
        line += " " + (
            _("Die Versammlung war beschlussfähig.")
            if q["reached"]
            else _("Die Versammlung war nicht beschlussfähig.")
        )
    return line


def render(meeting: Meeting, *, draft: bool) -> bytes:
    """Protokoll als PDF in der Sprache der Einheit."""
    org = meeting.organization
    with language_of_org(org):
        return _render(meeting, draft=draft)


def _render(meeting: Meeting, *, draft: bool) -> bytes:
    org = meeting.organization
    event = meeting.event
    st = _styles()
    primary = colors.HexColor(effective_theme(org.ancestors())["primary"])
    unit = org.name
    if meeting.department_id:
        from organizations.models import Department

        dept = Department.objects.filter(pk=meeting.department_id).first()
        if dept is not None:
            unit = f"{dept.name} · {org.name}"
    start = timezone.localtime(event.starts_at)
    end = timezone.localtime(event.ends_at)
    title = _("Protokoll: {title}").format(title=event.title)
    story: list = [Paragraph(f"<b>{escape(title)}</b>", st["title"])]
    if draft:
        note = escape(_("Entwurf, noch nicht freigegeben"))
        story.append(Paragraph(f'<font color="#b00020"><b>{note}</b></font>', st["normal"]))
    story.append(Paragraph(escape(unit), st["normal"]))
    story.append(Spacer(1, 3 * mm))
    head = [
        (_("Datum"), f"{date_text(start)}, {start:%H:%M}–{end:%H:%M}"),
        (_("Ort"), ", ".join(p for p in (event.location, event.address) if p)),
        (_("Leitung"), meeting.chair),
        (_("Protokollführung"), meeting.minute_taker),
        (_("Anwesenheit"), _attendance_line(meeting)),
    ]
    rows = [
        [Paragraph(f"<b>{escape(k)}</b>", st["normal"]), Paragraph(escape(v), st["normal"])]
        for k, v in head
        if v
    ]
    if rows:
        story.append(
            Table(
                rows,
                colWidths=[35 * mm, 135 * mm],
                hAlign="LEFT",
                style=[("VALIGN", (0, 0), (-1, -1), "TOP")],
            )
        )
    resolutions: dict[int, list[Resolution]] = {}
    for r in meeting.resolutions.all():
        resolutions.setdefault(r.agenda_item_id, []).append(r)
    # Unterpunkte (TOP 8.1) etwas kleiner und eingerückt unter ihrem Punkt
    sub_heading = ParagraphStyle("h3", parent=st["h2"], fontSize=10, leading=13, leftIndent=6 * mm)
    sub_normal = ParagraphStyle("ns", parent=st["normal"], leftIndent=6 * mm)
    for item in meeting.agenda.all():
        heading = _("TOP {n}: {title}").format(n=item.number or item.position, title=item.title)
        if item.level:
            head_style, body_style = sub_heading, sub_normal
        else:
            head_style, body_style = st["h2"], st["normal"]
        story.append(Paragraph(f"<b>{escape(heading)}</b>", head_style))
        if item.minutes:
            story.append(Paragraph(_text(item.minutes), body_style))
        for r in resolutions.get(item.pk, []):
            if r.kind == Resolution.Kind.ELECTION:
                label = _("Wahl {office}: {name}").format(office=r.office, name=r.elected_name)
            else:
                label = _("Beschluss")
            if r.number:
                label += f" {r.number}"
            outcome = ", ".join(p for p in (_votes(r), _result(r)) if p)
            body = "" if r.kind == Resolution.Kind.ELECTION else f" {_text(r.text)}"
            story.append(
                Paragraph(
                    f"<b>{escape(label)}</b>{body} <i>({escape(outcome)})</i>",
                    body_style,
                )
            )
    story.append(Spacer(1, 8 * mm))
    for who, user, at in (
        (_("Leitung"), meeting.chair_confirmed_by, meeting.chair_confirmed_at),
        (_("Protokollführung"), meeting.taker_confirmed_by, meeting.taker_confirmed_at),
    ):
        if at:
            line = _("{role}: bestätigt von {name} am {day}").format(
                role=who, name=user_name(user), day=date_text(timezone.localtime(at))
            )
            story.append(Paragraph(escape(line), st["normal"]))
    story.append(
        Paragraph(
            escape(_("Erstellt am {day} in HUBIplan.").format(day=date_text(timezone.localdate()))),
            st["small"],
        )
    )
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, title=title
    )
    doc.build(story, onFirstPage=_line(primary), onLaterPages=_line(primary))
    return buf.getvalue()


def _line(primary):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(primary)
        canvas.setLineWidth(0.8)
        canvas.line(20 * mm, 12 * mm, A4[0] - 20 * mm, 12 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(A4[0] - 20 * mm, 8 * mm, str(doc.page))
        canvas.restoreState()

    return draw


def number_resolutions(meeting: Meeting) -> None:
    """Beschlüsse fortlaufend je Einheit und Jahr nummerieren (Beschlussbuch, z. B. 2027/03)."""
    year = timezone.localtime(meeting.event.starts_at).year
    prefix = f"{year}/"
    used = Resolution.objects.filter(
        organization=meeting.organization,
        meeting__department_id=meeting.department_id,
        number__startswith=prefix,
    ).values_list("number", flat=True)
    seq = max((int(n[len(prefix) :]) for n in used if n[len(prefix) :].isdigit()), default=0)
    for r in meeting.resolutions.order_by("agenda_item__position", "position", "pk"):
        seq += 1
        r.number = f"{prefix}{seq:02d}"
        r.save(update_fields=["number"])


def file_document(meeting: Meeting, content: bytes, user):
    """Im Ordner „Protokolle“ der Einheit ablegen, wenn die Ablage eingeschaltet ist."""
    from documents import services as docs
    from documents.models import Document, DocumentVersion, Folder

    org = meeting.organization
    if not module_on(org, "docs"):
        return None
    try:
        docs.check_budget(org, len(content))
    except DjangoValidationError:
        return None
    folder_name = _("Protokolle")
    folder = Folder.objects.filter(
        organization=org, department_id=meeting.department_id, name=folder_name
    ).first()
    if folder is None:
        folder = Folder.objects.create(
            organization=org,
            department_id=meeting.department_id,
            name=folder_name,
            visibility=Folder.Visibility.BOARD,
            public_key=Folder.new_key(),
            created_by=user,
        )
    start = timezone.localtime(meeting.event.starts_at)
    document = Document.objects.create(
        organization=org,
        department_id=meeting.department_id,
        folder=folder,
        title=_("Protokoll {title}").format(title=meeting.event.title)[:200],
        date=start.date(),
        created_by=user,
    )
    name = f"protokoll-{start:%Y-%m-%d}-{meeting.pk}.pdf"
    file = DocumentVersion(
        organization=org,
        department_id=meeting.department_id,
        document=document,
        name=name,
        size=len(content),
        content_type="application/pdf",
        uploaded_by=user,
    )
    file.file.save(docs.storage_name(name), ContentFile(content), save=False)
    file.save()
    return document


def release(meeting: Meeting, user) -> MinutesVersion:
    number_resolutions(meeting)
    meeting.status = Meeting.Status.DONE
    meeting.save(update_fields=["status", "updated_at"])
    content = render(meeting, draft=False)
    version = MinutesVersion(
        organization=meeting.organization,
        meeting=meeting,
        number=meeting.minutes_versions.count() + 1,
        sha256=hashlib.sha256(content).hexdigest(),
    )
    version.file.save(f"protokoll-{meeting.pk}.pdf", ContentFile(content), save=False)
    version.save()
    with language_of_org(meeting.organization):
        document = file_document(meeting, content, user)
    if document is not None:
        version.document = document
        version.save(update_fields=["document"])
    # Fristenkalender: nach einer Vorstandswahl die Anmeldung beim Registergericht
    from obligations.election import after_release

    after_release(meeting, user)
    return version
