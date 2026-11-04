"""Neutral performance notices through the existing outbox, with retryable state."""

import datetime
import hashlib
import json
import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext

from core.i18n import language_of, user_language
from core.tenancy import rls_bypass, tenant_context
from outbox import mail
from portal.models import PortalAccess

from .availability import performance_interval
from .models import Assignment, Performance, PerformanceNotice

logger = logging.getLogger(__name__)


def fingerprint(row):
    performance, event = row.performance, row.performance.event
    data = {
        "event": [
            event.title,
            event.starts_at,
            event.ends_at,
            event.location,
            event.address,
            event.is_cancelled,
            event.cancel_note,
            event.all_day,
        ],
        "performance": [
            performance.meeting_at,
            performance.meeting_place,
            performance.setup_at,
            performance.uniform,
            performance.formation,
            performance.notes,
        ],
        "position": [row.position.instrument, row.position.register],
        "program": list(
            performance.program_entries.order_by("position", "pk").values_list(
                "kind",
                "arrangement_id",
                "arrangement__piece__title",
                "arrangement__name",
                "arrangement__duration_seconds",
                "duration_seconds",
                "paper_format",
                "note",
            )
        ),
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def recipient(row):
    musician, org = row.musician, row.organization
    if (
        not musician.active
        or not musician.membership_id
        or row.status == "declined"
        or not org.member_portal_enabled
        or not {"music", "events"} <= set(org.enabled_modules)
        or not musician.membership.current_period()
    ):
        return None
    return (
        PortalAccess.objects.select_related("user")
        .filter(
            organization=org,
            membership_id=musician.membership_id,
            user__is_active=True,
        )
        .first()
    )


def send(row, access, kind):
    with language_of(access.user):
        subject = (
            gettext("Neue Auftrittseinteilung im Mitgliederbereich")
            if kind == "invite"
            else gettext("Erinnerung an eine Auftrittsrückmeldung")
            if kind == "reminder"
            else gettext("Auftritt abgesagt")
            if kind == "cancelled"
            else gettext("Auftrittsinformationen geändert")
        )
        body = gettext(
            "Im Mitgliederbereich liegen neue oder geänderte Auftrittsinformationen "
            "oder eine noch offene Rückmeldung für Sie vor: {link}"
        ).format(link=f"{settings.FRONTEND_URL}/mein-bereich")
        return mail.send(
            access.user.email,
            subject,
            body,
            organization=row.organization,
            kind="termin",
            language=user_language(access.user),
            fail_silently=True,
        )


@transaction.atomic
def process_assignment(pk):
    initial = Assignment.objects.filter(pk=pk).values_list("performance_id", flat=True).first()
    if not initial:
        return 0
    # Same lock order as assignment editing and member responses.
    Performance.objects.select_for_update().get(pk=initial)
    row = (
        Assignment.objects.select_for_update(of=("self",))
        .select_related(
            "organization",
            "performance__event",
            "musician__membership",
            "position",
        )
        .filter(pk=pk)
        .first()
    )
    if not row:
        return 0
    now = timezone.now()
    start, end = performance_interval(row.performance)
    if end <= now:
        return 0
    access = recipient(row)
    if not access:
        # A later explicit re-request should be noticed, including after a decline.
        PerformanceNotice.objects.filter(assignment=row).update(last_status=row.status)
        return 0
    state, _ = PerformanceNotice.objects.get_or_create(
        assignment=row,
        defaults={"organization": row.organization},
    )
    signature = fingerprint(row)
    if state.fingerprint == "baseline":
        state.fingerprint, state.last_status = signature, row.status
        state.save(update_fields=["fingerprint", "last_status"])
    if state.attempted_at and now - state.attempted_at < datetime.timedelta(minutes=5):
        if row.status != "pending" and state.last_status != row.status:
            state.last_status = row.status
            state.save(update_fields=["last_status"])
        return 0
    changed = state.fingerprint != signature
    requested = row.status == "pending" and state.last_status != "pending"
    if changed or requested:
        kind = "invite" if not state.fingerprint or requested else "changed"
        if row.performance.event.is_cancelled:
            # No initial invitations to an already cancelled event.
            if not state.fingerprint:
                state.fingerprint, state.last_status = signature, row.status
                state.save(update_fields=["fingerprint", "last_status"])
                return 0
            kind = "cancelled"
    elif (
        row.status == "pending"
        and not row.performance.event.is_cancelled
        and row.performance.remind_days
        and now < start
        and (not state.notified_at or now - state.notified_at >= datetime.timedelta(days=1))
        and start - now <= datetime.timedelta(days=row.performance.remind_days)
        and state.reminder_fingerprint != signature
    ):
        kind = "reminder"
    else:
        if state.last_status != row.status:
            state.last_status = row.status
            state.save(update_fields=["last_status"])
        return 0
    state.attempted_at = now
    accepted = send(row, access, kind)
    if accepted:
        if kind == "reminder":
            state.reminder_fingerprint, state.reminded_at = signature, now
        else:
            state.fingerprint, state.notified_at = signature, now
            state.reminder_fingerprint = ""
        state.last_status = row.status
    state.save()
    return int(accepted)


def process_ids(ids):
    count = 0
    for pk, org_id in ids:
        try:
            with tenant_context(org_id):
                count += process_assignment(pk)
        except Exception:
            logger.exception("Auftrittshinweis für Einteilung %s fehlgeschlagen", pk)
    return count


@shared_task
def assignment_notice(pk):
    with rls_bypass():
        ids = list(Assignment.objects.filter(pk=pk).values_list("pk", "organization_id"))
    return process_ids(ids)


@shared_task
def performance_notice(pk):
    with rls_bypass():
        ids = list(
            Assignment.objects.filter(performance_id=pk).values_list("pk", "organization_id")
        )
    return process_ids(ids)


@shared_task
def performance_reminders():
    with rls_bypass():
        ids = list(
            Assignment.objects.filter(
                performance__event__ends_at__gt=timezone.now(),
                musician__active=True,
            ).values_list("pk", "organization_id")
        )
    return process_ids(ids)
