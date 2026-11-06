"""Fachlogik der Helferdienste: Personen suchen, Einteilungen prüfen, Schichten zählen."""

from __future__ import annotations

import datetime

from django.utils import timezone
from django.utils.translation import gettext as _

from .models import HelperPlan, Shift, ShiftAssignment


def person_name(membership) -> str:
    person = membership.person
    return f"{person.first_name} {person.last_name}".strip()


def members(scope):
    """Aktuelle Mitglieder, die eingeteilt werden können (in einer Untereinheit nur deren)."""
    from circulars.recipients import club_base
    from members.models import Membership
    from organizations.models import Department

    if scope.org.type != "club":
        return Membership.objects.none()
    department = Department.objects.get(pk=scope.department_id) if scope.department_id else None
    return club_base(scope.org, department)


def age_on(birth_date: datetime.date | None, day: datetime.date) -> int | None:
    if birth_date is None:
        return None
    return day.year - birth_date.year - ((day.month, day.day) < (birth_date.month, birth_date.day))


def active(qs):
    return qs.filter(status=ShiftAssignment.Status.ACTIVE)


def taken(shift: Shift) -> int:
    return active(shift.assignments).count()


def overlapping(shift: Shift, membership_id: int, *, exclude: int | None = None):
    """Andere Schichten derselben Person, die sich zeitlich überschneiden (alle Pläne)."""
    qs = active(
        ShiftAssignment.objects.filter(
            organization_id=shift.organization_id,
            membership_id=membership_id,
            shift__starts_at__lt=shift.ends_at,
            shift__ends_at__gt=shift.starts_at,
        )
    ).exclude(shift__duty__plan__status=HelperPlan.Status.CLOSED)
    if exclude:
        qs = qs.exclude(pk=exclude)
    return qs.select_related("shift__duty")


def shift_label(shift: Shift) -> str:
    start = timezone.localtime(shift.starts_at)
    end = timezone.localtime(shift.ends_at)
    return f"{shift.duty.name} {start:%d.%m. %H:%M}–{end:%H:%M}"


def warnings(shift: Shift, membership=None) -> list[dict]:
    """Hinweise vor einer Einteilung: Schicht voll, Überschneidung, Mindestalter."""
    found = []
    if taken(shift) >= shift.needed:
        found.append({"code": "full", "text": _("Die Schicht ist schon voll besetzt.")})
    if membership is None:
        return found
    for other in overlapping(shift, membership.pk):
        if other.shift_id == shift.pk:
            continue
        found.append(
            {
                "code": "overlap",
                "text": _("Überschneidet sich mit {shift}.").format(shift=shift_label(other.shift)),
            }
        )
    min_age = shift.duty.min_age
    if min_age:
        age = age_on(membership.person.birth_date, timezone.localtime(shift.starts_at).date())
        if age is None or age < min_age:
            found.append(
                {
                    "code": "age",
                    "text": _("Für diesen Dienst gilt ein Mindestalter von {age} Jahren.").format(
                        age=min_age
                    ),
                }
            )
    return found


def parse_quick(text: str, day: datetime.date) -> list[tuple[datetime.datetime, datetime.datetime]]:
    """Schnelleingabe „14-18, 18-22, 22-02“: Zeitfenster am Tag, über Mitternacht weiter."""
    tz = timezone.get_current_timezone()
    slots = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            a, b = (p.strip() for p in part.replace("–", "-").split("-", 1))
            start = _time(a)
            end = _time(b)
        except ValueError as exc:
            raise ValueError(part) from exc
        begin = datetime.datetime.combine(day, start, tz)
        finish = datetime.datetime.combine(day, end, tz)
        if finish <= begin:
            finish += datetime.timedelta(days=1)
        slots.append((begin, finish))
    return slots


def _time(value: str) -> datetime.time:
    value = value.lower().removesuffix("uhr").strip()
    if ":" in value:
        h, m = value.split(":", 1)
    else:
        h, m = value, "0"
    hour, minute = int(h), int(m)
    if hour == 24 and minute == 0:
        hour = 0
    return datetime.time(hour, minute)
