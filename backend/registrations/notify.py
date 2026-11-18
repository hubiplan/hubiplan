"""Mails zu Anmeldungen: Anmeldebestätigung (mit Rechnung und Kalenderdatei),
Zahlungseingang, Abmeldung. Texte in der Sprache der Einheit, wie ihre Rechnungen."""

from __future__ import annotations

import datetime
import logging
from urllib.parse import urlparse

from django.utils import timezone
from django.utils.translation import gettext as _

from core.i18n import date_text, datetime_text, language_of_org, org_language
from core.tenancy import rls_bypass
from outbox import mail

from .models import Registration

logger = logging.getLogger(__name__)


def euro(value) -> str:
    return f"{value:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _load(pk: int) -> Registration | None:
    with rls_bypass():
        return (
            Registration.objects.select_related(
                "organization", "setup__event", "invoice", "membership__person"
            )
            .filter(pk=pk)
            .first()
        )


def _greeting(reg: Registration) -> str:
    first = reg.membership.person.first_name if reg.membership_id else ""
    return _("Hallo {name},").format(name=first or reg.name)


def _portal_hint(reg: Registration) -> list[str]:
    org = reg.organization
    if reg.membership_id is None or not getattr(org, "member_portal_enabled", False):
        return []
    from organizations.addresses import base_url

    return [
        "",
        _("Deine Anmeldung siehst du jederzeit im Mitgliederbereich: {url}").format(
            url=base_url(org)
        ),
    ]


def persons_lines(reg: Registration) -> list[str]:
    lines = []
    for p in reg.participants.all():
        price = f"{p.price_name}, {euro(p.amount)}" if p.amount else p.price_name
        mark = "" if p.status == "active" else f" ({_('abgemeldet')})"
        lines.append(f"- {p.name}: {price}{mark}")
    return lines


def event_lines(reg: Registration) -> list[str]:
    event = reg.setup.event
    lines = [event.title, datetime_text(event.starts_at)]
    place = ", ".join(x for x in (event.location, event.address) if x)
    if place:
        lines.append(place)
    return lines


def ics(reg: Registration) -> bytes:
    from events import ical
    from events.models import Event
    from events.recurrence import occurrences
    from organizations.addresses import base_url

    event = reg.setup.event
    until = event.ends_at
    if event.repeat_until:
        until = max(
            until,
            timezone.make_aware(datetime.datetime.combine(event.repeat_until, datetime.time.max)),
        )
    items = occurrences(
        Event.objects.filter(pk=event.pk).select_related("organization", "department", "category"),
        event.starts_at - datetime.timedelta(days=1),
        until + datetime.timedelta(days=1),
    )
    host = urlparse(base_url(reg.organization)).hostname or "hubiplan"
    return ical.calendar(event.title, items, host)


def _send(reg: Registration, subject: str, lines: list[str], kind: str, attachments=None) -> bool:
    if not reg.email:
        return False
    org = reg.organization
    return mail.send(
        reg.email,
        subject,
        "\n".join(lines) + "\n",
        organization=org,
        kind=kind,
        attachments=attachments or None,
        reply_to=[org.contact_email] if org.contact_email else None,
        fail_silently=True,
        language=org_language(org),
    )


def confirmation(pk: int) -> bool:
    reg = _load(pk)
    if reg is None or reg.status != Registration.Status.REGISTERED:
        return False
    org = reg.organization
    with rls_bypass(), language_of_org(org):
        event = reg.setup.event
        lines = [
            _greeting(reg),
            "",
            _("vielen Dank für deine Anmeldung ({number}). Sie ist verbindlich.").format(
                number=reg.display_number
            ),
            "",
            *event_lines(reg),
            "",
            _("Angemeldet:"),
            *persons_lines(reg),
        ]
        attachments = []
        invoice = reg.invoice
        if invoice is not None and invoice.number is not None:
            from billing.archive import archived_pdf
            from billing.pdf import filename

            lines += [
                "",
                _("Summe: {total}").format(total=euro(reg.total)),
                _(
                    "Die Rechnung {number} liegt bei. Bitte überweise den Betrag bis {due} "
                    "und gib die Rechnungsnummer an."
                ).format(number=invoice.display_number, due=date_text(invoice.due_date)),
            ]
            try:
                attachments.append((filename(invoice), archived_pdf(invoice), "application/pdf"))
            except Exception:  # noqa: BLE001 – Bestätigung geht auch ohne Anhang raus
                logger.exception("Rechnung zur Anmeldung %s ohne PDF", reg.pk)
        if reg.setup.terms:
            lines += ["", _("Teilnahmebedingungen:"), reg.setup.terms]
        lines += [
            "",
            _("Abmelden kannst du dich bis {when}; danach wende dich bitte an uns.").format(
                when=datetime_text(reg.setup.closes_at)
            ),
            *_portal_hint(reg),
            "",
            org.name,
        ]
        try:
            attachments.append(("termin.ics", ics(reg), "text/calendar"))
        except Exception:  # noqa: BLE001
            logger.exception("Kalenderdatei zur Anmeldung %s", reg.pk)
        subject = _("Anmeldebestätigung: {title}").format(title=event.title)
        sent = _send(reg, subject, lines, "anmeldung", attachments)
        if sent:
            now = timezone.now()
            Registration.objects.filter(pk=reg.pk).update(confirmation_sent_at=now)
            if invoice is not None and invoice.number is not None:
                type(invoice).objects.filter(pk=invoice.pk).update(sent_at=now)
        return sent


