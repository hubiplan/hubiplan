"""Fachlogik der Qualifikationen: Stand je Person, Ablauf, Prüfung für Helferdienste."""

from __future__ import annotations

import calendar
import datetime

from django.utils.translation import gettext as _

from .models import Qualification, QualificationType

MODULE = "qualifications"
# Ohne eingestellte Erinnerung gilt ein Nachweis so viele Tage vor dem Ablauf als „läuft ab“
DEFAULT_SOON_DAYS = 60

VALID = "valid"
EXPIRING = "expiring"
EXPIRED = "expired"


def module_on(org) -> bool:
    return org is not None and MODULE in (org.enabled_modules or [])


def add_months(day: datetime.date, months: int) -> datetime.date:
    """Tag plus Monate; am Monatsende auf den letzten Tag des Zielmonats (31.1. + 1 → 28./29.2.)."""
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return day.replace(
        year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])
    )


def soon_days(kind: QualificationType) -> int:
    return kind.remind_days if kind.remind_days is not None else DEFAULT_SOON_DAYS


def status(q: Qualification, on: datetime.date) -> str:
    if q.valid_until is None:
        return VALID
    if q.valid_until < on:
        return EXPIRED
    if q.valid_until - datetime.timedelta(days=soon_days(q.kind)) <= on:
        return EXPIRING
    return VALID


def _rank(q: Qualification):
    # Längste Gültigkeit zuerst; unbefristet schlägt alles, bei Gleichstand der neuere Eintrag
    return (q.valid_until or datetime.date.max, q.acquired_on, q.pk)


def latest(rows) -> dict[tuple[int, int], Qualification]:
    """Maßgeblicher Nachweis je (Person, Art): der am längsten gültige."""
    best: dict[tuple[int, int], Qualification] = {}
    for q in rows:
        key = (q.person_id, q.kind_id)
        if key not in best or _rank(q) > _rank(best[key]):
            best[key] = q
    return best


def current_for(org_id: int, person_ids, kind_ids=None) -> dict[tuple[int, int], Qualification]:
    qs = Qualification.objects.filter(organization_id=org_id, person_id__in=person_ids)
    if kind_ids is not None:
        qs = qs.filter(kind_id__in=kind_ids)
    return latest(qs.select_related("kind"))


def _date(day: datetime.date) -> str:
    from core.i18n import date_text

    return date_text(day)


def problem(
    org_id: int, person_id: int, kind: QualificationType, day: datetime.date, *, own: bool = False
) -> dict | None:
    """Fehlt der Person die Qualifikation am Tag ``day`` oder ist sie dann abgelaufen?

    ``own``: Text für das Mitglied selbst (Eintragen im Mitgliederbereich)."""
    q = current_for(org_id, [person_id], [kind.pk]).get((person_id, kind.pk))
    if q is None:
        if own:
            text = _(
                "Für diesen Dienst ist „{name}“ nötig. Bei dir ist das nicht eingetragen; "
                "bitte wende dich an den Vorstand."
            )
        else:
            text = _("Für diesen Dienst ist „{name}“ nötig; beim Mitglied ist nichts eingetragen.")
        return {"code": "qualification", "text": text.format(name=kind.name)}
    if q.valid_until is not None and q.valid_until < day:
        if own:
            text = _(
                "Für diesen Dienst ist „{name}“ nötig. Dein Nachweis gilt nur bis {date}; "
                "bitte wende dich an den Vorstand."
            )
        else:
            text = _("Für diesen Dienst ist „{name}“ nötig; der Nachweis gilt nur bis {date}.")
        return {
            "code": "qualification",
            "text": text.format(name=kind.name, date=_date(q.valid_until)),
        }
    return None
