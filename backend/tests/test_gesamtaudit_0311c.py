"""Gesamtaudit 03.11.2026: Regressionstests zu GA-F05 und GA-V05 (erfundene Daten)."""
# ruff: noqa: F811  (Fixtures als Parameter)

from email.message import EmailMessage

import pytest

from circulars import inbound, services
from circulars.models import Circular, CircularRecipient, InboundMail
from outbox.models import OutgoingMail

from .test_mailverteiler import (  # noqa: F401
    base,
    cal,
    create_list,
    mail_bytes,
    members,
    private_root,
    verteiler_settings,
    zug,
    zug2,
)

pytestmark = pytest.mark.django_db


# --- GA-F05: App-Zustellung hängt nicht an der Stundengrenze für Mails ---


def _rundschreiben(api, board_a, cal_, settings):
    """Rundschreiben mit zwei wartenden Empfängern; die Stundengrenze ist schon erreicht."""
    settings.MAIL_RATE_PER_HOUR = 10
    for i in range(10):
        OutgoingMail.objects.create(to="x@example.org", subject=f"alt {i}", body="")
    create_list(api(board_a), base(cal_["a"]))
    found = inbound.process_message(mail_bytes(board_a.email))
    inbound.confirm(found)
    circular = Circular.objects.get(pk=found.circular_id)
    assert circular.recipients.filter(status=CircularRecipient.Status.PENDING).count() == 2
    assert services.mail_budget() == 0
    return circular


def test_app_zustellung_trotz_voller_stundengrenze(
    cal, board_a, members, api, settings, monkeypatch
):
    circular = _rundschreiben(api, board_a, cal, settings)
    per_app, per_mail = circular.recipients.order_by("pk")
    CircularRecipient.objects.filter(pk=per_app.pk).update(channel=CircularRecipient.Channel.APP)
    monkeypatch.setattr(services, "deliver_app", lambda recipient, circular: True)
    assert services.send_pending(circular.pk) == 1
    per_app.refresh_from_db()
    per_mail.refresh_from_db()
    assert per_app.status == CircularRecipient.Status.SENT
    assert per_mail.status == CircularRecipient.Status.PENDING  # wartet auf freie Plätze


def test_ersatzmail_wartet_auf_stundengrenze(cal, board_a, members, api, settings, monkeypatch):
    circular = _rundschreiben(api, board_a, cal, settings)
    per_app = circular.recipients.order_by("pk").first()
    CircularRecipient.objects.filter(pk=per_app.pk).update(channel=CircularRecipient.Channel.APP)
    pushes = []

    def kein_geraet(recipient, circular):
        pushes.append(recipient.pk)
        return False

    monkeypatch.setattr(services, "deliver_app", kein_geraet)
    services.send_pending(circular.pk)
    per_app.refresh_from_db()
    assert per_app.channel == CircularRecipient.Channel.MAIL
    assert per_app.status == CircularRecipient.Status.PENDING
    # Später ist wieder Platz: nur die Mail geht, kein zweiter Push
    settings.MAIL_RATE_PER_HOUR = 0
    services.send_pending(circular.pk)
    per_app.refresh_from_db()
    assert per_app.status == CircularRecipient.Status.SENT
    assert pushes == [per_app.pk]


# --- GA-V05: Direktversand nur mit Ergebnis des eigenen Mailservers ---


def test_ohne_authserv_id_nichts_bestaetigt(settings):
    settings.MAIL_AUTHSERV_ID = ""
    msg = EmailMessage()
    msg["Authentication-Results"] = "mx.example.org; spf=pass; dkim=pass; dmarc=pass"
    assert not inbound.dmarc_passed(msg)
    settings.MAIL_AUTHSERV_ID = "mx.example.org"
    assert inbound.dmarc_passed(msg)


def test_direktverteiler_ohne_authserv_id_mit_bestaetigung(cal, board_a, members, api, settings):
    settings.MAIL_AUTHSERV_ID = ""
    create_list(api(board_a), base(cal["a"]), mode="direct")
    got = inbound.process_message(
        mail_bytes(
            board_a.email,
            Authentication_Results="mx.example.org; spf=pass; dkim=pass; dmarc=pass",
        )
    )
    assert got.status == InboundMail.Status.WAITING
