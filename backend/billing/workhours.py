"""Arbeitsstunden mit Ersatzbeitrag (docs/arbeitsstunden.md).

Je Mitgliedsart gibt es Pflichtstunden im Geschäftsjahr und einen Ersatzbeitrag je fehlender
Stunde (``WorkHourRule``). Geleistet sind die Stunden aus Helferschichten, die als erledigt
markiert sind. Wer nur einen Teil des Jahres Mitglied war, schuldet anteilig je angefangenem
Monat. Fehlende Stunden kommen als eigener Posten in den ersten Beitragslauf des folgenden
Geschäftsjahres.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext

from access.modules import module_on
from members.models import Membership

from .models import ZERO, BillingSettings, WorkHourRule

CENT = Decimal("0.01")
HOUR = Decimal(60)


@dataclass
class Balance:
    membership_id: int
    name: str
    member_type: str
    required: Decimal  # Stunden, anteilig
    done_minutes: int
    missing: Decimal  # Stunden
    rate: Decimal
    amount: Decimal

    @property
    def done(self) -> Decimal:
        return (Decimal(self.done_minutes) / HOUR).quantize(CENT, ROUND_HALF_UP)


def active(org) -> bool:
    """Gibt es Pflichtstunden und werden Helferdienste geführt?"""
    if not module_on(org, "helpers"):
        return False
    return WorkHourRule.objects.filter(organization=org, hours__gt=0).exists()


def hours_text(value: Decimal) -> str:
    """Stunden wie „4“, „2,5“ oder „1,25“ (deutsche Schreibweise auf der Rechnung)."""
    text = f"{value.quantize(CENT, ROUND_HALF_UP):f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") or "0"


def euro_text(value: Decimal) -> str:
    return f"{value:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _months(spans, start: datetime.date) -> int:
    """Angefangene Monate des Geschäftsjahres, in denen die Mitgliedschaft bestand."""
    from .services import add_months

    count = 0
    for k in range(12):
        m_start = add_months(start, k)
        m_end = add_months(start, k + 1) - datetime.timedelta(days=1)
        if any(
            s.entry_date <= m_end and (s.exit_date is None or s.exit_date >= m_start) for s in spans
        ):
            count += 1
    return count


def _type_at_end(membership, spans, start, end):
    """Mitgliedsart am letzten Tag der Mitgliedschaft im Geschäftsjahr."""
    last = min(end, max((s.exit_date or end) for s in spans))
    candidates = [
        a
        for a in membership.type_assignments.all()
        if a.valid_from <= last and (a.valid_until is None or a.valid_until >= start)
    ]
    if not candidates:
        return None
    current = [a for a in candidates if a.valid_until is None or a.valid_until >= last]
    return max(current or candidates, key=lambda a: a.valid_from).member_type


def done_minutes(org, ids, start: datetime.date, end: datetime.date) -> dict[int, int]:
    """Geleistete Minuten je Mitgliedschaft aus erledigten Helferschichten im Zeitraum."""
    from helpers.models import ShiftAssignment

    tz = timezone.get_current_timezone()
    since = datetime.datetime.combine(start, datetime.time.min, tzinfo=tz)
    until = datetime.datetime.combine(
        end + datetime.timedelta(days=1), datetime.time.min, tzinfo=tz
    )
    result: dict[int, int] = {}
    rows = ShiftAssignment.objects.filter(
        membership_id__in=ids,
        status=ShiftAssignment.Status.ACTIVE,
        done=True,
        shift__starts_at__gte=since,
        shift__starts_at__lt=until,
    ).values_list("membership_id", "shift__starts_at", "shift__ends_at")
    for membership_id, starts, ends in rows:
        minutes = max(int((ends - starts).total_seconds() // 60), 0)
        result[membership_id] = result.get(membership_id, 0) + minutes
    return result


def balances(org, year: int, ids=None) -> dict[int, Balance]:
    """Soll, geleistet und Ersatzbeitrag je Mitgliedschaft für das Geschäftsjahr ``year``.

    Enthält alle Mitglieder mit Pflichtstunden, auch die ohne fehlende Stunden.
    ``ids``: nur diese Mitgliedschaften (Beitragslauf)."""
    if not module_on(org, "helpers"):
        return {}
    rules = {
        r.member_type_id: r for r in WorkHourRule.objects.filter(organization=org, hours__gt=0)
    }
    if not rules:
        return {}
    cfg = BillingSettings.objects.filter(organization=org).first()
    min_age = cfg.work_min_age if cfg else None
    max_age = cfg.work_max_age if cfg else None
    start, end = org.fiscal_range(year)
    qs = (
        Membership.objects.filter(organization=org, purged_at__isnull=True)
        .filter(
            Q(periods__entry_date__lte=end)
            & (Q(periods__exit_date__isnull=True) | Q(periods__exit_date__gte=start))
        )
        .distinct()
        .select_related("person")
        .prefetch_related("periods", "type_assignments__member_type")
    )
    if ids is not None:
        qs = qs.filter(pk__in=ids)
    members = list(qs)
    minutes = done_minutes(org, [m.pk for m in members], start, end)
    from .services import age_on

    result: dict[int, Balance] = {}
    for m in members:
        person = m.person
        if person.is_organization:
            continue
        spans = [
            s
            for s in m.periods.all()
            if s.entry_date <= end and (s.exit_date is None or s.exit_date >= start)
        ]
        if not spans:
            continue
        member_type = _type_at_end(m, spans, start, end)
        rule = rules.get(member_type.pk) if member_type else None
        if rule is None:
            continue
        if person.birth_date and (min_age is not None or max_age is not None):
            age = age_on(person.birth_date, start)
            if min_age is not None and age < min_age:
                continue
            if max_age is not None and age > max_age:
                continue
        months = _months(spans, start)
        required = (rule.hours * months / Decimal(12)).quantize(CENT, ROUND_HALF_UP)
        done = minutes.get(m.pk, 0)
        missing = max(required - Decimal(done) / HOUR, ZERO).quantize(CENT, ROUND_HALF_UP)
        result[m.pk] = Balance(
            membership_id=m.pk,
            name=f"{person.last_name}, {person.first_name}",
            member_type=member_type.name,
            required=required,
            done_minutes=done,
            missing=missing,
            rate=rule.rate,
            amount=(missing * rule.rate).quantize(CENT, ROUND_HALF_UP),
        )
    return result


def line_text(org, year: int) -> str:
    return gettext("Ersatzbeitrag für fehlende Arbeitsstunden {year}").format(
        year=org.fiscal_label(year)
    )


def line_detail(b: Balance) -> str:
    return gettext("Soll {required} Std., geleistet {done} Std.: {missing} Std. × {rate}").format(
        required=hours_text(b.required),
        done=hours_text(b.done),
        missing=hours_text(b.missing),
        rate=euro_text(b.rate),
    )
