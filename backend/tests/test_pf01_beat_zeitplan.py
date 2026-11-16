"""PF-01 (Gesamtaudit 15.11.): Tägliche Jobs laufen trotz Ausrollen, letzter Lauf ist sichtbar.

Früher waren alle Einträge des Zeitplans Intervalle, und die Zeitplan-Datei lag im
Arbeitsspeicher. Jeder Neustart von "beat" begann das Intervall neu: Ein 24-Stunden-Job lief
bei mehr als einem Ausrollen am Tag nie (Löschfrist, Bereinigungen, Kettenprüfung).
"""

import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from celery.schedules import crontab
from django.conf import settings
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.utils import timezone

from core import joblauf
from core.models import JobRun

BERLIN = ZoneInfo("Europe/Berlin")


def _period(schedule) -> float:
    if isinstance(schedule, crontab):
        return 0
    return float(schedule.total_seconds() if hasattr(schedule, "total_seconds") else schedule)


def test_kein_langes_intervall_im_zeitplan():
    """Jobs mit Abstand ab 6 Stunden laufen zu festen Uhrzeiten, nicht im Intervall."""
    lang = {
        name
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items()
        if _period(entry["schedule"]) >= 6 * 3600
    }
    assert lang == set()


def test_zeitplan_datei_ueberlebt_das_ausrollen():
    compose = Path(settings.BASE_DIR).parent / "docker-compose.server.yml"
    if not compose.exists():
        pytest.skip("docker-compose.server.yml im Testcontainer nicht vorhanden")
    text = compose.read_text(encoding="utf-8")
    assert "--schedule /tmp/" not in text
    assert "--schedule /app/beat/celerybeat-schedule" in text
    assert "beat-zeitplan:/app/beat" in text


def test_max_age_nach_zeitplan():
    assert joblauf.max_age(crontab(minute=0, hour=3)) == datetime.timedelta(hours=26)
    assert joblauf.max_age(crontab(minute=0, hour=7, day_of_week="mon")) == datetime.timedelta(
        days=7, hours=2
    )
    assert joblauf.max_age(crontab(minute=20, hour="1,7,13,19")) == datetime.timedelta(hours=8)
    assert joblauf.max_age(60) == datetime.timedelta(hours=1, minutes=1)
    assert joblauf.max_age(3600.0) == datetime.timedelta(hours=2)


def _task(name, eager=False):
    return SimpleNamespace(name=name, request=SimpleNamespace(is_eager=eager))


@pytest.mark.django_db
def test_lauf_wird_vermerkt():
    task = _task("members.tasks.purge_expired_members")
    joblauf._started(sender=task)
    joblauf._succeeded(sender=task)
    row = JobRun.objects.get(name="loeschfrist")
    assert row.task == "members.tasks.purge_expired_members"
    assert row.last_started_at and row.last_success_at
    assert row.last_failure_at is None

    joblauf._failed(sender=task, exception=ValueError("kaputt"))
    row.refresh_from_db()
    assert row.last_failure_at and row.last_error == "ValueError: kaputt"


@pytest.mark.django_db
def test_sofort_ausgefuehrte_und_fremde_aufgaben_zaehlen_nicht():
    joblauf._succeeded(sender=_task("members.tasks.purge_expired_members", eager=True))
    joblauf._succeeded(sender=_task("core.tasks.nicht_im_zeitplan"))
    assert not JobRun.objects.exists()


@pytest.mark.django_db
def test_ueberfaellige_jobs_werden_gemeldet():
    cache.clear()
    now = timezone.now()
    joblauf.status(now)  # Beginn der Beobachtung: nichts überfällig
    assert joblauf.overdue_lines(joblauf.status(now)) == []

    JobRun.objects.filter(name="loeschfrist").update(
        last_success_at=now - datetime.timedelta(hours=30),
        last_failure_at=now - datetime.timedelta(hours=1),
        last_error="RuntimeError: Datenbank weg",
    )
    JobRun.objects.filter(name="postausgang-aufraeumen").update(
        last_success_at=now - datetime.timedelta(hours=2)
    )
    lines = joblauf.overdue_lines(joblauf.status(now))
    assert len(lines) == 1
    assert lines[0].startswith("loeschfrist (members.tasks.purge_expired_members)")
    assert "RuntimeError: Datenbank weg" in lines[0]

    with mock.patch("core.alarm.send_alert") as send:
        assert joblauf.check_jobs() == lines
        joblauf.check_jobs()  # derselbe Stand: keine zweite Mail am selben Tag
    assert send.call_count == 1
    assert "Hintergrundjobs prüfen" in send.call_args.args[0]

    with pytest.raises(CommandError, match="1 Job"):
        call_command("jobs_status", "--pruefen")


@pytest.mark.django_db
def test_neue_installation_meldet_erst_nach_der_frist():
    cache.clear()
    now = timezone.now()
    joblauf.status(now)
    later = now + datetime.timedelta(hours=27)
    names = {line.split(" ", 1)[0] for line in joblauf.overdue_lines(joblauf.status(later))}
    assert "loeschfrist" in names  # 27 Stunden ohne Lauf: überfällig
    assert "protokoll-kassenpruefer" not in names  # wöchentlich: noch nicht


@pytest.mark.parametrize(
    "name, hour",
    [("loeschfrist", 3), ("erziehungsberechtigte-volljaehrig", 6), ("postausgang-aufraeumen", 4)],
)
def test_nach_neustart_laeuft_der_job_zur_festen_uhrzeit(name, hour):
    """Mit der echten Celery-Anwendung: Direkt nach einem Neustart (ohne Zeitplan-Datei) ist
    der nächste Lauf zur festen Uhrzeit, nicht erst 24 Stunden später."""
    from celery.beat import ScheduleEntry

    from config.celery import app

    conf = settings.CELERY_BEAT_SCHEDULE[name]
    entry = ScheduleEntry(name=name, task=conf["task"], schedule=conf["schedule"], app=app)
    now = datetime.datetime.now(BERLIN)
    minute = min(conf["schedule"].minute)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = (target + datetime.timedelta(days=1)).replace(hour=hour, minute=minute)
    due, next_in = entry.is_due()
    assert not due
    assert abs(next_in - (target - now).total_seconds()) < 3700  # Zeitumstellung: ± 1 Stunde