def payment_received(pk: int) -> bool:
    reg = _load(pk)
    if reg is None or reg.invoice is None:
        return False
    org = reg.organization
    with rls_bypass(), language_of_org(org):
        invoice = reg.invoice
        lines = [
            _greeting(reg),
            "",
            _("deine Zahlung über {amount} für die Rechnung {number} ist eingegangen.").format(
                amount=euro(invoice.paid), number=invoice.display_number
            ),
            _("Damit ist deine Anmeldung {number} vollständig bezahlt. Vielen Dank!").format(
                number=reg.display_number
            ),
            "",
            *event_lines(reg),
            "",
            *persons_lines(reg),
            *_portal_hint(reg),
            "",
            org.name,
        ]
        subject = _("Zahlung eingegangen: {title}").format(title=reg.setup.event.title)
        return _send(reg, subject, lines, "zahlungsbestaetigung")


def _invoice_attachment(invoice, lines: list[str], text: str) -> list:
    from billing.archive import archived_pdf
    from billing.pdf import filename

    try:
        content = archived_pdf(invoice)
    except Exception:  # noqa: BLE001 – Mail geht auch ohne Anhang raus
        logger.exception("Rechnung %s ohne PDF", invoice.pk)
        return []
    lines += ["", text]
    return [(filename(invoice), content, "application/pdf")]


def waitlisted(pk: int) -> bool:
    """Auf der Warteliste: Platz in der Reihe, noch keine Rechnung."""
    from .services import waitlist_position

    reg = _load(pk)
    if reg is None or reg.status != Registration.Status.WAITING:
        return False
    org = reg.organization
    with rls_bypass(), language_of_org(org):
        lines = [
            _greeting(reg),
            "",
            _(
                "danke für deine Anmeldung ({number}). Im Moment sind alle Plätze vergeben; du "
                "stehst auf Platz {position} der Warteliste."
            ).format(number=reg.display_number, position=waitlist_position(reg)),
            _(
                "Wird ein Platz frei, rückst du automatisch verbindlich nach und bekommst eine "
                "Mail mit der Rechnung. Danach kannst du dich noch 48 Stunden kostenfrei abmelden."
            ),
            "",
            *event_lines(reg),
            "",
            _("Auf der Warteliste:"),
            *persons_lines(reg),
            *_portal_hint(reg),
            "",
            org.name,
        ]
        subject = _("Warteliste: {title}").format(title=reg.setup.event.title)
        return _send(reg, subject, lines, "warteliste")


def moved_up(pk: int) -> bool:
    """Von der Warteliste nachgerückt: wie die Anmeldebestätigung, mit 48-Stunden-Hinweis."""
    reg = _load(pk)
    if reg is None or reg.status != Registration.Status.REGISTERED:
        return False
    org = reg.organization
    with rls_bypass(), language_of_org(org):
        event = reg.setup.event
        lines = [
            _greeting(reg),
            "",
            _("gute Nachricht: Für deine Anmeldung {number} ist ein Platz frei geworden.").format(
                number=reg.display_number
            ),
            _("Du bist jetzt verbindlich angemeldet."),
            "",
            *event_lines(reg),
            "",
            _("Angemeldet:"),
            *persons_lines(reg),
        ]
        attachments = []
        invoice = reg.invoice
        if invoice is not None and invoice.number is not None:
            lines += ["", _("Summe: {total}").format(total=euro(reg.total))]
            attachments += _invoice_attachment(
                invoice,
                lines,
                _(
                    "Die Rechnung {number} liegt bei. Bitte überweise den Betrag bis {due} "
                    "und gib die Rechnungsnummer an."
                ).format(number=invoice.display_number, due=date_text(invoice.due_date)),
            )
        if reg.free_cancel_until:
            lines += [
                "",
                _("Passt es dir nicht mehr, kannst du dich bis {when} kostenfrei abmelden.").format(
                    when=datetime_text(reg.free_cancel_until)
                ),
            ]
        lines += [*_portal_hint(reg), "", org.name]
        try:
            attachments.append(("termin.ics", ics(reg), "text/calendar"))
        except Exception:  # noqa: BLE001
            logger.exception("Kalenderdatei zur Anmeldung %s", reg.pk)
        subject = _("Platz frei: {title}").format(title=event.title)
        sent = _send(reg, subject, lines, "anmeldung", attachments)
        if sent:
            now = timezone.now()
            Registration.objects.filter(pk=reg.pk).update(confirmation_sent_at=now)
            if invoice is not None and invoice.number is not None:
                type(invoice).objects.filter(pk=invoice.pk).update(sent_at=now)
        return sent


