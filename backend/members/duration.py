"""Mitgliedsdauer und Jubiläen (Meilenstein 4).

- Dauer im Verein: Summe der Zeiträume, in denen eine Art galt, die „zählt für
  Mitgliedsdauer“ trägt.
- Dauer im Dachverband: alle gemeldeten Zeiten in allen seinen Vereinen
  (Überschneidungen zählen einmal), je nach Regel des Dachverbands alle
  gemeldeten oder nur gemeldete aktive Zeiten.
- Jubiläum: der Tag, an dem die gezählte Zeit N Jahre erreicht. Lücken
  verschieben das Jubiläum entsprechend nach hinten.
- Genauigkeit (je Organisation): tagesgenau wie oben; monats- oder jahresgenau
  zählen ganze Monate bzw. Jahre (angefangene zählen voll), das Jubiläum fällt
  dann auf einen ganzen Monat bzw. ein ganzes Jahr (Eintritt 2001 → 25 Jahre
  im ganzen Jahr 2026). Gespeichert bleibt alles tagesgenau.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from dateutil.relativedelta import relativedelta

from core.tenancy import rls_bypass
from organizations.models import Organization

from .models import (
    Membership,
    MembershipPeriod,
    MemberType,
    MemberTypeAssignment,
    overlaps,
    today,
)

Range = tuple[datetime.date, datetime.date | None]


def merge(ranges: Iterable[Range]) -> list[Range]:
    """Überschneidende oder angrenzende Zeiträume zusammenfassen."""
    result: list[list] = []
    for start, end in sorted(ranges, key=lambda r: r[0]):
        if result:
            last = result[-1]
            last_end = last[1]
            if last_end is None or start <= last_end + datetime.timedelta(days=1):
                if last_end is not None and (end is None or end > last_end):
                    last[1] = end
                continue
        result.append([start, end])
    return [(s, e) for s, e in result]


def counted_ranges(membership: Membership, predicate) -> list[Range]:
    """Teile der Zeiträume, in denen eine Art galt, die ``predicate`` erfüllt."""
    return merge(
        _counted(
            [(p.entry_date, p.exit_date) for p in membership.periods.all()],
            [
                (ta.valid_from, ta.valid_until, ta.member_type)
                for ta in membership.type_assignments.all()
            ],
            predicate,
        )
    )


def _counted(periods, assignments, predicate) -> list[Range]:
    """Wie ``counted_ranges``, aus einfachen Tupeln und ohne Zusammenfassen."""
    ranges = []
    for entry, exit_ in periods:
        for valid_from, valid_until, member_type in assignments:
            if not predicate(member_type):
                continue
            if overlaps(entry, exit_, valid_from, valid_until):
                ends = [d for d in (exit_, valid_until) if d]
                ranges.append((max(entry, valid_from), min(ends) if ends else None))
    return ranges


def days_in(ranges: list[Range], until: datetime.date) -> int:
    total = 0
    for start, end in ranges:
        if start > until:
            continue
        stop = min(end, until) if end else until
        total += (stop - start).days + 1
    return total


DAY, MONTH, YEAR = "day", "month", "year"


def _unit(d: datetime.date, precision: str) -> int:
    return d.year * 12 + d.month - 1 if precision == MONTH else d.year


def _unit_start(index: int, precision: str) -> datetime.date:
    if precision == MONTH:
        return datetime.date(index // 12, index % 12 + 1, 1)
    return datetime.date(index, 1, 1)


def unit_end(d: datetime.date, precision: str) -> datetime.date:
    """Letzter Tag des Monats bzw. Jahres, in dem ``d`` liegt (tagesgenau: ``d``)."""
    if precision == MONTH:
        return d.replace(day=1) + relativedelta(months=1, days=-1)
    if precision == YEAR:
        return datetime.date(d.year, 12, 31)
    return d


def jubilee_date(ranges: list[Range], years: int, precision: str = DAY) -> datetime.date | None:
    """Tag, an dem die gezählte Zeit ``years`` Jahre erreicht (kann in der Zukunft liegen).

    Monats-/jahresgenau: erster Tag des Monats bzw. Jahres, in dem das Jubiläum liegt.
    """
    if not ranges:
        return None
    try:
        return _jubilee_date(ranges, years, precision)
    except (OverflowError, ValueError):
        return None  # liegt jenseits des darstellbaren Kalenders (Jahr 9999)


def _jubilee_date(ranges: list[Range], years: int, precision: str) -> datetime.date | None:
    if precision in (MONTH, YEAR):
        return _unit_jubilee(ranges, years, precision)
    first = ranges[0][0]
    needed = (first + relativedelta(years=years) - first).days
    counted = 0
    for start, end in ranges:
        length = None if end is None else (end - start).days + 1
        if length is None or counted + length >= needed:
            return start + datetime.timedelta(days=needed - counted)
        counted += length
    return None  # mit den bisherigen (beendeten) Zeiten nicht erreicht


def _unit_jubilee(ranges: list[Range], years: int, precision: str) -> datetime.date | None:
    units: list[list] = []
    for start, end in ranges:
        s, e = _unit(start, precision), (None if end is None else _unit(end, precision))
        if units and (units[-1][1] is None or s <= units[-1][1] + 1):
            if units[-1][1] is not None and (e is None or e > units[-1][1]):
                units[-1][1] = e
            continue
        units.append([s, e])
    needed = years * (12 if precision == MONTH else 1)
    counted = 0
    for s, e in units:
        length = None if e is None else e - s + 1
        if length is None or counted + length >= needed:
            return _unit_start(s + needed - counted, precision)
        counted += length
    return None


@dataclass
class Duration:
    days: int
    years: int
    ranges: list[Range]

    @classmethod
    def of(cls, ranges: list[Range], on: datetime.date, precision: str = DAY) -> Duration:
        days = days_in(ranges, on)
        years = 0
        while True:
            d = jubilee_date(ranges, years + 1, precision)
            if d is None or d > on:
                break
            years += 1
        return cls(days=days, years=years, ranges=ranges)


def _club_counts(member_type) -> bool:
    return member_type.counts_for_duration


def club_ranges(membership: Membership) -> list[Range]:
    return counted_ranges(membership, _club_counts)


def federation_predicate(federation: Organization):
    only_active = federation.federation_duration_rule == "active_reported"
    return lambda t: t.reported and (t.active or not only_active)


def federation_ranges(person, federation: Organization) -> list[Range]:
    """Gemeldete Zeiten der Person in allen Vereinen des Dachverbands (Systemabfrage)."""
    predicate = federation_predicate(federation)
    ranges: list[Range] = []
    with rls_bypass():
        memberships = Membership.objects.filter(person=person, scope=federation).prefetch_related(
            "periods", "type_assignments__member_type"
        )
        for membership in memberships:
            ranges.extend(counted_ranges(membership, predicate))
    return merge(ranges)


def duration_info(membership: Membership, on: datetime.date | None = None) -> dict:
    on = on or today()
    club = membership.organization
    club_d = Duration.of(club_ranges(membership), on, club.date_precision)
    info = {
        "club": {
            "days": club_d.days,
            "years": club_d.years,
            "precision": club.date_precision,
            "next": next_jubilee(club_d.ranges, club.jubilee_years, on, club.date_precision),
        },
        "federation": None,
    }
    federation = club.federation
    if federation is not None:
        fed_p = federation.date_precision
        fed_d = Duration.of(federation_ranges(membership.person, federation), on, fed_p)
        info["federation"] = {
            "days": fed_d.days,
            "years": fed_d.years,
            "precision": fed_p,
            "rule": federation.get_federation_duration_rule_display(),
            "next": next_jubilee(fed_d.ranges, federation.jubilee_years, on, fed_p),
        }
    return info


def next_jubilee(
    ranges: list[Range], levels: list[int], on: datetime.date, precision: str = DAY
) -> dict | None:
    for years in sorted(levels):
        d = jubilee_date(ranges, years, precision)
        if d and d > on:
            return {"years": years, "date": d}
    return None


def _history(memberships) -> tuple[dict[int, list], dict[int, list]]:
    """Zeiträume und Artzuordnungen je Mitgliedschaft, als einfache Tupel."""

    periods: dict[int, list] = defaultdict(list)
    for mid, entry, exit_ in MembershipPeriod.objects.filter(
        membership__in=memberships
    ).values_list("membership_id", "entry_date", "exit_date"):
        periods[mid].append((entry, exit_))
    rows = list(
        MemberTypeAssignment.objects.filter(membership__in=memberships).values_list(
            "membership_id", "valid_from", "valid_until", "member_type_id"
        )
    )
    types = MemberType.objects.in_bulk({row[3] for row in rows})
    assignments: dict[int, list] = defaultdict(list)
    for mid, valid_from, valid_until, type_id in rows:
        assignments[mid].append((valid_from, valid_until, types[type_id]))
    return periods, assignments


def _federation_ranges_of(memberships, federation: Organization) -> dict[int, list[Range]]:
    """Wie ``federation_ranges``, für alle Personen der Mitgliedschaften in wenigen
    Abfragen statt einer je Mitglied (Systemabfrage)."""
    predicate = federation_predicate(federation)
    raw: dict[int, list[Range]] = defaultdict(list)
    with rls_bypass():
        everywhere = Membership.objects.filter(
            scope=federation, person__in=memberships.values("person_id")
        )
        periods, assignments = _history(everywhere)
        for mid, person_id in everywhere.order_by().values_list("pk", "person_id"):
            raw[person_id].extend(
                _counted(periods.get(mid, []), assignments.get(mid, []), predicate)
            )
    return {person_id: merge(ranges) for person_id, ranges in raw.items()}


def jubilees_between(club: Organization, start: datetime.date, end: datetime.date) -> list[dict]:
    """Jubiläen der Mitglieder eines Vereins im Zeitraum [start, end], die am Jubiläum
    selbst Mitglied waren.

    Enthält die Vereinsjubiläen und – bei Vereinen im Dachverband – die
    Dachverbandsjubiläen nach dessen Stufen und Regel. Monats-/jahresgenau
    zählt ein Jubiläum, wenn sein Monat bzw. Jahr den Zeitraum berührt.
    """
    # Zeiträume und Arten aller Mitglieder als einfache Zeilen (ohne Modellobjekte, ohne
    # Namen); Personen werden erst für die Treffer geladen und entschlüsselt
    # (Gesamtaudit 11.11., P-03).
    memberships = Membership.objects.filter(organization=club, purged_at__isnull=True)
    periods, assignments = _history(memberships)
    federation = club.federation
    fed_levels = federation.jubilee_years if federation else []
    fed_ranges = _federation_ranges_of(memberships, federation) if fed_levels else {}
    precision = club.date_precision
    hits = []
    for mid, person_id in memberships.order_by().values_list("pk", "person_id"):
        own = periods.get(mid, [])

        def member_during(a, b, own=own):
            # Fachfrage 10 (Audit 31.10.): wer am Jubiläum selbst Mitglied war, nicht nur
            # wer am Anfang oder Ende des gewählten Zeitraums dabei war
            return any(p[0] <= b and (p[1] is None or p[1] >= a) for p in own)

        if not member_during(start, end):
            continue
        todo = [
            ("club", club, merge(_counted(own, assignments.get(mid, []), _club_counts)), precision)
        ]
        if fed_levels:
            todo.append(
                ("federation", federation, fed_ranges.get(person_id, []), federation.date_precision)
            )
        for kind, org, ranges, prec in todo:
            if not ranges:
                continue
            for years in org.jubilee_years:
                # Früher als Beginn + Jahre kann das Jubiläum nicht liegen
                if ranges[0][0].year + years > end.year:
                    continue
                d = jubilee_date(ranges, years, prec)
                if d and d <= end and unit_end(d, prec) >= start:
                    if member_during(d, unit_end(d, prec)):
                        hits.append((mid, kind, org, years, d, prec))
    found = {
        m.pk: m
        for m in Membership.objects.filter(pk__in={h[0] for h in hits}).select_related(
            "person", "person__federation"
        )
    }
    result = [
        _row(found[mid], kind, org, years, d, prec) for mid, kind, org, years, d, prec in hits
    ]
    from .birthdays import unit_names

    units = unit_names({r["member_id"] for r in result}, start)
    for r in result:
        r["units"] = units.get(r["member_id"], "")
    result.sort(key=lambda r: (r["date"], r["last_name"], r["first_name"]))
    return result


def _row(
    membership: Membership,
    kind: str,
    org,
    years: int,
    d: datetime.date,
    precision: str = DAY,
) -> dict:
    fm = getattr(membership.person, "federation", None)
    return {
        "member_id": membership.pk,
        "last_name": membership.person.last_name,
        "first_name": membership.person.first_name,
        "birth_date": membership.person.birth_date,
        "member_number": fm.member_number if fm else None,
        "kind": kind,
        "organization": org.name,
        "organization_label": org.label,
        # Kurzname für enge Stellen (Startseite, Liste); Exporte nutzen den vollen Namen
        "organization_short": org.display_name,
        "years": years,
        "date": d,
        "precision": precision,
    }
