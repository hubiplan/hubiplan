"""Kündigung durch das Mitglied im Mitgliederbereich.

Das Mitglied reicht die Kündigung ein; das frühestmögliche Austrittsdatum folgt aus der
Kündigungsfrist und dem Termin, die der Verein nach seiner Satzung einstellt. Der Verein
bestätigt die Kündigung (dann wird der Austritt eingetragen) oder lehnt sie mit Begründung
ab. Das Mitglied bekommt eine Eingangs- und eine Austrittsbestätigung per Mail.
"""

from __future__ import annotations

import datetime

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext, gettext_noop
from rest_framework.exceptions import ValidationError

from audit.log import record
from core.i18n import date_text, language_of, user_language
from members import workflows
from members.models import ExitReason, Membership, today
from organizations.models import Organization
from outbox import mail

from .models import CancellationRequest

# Wie weit nach dem frühesten Datum ein Mitglied den Austritt legen darf
LATEST_YEARS = 3
STEP_MONTHS = {
    Organization.CancellationEnd.MONTH: 1,
    Organization.CancellationEnd.QUARTER: 3,
    Organization.CancellationEnd.HALF_YEAR: 6,
    Organization.CancellationEnd.YEAR: 12,
}


def earliest_exit(club: Organization, on: datetime.date | None = None) -> datetime.date:
    """Frühestes Austrittsdatum für eine heute eingehende Kündigung.

    Erst die Frist (Monate), dann das nächste Ende des gewählten Abschnitts. Quartal,
    Halbjahr und Jahr zählen ab Beginn des Geschäftsjahres. Beispiel: drei Monate zum
    Jahresende, Kündigung am 12.11.2026 → Austritt zum 31.12.2027."""
    on = on or today()
    base = on + relativedelta(months=club.cancellation_notice_months or 0)
    step = STEP_MONTHS.get(club.cancellation_period_end)
    if step is None:
        return base
    start = club.fiscal_start(club.fiscal_year_of(base))
    while True:
        end = start + relativedelta(months=step) - datetime.timedelta(days=1)
        if end >= base:
            return end
        start += relativedelta(months=step)


def rule_text(club: Organization) -> str:
    """Regel in Worten, z. B. „mit einer Frist von 3 Monaten zum Ende des Geschäftsjahres“."""
    months = club.cancellation_notice_months or 0
    end = Organization.CancellationEnd(club.cancellation_period_end).label
    if months == 0:
        return gettext("ohne Frist {end}").format(end=end)
    if months == 1:
        return gettext("mit einer Frist von einem Monat {end}").format(end=end)
    return gettext("mit einer Frist von {months} Monaten {end}").format(months=months, end=end)


def _open_period(membership: Membership):
    return membership.periods.filter(exit_date__isnull=True).first()


def info(club: Organization, membership: Membership) -> dict:
    """Angaben für „Meine Daten“: darf gekündigt werden, ab wann, offene Kündigung."""
    period = _open_period(membership)
    items = list(CancellationRequest.objects.filter(membership=membership)[:10])
    pending = next((c for c in items if c.status == CancellationRequest.Status.PENDING), None)
    planned_exit = (
        membership.periods.filter(exit_date__isnull=False, exit_date__gte=today())
        .order_by("-exit_date")
        .values_list("exit_date", flat=True)
        .first()
    )
    return {
        "enabled": bool(club.member_cancellation_enabled),
        # Nur mit laufendem Zeitraum ohne eingetragenen Austritt
        "possible": bool(club.member_cancellation_enabled and period and not pending),
        "earliest_date": earliest_exit(club) if period else None,
        "rule": rule_text(club),
        "planned_exit": planned_exit,
        "requests": [request_data(c) for c in items],
    }


def request_data(c: CancellationRequest) -> dict:
    person = c.membership.person
    return {
        "id": c.pk,
        "member_id": c.membership_id,
        "member_name": person.display_name,
        "exit_date": c.exit_date,
        "earliest_date": c.earliest_date,
        "message": c.message,
        "status": c.status,
        "status_label": c.get_status_display(),
        "response": c.response,
        "created_at": c.created_at,
        "decided_at": c.decided_at,
    }


def _date(day: datetime.date) -> str:
    return date_text(day)


def _greeting(c: CancellationRequest) -> str:
    person = c.membership.person
    name = person.first_name if not person.is_organization else person.display_name
    return gettext("Hallo {name},").format(name=name or person.display_name) + "\n\n"


def _send(c: CancellationRequest, subject: str, text: str) -> None:
    """Mail an das Konto, das gekündigt hat (in dessen Sprache)."""
    user = c.user
    if user is None or not user.email:
        return
    mail.send(
        user.email,
        subject,
        text,
        organization=c.organization,
        kind="kuendigung",
        language=user_language(user),
        fail_silently=True,
    )


def _mail_received(c: CancellationRequest) -> None:
    club = c.organization
    with language_of(c.user):
        body = (
            _greeting(c)
            + gettext(
                "{org} hat Ihre Kündigung der Mitgliedschaft erhalten. Gewünschter Austritt: "
                "{date}."
            ).format(org=club.name, date=_date(c.exit_date))
            + "\n\n"
            + gettext(
                "Der Verein prüft die Kündigung und bestätigt sie Ihnen. Bis dahin können Sie "
                "sie im Mitgliederbereich unter „Meine Daten“ zurücknehmen."
            )
            + "\n"
        )
        subject = gettext("Kündigung eingegangen – {org}").format(org=club.name)
    _send(c, subject, body)


