"""Fachfrage FQ15 (Audit 02.11.): große offene Verteiler moderieren, Gesamtgrenze je Tag."""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest

from circulars import inbound
from circulars.models import CircularRecipient, InboundMail
from outbox.models import OutgoingMail

from .test_m12_events import JSON, cal, private_root, zug, zug2  # noqa: F401
from .test_mailverteiler import (  # noqa: F401
    base,
    create_list,
    mail_bytes,
    members,
    verteiler_settings,  # noqa: F401  (autouse)
)

pytestmark = pytest.mark.django_db


def _open(c, cal, **extra):
    ml = create_list(c, base(cal["a"]))
    resp = c.patch(
        f"{base(cal['a'])}lists/{ml['id']}/",
        {"open_senders": True, **extra},
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.json()
    return resp.json()


def test_standard_grenze_50(cal, board_a, members, api):
    data = _open(api(board_a), cal)
    assert data["open_direct_max"] == 50


def test_grosser_verteiler_wartet_auf_freigabe(
    cal, board_a, members, api, django_capture_on_commit_callbacks
):
    data = _open(api(board_a), cal, open_direct_max=1)
    assert data["open_direct_max"] == 1
    with django_capture_on_commit_callbacks(execute=True):
        entry = inbound.process_message(mail_bytes("fremd@example.net"))
    assert entry.status == InboundMail.Status.DRAFT
    assert "Zur Freigabe" in entry.reason
    entry.circular.refresh_from_db()
    assert entry.circular.is_draft
    assert not CircularRecipient.objects.filter(circular=entry.circular).exists()
    # Hinweis an die Freigebenden, nicht an den fremden Absender
    note = OutgoingMail.objects.get(kind="verteiler", to__contains=board_a.email)
    assert note.subject.startswith("Zur Freigabe:") and "fremd@example.net" in note.body
    assert not OutgoingMail.objects.filter(to__contains="fremd@").exists()


def test_gesamtgrenze_je_tag(
    cal, board_a, members, api, settings, django_capture_on_commit_callbacks
):
    settings.MAILING_OPEN_PER_DAY_TOTAL = 2
    _open(api(board_a), cal)
    states = []
    for i in range(3):
        with django_capture_on_commit_callbacks(execute=True):
            entry = inbound.process_message(mail_bytes(f"fremd{i}@example.net", subject=f"S{i}"))
        states.append(entry.status)
    assert states == [InboundMail.Status.SENT, InboundMail.Status.SENT, InboundMail.Status.DRAFT]