def cancellation(
    pk: int,
    notice: str = "",
    names: list[str] | None = None,
    new_invoice: int | None = None,
    fee: str = "0",
    old_invoice: int | None = None,
) -> bool:
    """Abmeldung (ganz oder einzelne Personen), Absage des Termins, Verfall unbezahlter
    Anmeldungen, Ende der Warteliste. Mit Stornorechnung, neuer Rechnung und Erstattung."""
    from decimal import Decimal

    reg = _load(pk)
    if reg is None:
        return False
    partial = names is not None
    if not partial and reg.status != Registration.Status.CANCELLED:
        return False
    org = reg.organization
    with rls_bypass(), language_of_org(org):
        event = reg.setup.event
        number = reg.display_number
        if notice == "event":
            intro = _(
                "leider müssen wir „{title}“ absagen. Deine Anmeldung {number} ist damit "
                "aufgehoben:"
            ).format(title=event.title, number=number)
            subject = _("Abgesagt: {title}").format(title=event.title)
        elif notice == "expired":
            intro = _(
                "deine Anmeldung {number} ist verfallen, weil die Teilnahmegebühr nicht "
                "rechtzeitig bezahlt war:"
            ).format(number=number)
            subject = _("Anmeldung verfallen: {title}").format(title=event.title)
        elif notice == "no_place":
            intro = _(
                "leider ist für deine Anmeldung {number} auf der Warteliste kein Platz mehr "
                "frei geworden:"
            ).format(number=number)
            subject = _("Kein Platz frei geworden: {title}").format(title=event.title)
        elif partial:
            intro = _("für deine Anmeldung {number} haben wir abgemeldet: {names}.").format(
                number=number, names=", ".join(names)
            )
            subject = _("Abmeldung bestätigt: {title}").format(title=event.title)
        else:
            intro = _("deine Anmeldung {number} ist abgemeldet:").format(number=number)
            subject = _("Abmeldung bestätigt: {title}").format(title=event.title)
        lines = [_greeting(reg), "", intro, "", *event_lines(reg), "", *persons_lines(reg)]
        attachments = []
        from billing.models import Invoice

        old = Invoice.objects.filter(pk=old_invoice).first() if old_invoice else None
        if old is not None and old.status == "cancelled":
            from billing.archive import archived_cancellation
            from billing.pdf import cancellation_filename

            content = archived_cancellation(old)
            if content:
                attachments.append((cancellation_filename(old), content, "application/pdf"))
                lines += [
                    "",
                    _("Die Stornorechnung {number} liegt bei.").format(
                        number=old.cancellation_number
                    ),
                ]
        new = None
        if new_invoice:
            new = Invoice.objects.filter(pk=new_invoice).first()
        if new is not None and new.number is not None:
            fee_value = Decimal(fee or "0")
            if fee_value > 0:
                lines += [
                    "",
                    _("Nach den Teilnahmebedingungen fällt eine Stornogebühr von {fee} an.").format(
                        fee=euro(fee_value)
                    ),
                ]
            if new.status == "paid":
                text = _(
                    "Die neue Rechnung {number} liegt bei; sie ist mit deiner Zahlung schon "
                    "beglichen."
                ).format(number=new.display_number)
            else:
                text = _(
                    "Die neue Rechnung {number} über {total} liegt bei. Bitte überweise den "
                    "offenen Betrag bis {due}."
                ).format(
                    number=new.display_number,
                    total=euro(new.total),
                    due=date_text(new.due_date),
                )
            attachments += _invoice_attachment(new, lines, text)
        if old is not None and old.status == "cancelled" and old.paid > 0:
            lines.append(
                _("Den schon gezahlten Betrag von {amount} erstatten wir dir.").format(
                    amount=euro(old.paid)
                )
            )
        lines += ["", org.name]
        return _send(reg, subject, lines, "abmeldung", attachments)