def _mail_decided(c: CancellationRequest) -> None:
    club = c.organization
    with language_of(c.user):
        if c.status == CancellationRequest.Status.ACCEPTED:
            subject = gettext("Austrittsbestätigung – {org}").format(org=club.name)
            text = gettext(
                "{org} bestätigt Ihren Austritt zum {date}. Bis dahin bleiben Sie Mitglied."
            ).format(org=club.name, date=_date(c.exit_date))
        else:
            subject = gettext("Kündigung nicht bestätigt – {org}").format(org=club.name)
            text = gettext(
                "{org} hat Ihre Kündigung vom {date} nicht bestätigt. Ihre Mitgliedschaft "
                "läuft weiter."
            ).format(org=club.name, date=_date(timezone.localdate(c.created_at)))
        body = _greeting(c) + text + "\n"
        if c.response:
            body += "\n" + gettext("Nachricht des Vereins: {text}").format(text=c.response) + "\n"
    _send(c, subject, body)


def _check_date(club: Organization, wanted: datetime.date | None) -> tuple:
    earliest = earliest_exit(club)
    exit_date = wanted or earliest
    if exit_date < earliest:
        raise ValidationError(
            {
                "exit_date": gettext("Frühestens zum {date} ({rule}).").format(
                    date=_date(earliest), rule=rule_text(club)
                )
            }
        )
    if exit_date > earliest + relativedelta(years=LATEST_YEARS):
        raise ValidationError(
            {
                "exit_date": gettext("Bitte ein Datum bis zum {date} wählen.").format(
                    date=_date(earliest + relativedelta(years=LATEST_YEARS))
                )
            }
        )
    return exit_date, earliest


@transaction.atomic
def submit(
    club: Organization,
    membership: Membership,
    user,
    exit_date: datetime.date | None,
    message: str = "",
) -> CancellationRequest:
    if not club.member_cancellation_enabled:
        raise ValidationError(
            gettext("Kündigen im Mitgliederbereich ist in diesem Verein nicht eingeschaltet.")
        )
    workflows.lock(membership)
    if _open_period(membership) is None:
        raise ValidationError(
            gettext("Für deine Mitgliedschaft ist schon ein Austritt eingetragen.")
        )
    if CancellationRequest.objects.filter(
        membership=membership, status=CancellationRequest.Status.PENDING
    ).exists():
        raise ValidationError(gettext("Deine Kündigung liegt dem Verein schon vor."))
    exit_date, earliest = _check_date(club, exit_date)
    c = CancellationRequest.objects.create(
        organization=club,
        membership=membership,
        user=user,
        exit_date=exit_date,
        earliest_date=earliest,
        message=message[:500],
    )
    record(
        club,
        user,
        "create",
        c,
        {"Kündigung zum": [None, exit_date.isoformat()]},
        person=membership.person,
    )
    transaction.on_commit(lambda: _mail_received(c))
    return c


@transaction.atomic
def withdraw(club: Organization, membership: Membership, user, pk: int) -> CancellationRequest:
    c = CancellationRequest.objects.select_for_update().filter(membership=membership, pk=pk).first()
    if c is None or c.status != CancellationRequest.Status.PENDING:
        raise ValidationError(gettext("Diese Kündigung ist schon bearbeitet."))
    c.status = CancellationRequest.Status.WITHDRAWN
    c.decided_at = timezone.now()
    c.save(update_fields=["status", "decided_at"])
    changes = {"Kündigung": ["offen", "zurückgenommen"]}
    record(club, user, "update", c, changes, person=membership.person)
    return c


@transaction.atomic
def decide(
    club: Organization,
    c: CancellationRequest,
    user,
    *,
    accept: bool,
    response: str = "",
    exit_date: datetime.date | None = None,
) -> CancellationRequest:
    """Bestätigen (Austritt eintragen) oder ablehnen. Der Verein darf das Datum anpassen."""
    if c.status != CancellationRequest.Status.PENDING:
        raise ValidationError(gettext("Diese Kündigung ist schon bearbeitet."))
    membership = c.membership
    if accept:
        if exit_date is not None:
            c.exit_date = exit_date
        workflows.exit_membership(
            membership,
            c.exit_date,
            ExitReason.EXIT,
            "Kündigung im Mitgliederbereich",
        )
        record(
            club,
            user,
            "update",
            membership,
            {
                "Austritt": [None, c.exit_date.isoformat()],
                "Austrittsgrund": [None, ExitReason.EXIT.label],
            },
            person=membership.person,
        )
        c.status = CancellationRequest.Status.ACCEPTED
    else:
        c.status = CancellationRequest.Status.REJECTED
    c.response = response[:500]
    c.decided_by = user
    c.decided_at = timezone.now()
    c.save()
    from devices.push import notify_membership

    notify_membership(
        membership.pk,
        gettext_noop("Deine Kündigung wurde bestätigt")
        if accept
        else gettext_noop("Deine Kündigung wurde nicht bestätigt"),
        c.response or club.name,
    )
    transaction.on_commit(lambda: _mail_decided(c))
    return c
