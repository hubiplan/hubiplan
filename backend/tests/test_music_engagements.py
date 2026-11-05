"""Immutable offers, acceptance evidence and stable confirmation originals."""
# ruff: noqa: F811

import datetime
import hashlib
import uuid

import pytest
from django.utils import timezone

from billing.models import BusinessPartner
from core.tenancy import tenant_context
from music.models import PerformanceAccount

from .test_music import JSON, c, club, music  # noqa: F401
from .test_music_guests import guest  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def engagement(club, guest):
    g = guest
    with tenant_context(club.pk):
        partner = BusinessPartner.objects.create(
            organization=club,
            name="Muster Veranstalter",
            details={
                "name": "Muster Veranstalter",
                "street": "Musterstraße 1",
                "postcode": "12345",
                "city": "Musterstadt",
                "country": "DE",
            },
        )
        g.performance.customer = partner
        g.performance.save()
        PerformanceAccount.objects.create(
            organization=club, performance=g.performance, fee=500, date=timezone.localdate()
        )
    return g, f"{g.base}/performances/{g.performance.pk}/engagement/"


def post(c, url, action, **values):
    return c.post(
        url, {"action": action, **values}, content_type=JSON, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())
    )


def offer(c, url):
    return post(
        c,
        url,
        "offer",
        valid_until=(timezone.localdate() + datetime.timedelta(days=5)).isoformat(),
        terms="Zwei Stunden Blasmusik. Pausen nach Absprache. <Muster>",
    )


def test_offer_accept_confirmation_archive_and_cancellation(c, club, engagement):
    g, url = engagement
    response = offer(c, url)
    assert response.status_code == 200, response.content
    document = response.json()
    original = c.get(url, {"document": document["id"]})
    assert original.content.startswith(b"%PDF-")
    assert hashlib.sha256(original.content).hexdigest() == document["sha256"]
    assert post(c, url, "confirm", document=document["id"]).status_code == 400
    response = post(
        c,
        url,
        "accept",
        document=document["id"],
        acceptance_note="Telefonische Zusage durch Veranstalter, Mustervermerk",
    )
    assert response.status_code == 200, response.content
    settlement = f"{g.base}/performances/{g.performance.pk}/settlement/"
    assert post(c, settlement, "agreement", fee="600", travel="0", extras="0").status_code == 400
    confirmation = post(c, url, "confirm", document=document["id"])
    assert confirmation.status_code == 200, confirmation.content
    assert (
        post(c, url, "confirm", document=document["id"]).json()["id"] == confirmation.json()["id"]
    )
    assert c.get(url, {"document": document["id"]}).content == original.content
    assert (
        post(
            c,
            url,
            "cancel",
            document=document["id"],
            acceptance_note="Einvernehmliche Aufhebung, Mustervermerk",
        ).status_code
        == 200
    )
    archived = c.get(url).json()["documents"]
    cancelled = next(row for row in archived if row["id"] == document["id"])
    assert cancelled["acceptance_note"].startswith("Telefonische Zusage")
    assert cancelled["resolution_note"].startswith("Einvernehmliche Aufhebung")
    assert (
        next(row for row in archived if row["kind"] == "confirmation")["source_status"]
        == "cancelled"
    )
    assert post(c, settlement, "agreement", fee="600", travel="0", extras="0").status_code == 200


def test_changed_data_requires_new_offer(c, club, engagement):
    g, url = engagement
    document = offer(c, url).json()
    with tenant_context(club.pk):
        account = PerformanceAccount.objects.get(performance=g.performance)
        account.fee = 600
        account.save()
    assert (
        post(c, url, "accept", document=document["id"], acceptance_note="Musterzusage").status_code
        == 400
    )
    assert offer(c, url).status_code == 200
    documents = c.get(url).json()["documents"]
    assert documents[0]["snapshot"]["total"] == "600.00"
    assert documents[1]["status"] == "superseded"
