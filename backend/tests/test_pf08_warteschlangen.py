"""Getrennte Warteschlangen, Verfall, Grenzen und Sperren für Langläufer (Gesamtaudit 15.11.).

PF-08: Ein Worker mit zwei Plätzen erledigte alles, ohne Warteschlangen, Zeitgrenzen und
Verfallszeit; stundenlange Zeitplan-Jobs hielten Anmeldelinks, Mails und Exporte auf.
PF-13: Der Postfachabruf nahm eine 10-Minuten-Cache-Sperre, die kürzer als der Lauf war, und
markierte bei Zeitablauf die gerade bearbeitete Mail als gelesen. Erfundene Daten.
"""

from pathlib import Path
from unittest import mock

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from celery.schedules import crontab
from django.conf import settings
from django.db import connections

from core import einzeln

REPO = Path(settings.BASE_DIR).parent


def test_zeitplan_jobs_in_eigener_warteschlange_mit_verfall():
    assert settings.ZEITPLAN_QUEUE == "zeitplan"
    for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
        options = entry["options"]
        assert options["queue"] == "zeitplan", name
        if isinstance(entry["schedule"], crontab):
            assert options["expires"] == 6 * 60 * 60, name
        else:
            assert 60 <= options["expires"] <= entry["schedule"] + 60, name
    # Was Benutzer auslösen, bleibt in der Standardwarteschlange; nur Anmelde- und
    # Sicherheitsmails gehen nach „eilig“
    assert settings.CELERY_TASK_DEFAULT_QUEUE == "celery"
    assert settings.CELERY_TASK_ROUTES == {
        "outbox.tasks.send_message": {"queue": "eilig"},
        "portal.tasks.send_requested_link": {"queue": "eilig"},
    }


def test_globale_grenzen():
    assert settings.CELERY_TASK_SOFT_TIME_LIMIT == 3 * 60 * 60
    assert settings.CELERY_TASK_TIME_LIMIT > settings.CELERY_TASK_SOFT_TIME_LIMIT
    assert settings.CELERY_WORKER_PREFETCH_MULTIPLIER == 1
    assert settings.CELERY_WORKER_MAX_TASKS_PER_CHILD == 200


def test_compose_trennt_die_worker():
    compose = REPO / "docker-compose.server.yml"
    if not compose.exists():
        pytest.skip("Compose-Dateien im Testcontainer nicht vorhanden")
    text = compose.read_text(encoding="utf-8")
    assert "--concurrency=2 -Q eilig,celery" in text
    assert "worker-zeitplan:" in text and "-Q eilig,zeitplan" in text
    clamav = (REPO / "docker-compose.clamav.yml").read_text(encoding="utf-8")
    assert "worker-zeitplan:" in clamav  # Virenprüfung läuft im Zeitplan
    for script in ("deploy/server-setup.sh", "deploy/datenschluessel-wechseln.sh"):
        assert "worker worker-zeitplan beat" in (REPO / script).read_text(encoding="utf-8")


@pytest.mark.django_db
def test_einzeln_ueberspringt_zweiten_lauf():
    calls = []

    @einzeln.einzeln
    def job():
        calls.append(1)
        return "fertig"

    name = f"{job.__module__}.{job.__name__}"
    other = connections.create_connection("default")
    try:
        with other.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_lock(%s, %s)", [einzeln.NAMESPACE, einzeln._key(name)]
            )
        assert job() is None and calls == []
        with other.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_unlock(%s, %s)", [einzeln.NAMESPACE, einzeln._key(name)]
            )
    finally:
        other.close()
    assert job() == "fertig" and calls == [1]


def test_langlaeufer_sind_gesperrt():
    from billing.tasks import check_incoming_all
    from events.tasks import sync_external_calendars
    from peering.tasks import deliver_due, sync_all

    for task in (check_incoming_all, sync_external_calendars, sync_all, deliver_due):
        assert getattr(task.run, "__wrapped__", None) is not None, task.name


class _FakeImap:
    def __init__(self, *args, **kwargs):
        self.stored = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, *args):
        return "OK", []

    def select(self, *args):
        return "OK", []

    def uid(self, command, *args):
        if command == "search":
            return "OK", [b"7"]
        if command == "fetch" and "SIZE" in args[1]:
            return "OK", [b"7 (RFC822.SIZE 100)"]
        if command == "fetch":
            return "OK", [(b"7", b"Subject: Test\r\n\r\nText")]
        if command == "store":
            self.stored.append(args)
        return "OK", []

    def expunge(self):
        return "OK", []


@pytest.mark.django_db
def test_postfach_zeitgrenze_markiert_mail_nicht_als_gelesen(settings):
    from circulars import inbound

    settings.INBOUND_IMAP_HOST = "imap.example.org"
    fake = _FakeImap()
    with (
        mock.patch("circulars.inbound.imaplib.IMAP4_SSL", return_value=fake),
        mock.patch("billing.incoming_mail.addressed_here", return_value=False),
        mock.patch.object(inbound, "process_message", side_effect=SoftTimeLimitExceeded()),
        pytest.raises(SoftTimeLimitExceeded),
    ):
        inbound.fetch_inbound()
    assert fake.stored == []  # nicht \\Seen: der nächste Lauf holt sie


def test_datenauftraege_und_massenversand_mit_eigener_grenze():
    """Import, Export, Datenübernahme, Rundschreiben, Termin-Mails: 12 statt 3 Stunden."""
    from circulars.tasks import send_circular
    from datatransfer import tasks as dt
    from events.tasks import send_event_mails
    from exchange import tasks as ex

    for task in (
        send_circular,
        send_event_mails,
        dt.run_export,
        dt.check_import,
        dt.run_import,
        ex.run_export,
        ex.validate_import,
        ex.run_import,
    ):
        assert task.soft_time_limit == einzeln.LONG_SOFT, task.name
        assert task.time_limit > task.soft_time_limit, task.name


def test_sicherheitsmail_im_hintergrund_eilig_mit_verfall(settings):
    from django.core.mail import EmailMessage

    from outbox import tasks

    settings.MAIL_IN_BACKGROUND = True
    message = EmailMessage("Anmeldelink", "Text", "verein@example.org", ["erika@example.org"])
    with (
        mock.patch.object(tasks.send_message, "apply_async") as later,
        mock.patch("django.db.transaction.on_commit", side_effect=lambda f, robust=False: f()),
    ):
        tasks.deliver(message)
    assert later.call_args.kwargs["expires"] == settings.EILIG_EXPIRES
