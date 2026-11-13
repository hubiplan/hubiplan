"""Fristen weiterschieben, zuständige Personen finden."""

from __future__ import annotations

import calendar
import datetime

from .access import EDIT
from .models import Obligation


def add_months(day: datetime.date, months: int) -> datetime.date:
    absolute = day.year * 12 + day.month - 1 + months
    year, month0 = divmod(absolute, 12)
    last = calendar.monthrange(year, month0 + 1)[1]
    # Monatsletzter bleibt Monatsletzter (31.01. → 28./29.02. → 31.03. über den Anker)
    keep_last = day.day == calendar.monthrange(day.year, day.month)[1]
    return datetime.date(year, month0 + 1, last if keep_last else min(day.day, last))


def next_due(obligation: Obligation, done_on: datetime.date) -> datetime.date | None:
    """Nächste Frist nach Erledigung; verpasste Fristen überspringen. Einmalig: keine."""
    if not obligation.interval_months or obligation.due_date is None:
        return None
    due = add_months(obligation.due_date, obligation.interval_months)
    while due <= done_on:
        due = add_months(due, obligation.interval_months)
    return due


def responsible_users(obligation: Obligation, on: datetime.date | None = None):
    """Inhaber der zuständigen Rolle; ohne Rolle alle, die den Fristenkalender pflegen."""
    from access.models import Role, RoleAssignment

    if obligation.role_id:
        roles = [obligation.role_id]
    else:
        roles = [
            r.pk
            for r in Role.objects.filter(
                organization_id=obligation.organization_id, department__isnull=True
            )
            if EDIT in (r.permissions or [])
        ]
    users = {}
    for a in (
        RoleAssignment.objects.active(on)
        .filter(role_id__in=roles, user__isnull=False, user__is_active=True)
        .select_related("user")
    ):
        users[a.user_id] = a.user
    return list(users.values())


def holds_role(user, obligation: Obligation) -> bool:
    from access.models import RoleAssignment

    if not obligation.role_id:
        return False
    return RoleAssignment.objects.active().filter(role_id=obligation.role_id, user=user).exists()


def due_soon(org, today: datetime.date):
    """Pflichten mit Frist, deren Erinnerungszeitraum begonnen hat."""
    rows = Obligation.objects.filter(
        organization=org, active=True, trigger=Obligation.Trigger.DATE, due_date__isnull=False
    ).select_related("role")
    return [o for o in rows if o.due_date - datetime.timedelta(days=o.remind_days) <= today]
