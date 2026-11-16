"""Wann liefen die Jobs aus dem Zeitplan von "beat" zuletzt? (Gesamtaudit 15.11., PF-01)

Der Worker vermerkt Beginn, Erfolg und Fehler jedes Jobs, der im Zeitplan
(``CELERY_BEAT_SCHEDULE``) steht, in ``core.JobRun``. ``check_jobs`` (stündlich) meldet per
Alarm-Mail Jobs, die länger nicht erfolgreich liefen, als ihr Zeitplan erwarten lässt;
``manage.py jobs_status`` zeigt den Stand für den Betrieb.

Die Aufzeichnung darf einen Job nie stören: Fehler beim Schreiben werden nur protokolliert.
Sofort ausgeführte Aufgaben (``CELERY_TASK_ALWAYS_EAGER``, Tests) zählen nicht als Lauf.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
from dataclasses import dataclass

from celery import shared_task
from celery.schedules import crontab
from celery.signals import task_failure, task_prerun, task_success
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Spielraum über dem erwarteten Abstand: Warteschlange, Laufzeit, Ausrollen zur Laufzeit
GRACE = datetime.timedelta(hours=2)


def scheduled() -> dict[str, list[str]]:
    """Aufgabenname → Namen der Einträge im Zeitplan."""
    result: dict[str, list[str]] = {}
    for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
        result.setdefault(entry["task"], []).append(name)
    return result


def _hour_gap(hours: set[int]) -> int:
    """Größter Abstand in Stunden zwischen zwei Läufen eines Tages (ringförmig)."""
    ordered = sorted(hours)
    gaps = [b - a for a, b in zip(ordered, ordered[1:], strict=False)]
    gaps.append(ordered[0] + 24 - ordered[-1])
    return max(gaps)


def max_age(schedule) -> datetime.timedelta:
    """Wie lange ein Job höchstens ohne erfolgreichen Lauf sein darf."""
    if isinstance(schedule, crontab):
        if len(schedule.day_of_week) < 7 or len(schedule.day_of_month) < 31:
            period = datetime.timedelta(days=7)
        else:
            period = datetime.timedelta(hours=_hour_gap(set(schedule.hour)))
        return period + GRACE
    if isinstance(schedule, datetime.timedelta):
        period = schedule
    elif isinstance(schedule, int | float):
        period = datetime.timedelta(seconds=schedule)
    else:  # celery.schedules.schedule
        period = schedule.run_every
    # Ein Intervall beginnt bei jedem Neustart neu: einmal den Abstand, mindestens eine Stunde
    return period + max(period, datetime.timedelta(hours=1))


def _record(task, **fields) -> None:
    request = getattr(task, "request", None)
    if request is not None and getattr(request, "is_eager", False):
        return
    names = scheduled().get(getattr(task, "name", ""), [])
    if not names:
        return
    try:
        from .models import JobRun

        for name in names:
            row, _ = JobRun.objects.get_or_create(name=name, defaults={"task": task.name})
            for key, value in fields.items():
                setattr(row, key, value)
            row.task = task.name
            row.save()
    except Exception:  # noqa: BLE001 – die Aufzeichnung darf den Job nie stören
        logger.exception("Joblauf von %s nicht vermerkt", getattr(task, "name", "?"))


@task_prerun.connect
def _started(sender=None, **kwargs) -> None:
    _record(sender, last_started_at=timezone.now())


@task_success.connect
def _succeeded(sender=None, **kwargs) -> None:
    _record(sender, last_success_at=timezone.now())


@task_failure.connect
def _failed(sender=None, exception=None, **kwargs) -> None:
    text = f"{type(exception).__name__}: {exception}" if exception else ""
    _record(sender, last_failure_at=timezone.now(), last_error=text[:500])


@dataclass
class Status:
    name: str
    task: str
    last_success_at: datetime.datetime | None
    last_failure_at: datetime.datetime | None
    last_error: str
    max_age: datetime.timedelta
    overdue: bool


def status(now: datetime.datetime | None = None) -> list[Status]:
    """Stand aller Jobs im Zeitplan. Legt fehlende Zeilen an (Beginn der Beobachtung)."""
    from .models import JobRun

    now = now or timezone.now()
    rows = {r.name: r for r in JobRun.objects.all()}
    result = []
    for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
        row = rows.get(name)
        if row is None:
            row = JobRun.objects.create(name=name, task=entry["task"])
        limit = max_age(entry["schedule"])
        # Seit dem letzten Erfolg bzw. seit Beginn der Beobachtung (neue Installation)
        since = row.last_success_at or row.created_at
        result.append(
            Status(
                name=name,
                task=entry["task"],
                last_success_at=row.last_success_at,
                last_failure_at=row.last_failure_at,
                last_error=row.last_error,
                max_age=limit,
                overdue=now - since > limit,
            )
        )
    return result


def _when(value: datetime.datetime | None) -> str:
    return f"{timezone.localtime(value):%d.%m.%Y %H:%M}" if value else "noch nie"


def overdue_lines(rows: list[Status]) -> list[str]:
    lines = []
    for row in rows:
        if not row.overdue:
            continue
        line = f"{row.name} ({row.task}): zuletzt erfolgreich {_when(row.last_success_at)}"
        if row.last_failure_at and (
            not row.last_success_at or row.last_failure_at > row.last_success_at
        ):
            line += f"; Fehler {_when(row.last_failure_at)}: {row.last_error or 'ohne Angabe'}"
        lines.append(line)
    return lines


@shared_task
def check_jobs() -> list[str]:
    """Überfällige Jobs per Alarm-Mail melden, höchstens einmal am Tag je Stand."""
    from . import alarm

    lines = overdue_lines(status())
    key = hashlib.sha256("\n".join(lines).encode()).hexdigest()[:32]
    if lines and cache.add(f"jobs-alarm:{key}", 1, 24 * 60 * 60):
        alarm.send_alert(
            "Hintergrundjobs prüfen",
            [
                "Diese Jobs liefen länger nicht erfolgreich, als ihr Zeitplan erwarten lässt:",
                *lines,
                "",
                "Stand: manage.py jobs_status; Dienste worker und beat und ihr Protokoll prüfen.",
            ],
        )
    return lines
