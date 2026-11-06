"""Probenhinweise über die vorhandene Ausgangspost, ohne Notenanhänge."""

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext

from core.i18n import language_of
from core.tenancy import rls_bypass, tenant_context
from events import recurrence
from organizations.addresses import base_url
from outbox import mail
from portal.models import PortalAccess

from .models import RehearsalInvitation, RehearsalNotice
from .practice import window


def send_notice(invite, original, kind):
    access = (
        PortalAccess.objects.filter(
            membership_id=invite.musician.membership_id,
            organization=invite.organization,
            user__is_active=True,
        )
        .select_related("user")
        .first()
        if invite.musician.membership_id
        else None
    )
    if (
        not access
        or not invite.active
        or not invite.musician.active
        or not invite.organization.member_portal_enabled
        or not {"music", "events"} <= set(invite.organization.enabled_modules)
        or not invite.musician.membership.current_period()
    ):
        return 0
    with transaction.atomic():
        _, created = RehearsalNotice.objects.get_or_create(
            organization=invite.organization, invitation=invite, original_start=original, kind=kind
        )
    if not created:
        return 0
    with language_of(access.user):
        return int(
            mail.send(
                access.user.email,
                gettext("Musikprobe im Mitgliederbereich"),
                gettext(
                    "Im Mitgliederbereich liegt eine Probeneinteilung oder eine noch offene "
                    "Rückmeldung für Sie vor: {link}"
                ).format(link=f"{base_url(invite.organization)}/mein-bereich"),
                organization=invite.organization,
                kind="termin",
                fail_silently=True,
            )
        )


@shared_task
def invite_notice(pk):
    with rls_bypass():
        invite = (
            RehearsalInvitation.objects.select_related(
                "organization", "musician__membership", "rehearsal__event"
            )
            .filter(pk=pk)
            .first()
        )
    if not invite:
        return 0
    with tenant_context(invite.organization_id):
        return send_notice(invite, invite.rehearsal.event.starts_at, "invite")


@shared_task
def rehearsal_reminders():
    with rls_bypass():
        ids = list(
            RehearsalInvitation.objects.filter(active=True, musician__active=True).values_list(
                "pk", "organization_id"
            )
        )
    count = 0
    now = timezone.now()
    for pk, org_id in ids:
        with tenant_context(org_id):
            invite = RehearsalInvitation.objects.select_related(
                "organization", "musician__membership", "rehearsal__event"
            ).get(pk=pk)
            for o in recurrence.occurrences([invite.rehearsal.event], now, window()[1]):
                if (
                    invite.rehearsal.remind_days
                    and not o.is_cancelled
                    and now < o.starts_at
                    and (o.starts_at - now).total_seconds() <= invite.rehearsal.remind_days * 86400
                    and not invite.responses.filter(original_start=o.original_start).exists()
                ):
                    count += send_notice(invite, o.original_start, "reminder")
    return count
