"""Mailversand: Verbindung wiederverwenden, sicher wiederholen, Stundengrenze für Massenmails.

Gesamtaudit 15.11., PF-09 (Fachfrage FF-41): eine SMTP-Verbindung je Mail, keine Wiederholung
bei vorübergehenden Fehlern, Stundengrenze nur bei Rundschreiben; Termin-Einladungen an viele
Mitglieder liefen am Postfach-Limit auf. Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import smtplib
from unittest import mock

import pytest
from django.core.mail import EmailMessage

from core.tenancy import rls_bypass
from events import notify
from outbox import mail
from outbox.backend import OutboxBackend
from outbox.models import OutgoingMail

from .factories import make_member
from .test_m12_events import (  # noqa: F401  (Fixtures)
    cal,
    create,
    member_with_access,
    org_base,
    private_root,
    zug,
    zug2,
)

pytestmark = pytest.mark.django_db


class FakeSmtp:
    """Ersatz für smtplib.SMTP; ``script`` bestimmt die Antworten auf sendmail."""

    instances = 0
    connect_failures = 0
    script: list = []
    sent: list = []

    def __init__(self, host, port, **kwargs):
        if FakeSmtp.connect_failures:
            FakeSmtp.connect_failures -= 1
            raise ConnectionRefusedError("erfundener Verbindungsfehler")
        FakeSmtp.instances += 1

    def ehlo(self, *args):
        return 250, b"ok"

    def starttls(self, *args, **kwargs):
        return 220, b"ok"

    def login(self, *args):
        return 235, b"ok"

    def noop(self):
        return 250, b"ok"

    def sendmail(self, from_addr, to_addrs, msg, *args, **kwargs):
        action = FakeSmtp.script.pop(0) if FakeSmtp.script else None
        if action is not None:
            raise action
        FakeSmtp.sent.append(to_addrs)
        return {}

    def quit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def smtp(settings):
    settings.EMAIL_HOST = "smtp.example.org"
    settings.EMAIL_USE_TLS = False
    settings.EMAIL_USE_SSL = False
    settings.EMAIL_HOST_USER = ""
    settings.EMAIL_BACKEND = "outbox.backend.OutboxBackend"
    settings.MAIL_RETRY_DELAYS = (0, 0)
    FakeSmtp.instances = 0
    FakeSmtp.connect_failures = 0
    FakeSmtp.script = []
    FakeSmtp.sent = []
    with mock.patch("smtplib.SMTP", FakeSmtp):
        yield FakeSmtp


def _status(subject):
    with rls_bypass():
        return OutgoingMail.objects.get(subject=subject).status


def _send(subject):
    message = EmailMessage(subject, "Text", "verein@example.org", ["erika@example.org"])
    return OutboxBackend(fail_silently=True).send_messages([message])


def test_vorubergehende_ablehnung_wird_einmal_wiederholt(smtp):
    smtp.script = [smtplib.SMTPDataError(451, b"spaeter")]
    assert _send("Vorübergehend") == 1
    assert smtp.sent == [["erika@example.org"]]  # genau einmal angenommen
    assert _status("Vorübergehend") == OutgoingMail.Status.SENT


def test_verbindungsabbruch_beim_senden_wird_nicht_wiederholt(smtp):
    """Offen, ob die Mail angenommen wurde: lieber keine als doppelt."""
    smtp.script = [smtplib.SMTPServerDisconnected("weg")]
    assert _send("Abbruch") == 0
    assert smtp.sent == []
    assert smtp.script == []  # kein zweiter Versuch
    assert _status("Abbruch") == OutgoingMail.Status.FAILED


def test_dauerhafte_ablehnung_wird_nicht_wiederholt(smtp):
    smtp.script = [smtplib.SMTPDataError(550, b"nein"), None]
    assert _send("Dauerhaft") == 0
    assert smtp.sent == [] and smtp.script == [None]
    assert _status("Dauerhaft") == OutgoingMail.Status.FAILED


def test_verbindungsaufbau_wird_wiederholt(smtp):
    smtp.connect_failures = 1
    assert _send("Aufbau") == 1
    assert smtp.sent == [["erika@example.org"]]


def test_eine_verbindung_fuer_viele_mails(smtp):
    with mail.connection():
        for i in range(3):
            assert mail.send(f"mitglied{i}@example.org", f"Serie {i}", "Text")
    assert smtp.instances == 1
    assert len(smtp.sent) == 3
    # Ohne Block wie bisher je Mail eine Verbindung
    mail.send("einzeln@example.org", "Einzeln", "Text")
    assert smtp.instances == 2


@pytest.fixture
def event_setup(cal, board_a, zug, api, private_root):
    club = cal["a"]
    members = [make_member(club, f"Erika{i}", "Muster", departments=[zug]) for i in range(15)]
    c = api(board_a)
    ev = create(
        c,
        org_base(club),
        title="Jahresfeier",
        starts_at="2099-06-13T14:00:00",
        ends_at="2099-06-13T18:00:00",
    )
    return {"club": club, "ev": ev, "members": members}


def test_termin_mails_halten_die_stundengrenze_und_setzen_fort(event_setup, settings):
    settings.EMAIL_BACKEND = "outbox.backend.OutboxBackend"
    settings.EMAIL_HOST = ""
    settings.CELERY_TASK_ALWAYS_EAGER = False
    settings.MAIL_RATE_PER_HOUR = 12  # 10 Plätze, ein Zehntel bleibt für Anmeldemails
    ev = event_setup["ev"]["id"]
    with mock.patch("events.tasks.send_event_mails.apply_async") as later:
        first = notify.send(ev, notify.INVITE)
    assert 0 < first <= 10
    later.assert_called_once()
    ((event_id, kind, remaining),) = later.call_args.args
    assert (event_id, kind) == (ev, notify.INVITE)
    assert first + len(remaining) >= 15
    # Eine Stunde später (hier: Grenze aufgehoben) folgt der Rest, ohne Doppel
    settings.MAIL_RATE_PER_HOUR = 0
    with mock.patch("events.tasks.send_event_mails.apply_async") as again:
        rest = notify.send(ev, notify.INVITE, remaining)
    again.assert_not_called()
    with rls_bypass():
        addresses = list(OutgoingMail.objects.filter(kind="termin").values_list("to", flat=True))
    assert len(addresses) == first + rest == len(set(addresses))  # niemand doppelt
