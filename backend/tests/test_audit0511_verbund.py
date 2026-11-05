# ruff: noqa: F811  (Fixtures aus test_verbund_kopplung)
"""Gesamtaudit 05.11. GA-02: große Pakete im Verbund, kein Stau durch ein einzelnes Paket."""

import json
import os

import pytest
from django.test import Client
from django.utils import timezone

from circulars.models import Circular
from organizations.models import PlatformSettings
from peering import services, transport
from peering.models import Message

from .test_verbund_kopplung import VERBAND, VEREIN, _setup, api, couple, net, world  # noqa: F401
from .test_verbund_rundschreiben import setup  # noqa: F401

pytestmark = pytest.mark.django_db
MB = 1024 * 1024


def test_eingang_prueft_auch_pakete_ueber_5_mb():
    """Djangos allgemeine Grenze (5 MB) weist Verbundpakete nicht mehr vorab ab."""
    ps = PlatformSettings.load()
    ps.peering_enabled = True
    ps.save()
    body = json.dumps({"from": "x", "pad": "a" * (6 * MB)}).encode()
    r = Client().post("/api/peering/v1/inbox/", body, content_type="application/json")
    assert r.status_code == 400
    assert r.json() == {"error": "Unterschrift fehlt."}


def test_eingang_lehnt_zu_grosse_pakete_mit_413_ab():
    ps = PlatformSettings.load()
    ps.peering_enabled = True
    ps.save()
    r = Client().post(
        "/api/peering/v1/inbox/",
        b"x",
        content_type="application/json",
        CONTENT_LENGTH=str(transport.MAX_BODY + 1),
    )
    assert r.status_code == 413


def send(net, world, subject: str, pdf: bytes = b"%PDF-1.4 erfunden") -> None:
    from django.core.files.base import ContentFile

    from circulars import services as circular_services
    from circulars.models import CircularAttachment
    from core.tenancy import tenant_context

    fed = world["fed"]
    with net.on(VERBAND), tenant_context(fed.pk):
        circular = Circular.objects.create(
            organization=fed,
            audience="members",
            subject=subject,
            body="Hallo",
            reply_to="info@verband.example",
        )
        CircularAttachment.objects.create(
            organization=fed,
            circular=circular,
            file=ContentFile(pdf, name="Plan.pdf"),
            name="Plan.pdf",
            size=len(pdf),
        )
        circular_services.start_sending(circular, world["fed_board"])


def arrived(net, world, subject: str) -> bool:
    """Weitergabe beim Verein angekommen (eigene Kopie, nicht das Original oben)."""
    with net.on(VEREIN):
        return Circular.objects.filter(organization=world["club"], subject=subject).exists()


@pytest.mark.parametrize("size", [4 * MB, 9 * MB])
def test_rundschreiben_mit_grossem_pdf_kommt_an(net, world, setup, size):
    send(net, world, "Großer Anhang", b"%PDF-1.4\n" + os.urandom(size))
    assert arrived(net, world, "Großer Anhang")


def test_abgelehntes_paket_haelt_die_folgenden_nicht_auf(net, world, setup, monkeypatch):
    """Unsignierte 4xx: nach einigen Versuchen abgelehnt, das nächste Paket geht durch."""
    real_call = transport.call
    blocked: list[str] = []

    def call(keys, path, envelope, *, sealed=None, **kw):
        ct = (sealed or {}).get("ct", "")
        if not blocked or blocked[0] == ct:
            blocked[:1] = [ct]
            raise transport.UnsignedResponse(400, "Antwort ohne gültige Unterschrift (HTTP 400).")
        return real_call(keys, path, envelope, sealed=sealed, **kw)

    monkeypatch.setattr(services.transport, "call", call)
    upper = setup["upper"]
    with net.on(VERBAND):
        first = Message.objects.filter(coupling=upper, direction="out").count()
    send(net, world, "Erstes Rundschreiben")
    with net.on(VERBAND):
        stuck = (
            Message.objects.filter(coupling=upper, direction="out", state="queued")
            .order_by("seq")
            .first()
        )
        assert stuck is not None and stuck.attempts == 1
        assert Message.objects.filter(coupling=upper, direction="out").count() > first

    send(net, world, "Zweites Rundschreiben")  # wartet hinter dem ersten
    assert not arrived(net, world, "Zweites Rundschreiben")
    with net.on(VERBAND):
        Message.objects.filter(pk=stuck.pk).update(
            attempts=services.GIVE_UP_AFTER - 1, next_try_at=timezone.now()
        )
        services.deliver(upper.pk)
        stuck.refresh_from_db()
        assert stuck.state == Message.State.REJECTED
    assert arrived(net, world, "Zweites Rundschreiben")


def test_413_wird_sofort_abgelehnt(net, world, setup, monkeypatch):
    def call(*args, **kwargs):
        raise transport.UnsignedResponse(413, "Antwort ohne gültige Unterschrift (HTTP 413).")

    monkeypatch.setattr(services.transport, "call", call)
    upper = setup["upper"]
    send(net, world, "Zu groß")
    with net.on(VERBAND):
        assert not Message.objects.filter(coupling=upper, direction="out", state="queued").exists()
        assert Message.objects.filter(coupling=upper, direction="out", state="rejected").exists()
