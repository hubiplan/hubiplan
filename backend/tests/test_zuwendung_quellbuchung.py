"""Bestätigte Zuwendungen schützen auch ihre Quellbuchung (FIN03-02)."""
# ruff: noqa: F811

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from core.tenancy import tenant_context
from finance import donations
from finance.models import Booking, Donation, DonationStatement

from .test_gesamtaudit_nebenlaeufig import hold_then
from .test_m9_billing import JSON, base, c, club, setup, zug  # noqa: F401
from .test_zuwendungen import _private, ev, ready  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def source(ready, c, club, setup):
    category = c.post(
        f"{ready}/categories/",
        {"name": "Erfundene Spenden", "kind": "income", "donations": True},
        content_type=JSON,
    ).json()["id"]
    response = c.post(
        f"{ready}/bookings/",
        {
            "date": timezone.localdate().isoformat(),
            "kind": "income",
            "amount": "100.00",
            "account": setup["bank"],
            "category": category,
            "text": "Erfundene Spende",
            "counterparty": "Paula Prüfperson",
        },
        content_type=JSON,
    )
    assert response.status_code == 201, response.json()
    booking = response.json()
    imported = c.post(
        f"{ready}/donations/import/", {"year": timezone.localdate().year}, content_type=JSON
    )
    assert imported.status_code == 200 and imported.json()["created"] == 1
    with tenant_context(club.pk):
        donation = Donation.objects.get(booking_id=booking["id"])
    assert (
        c.patch(
            f"{ready}/donations/{donation.pk}/",
            {"donor_address": "Erfundener Weg 1\n12345 Musterstadt"},
            content_type=JSON,
        ).status_code
        == 200
    )
    return {"booking": booking, "donation": donation.pk}


def issue(c, ready, source):
    response = c.post(
        f"{ready}/donation-statements/", {"donations": [source["donation"]]}, content_type=JSON
    )
    assert response.status_code == 201, response.json()
    return response.json()


@pytest.mark.parametrize(
    "field", ["amount", "date", "counterparty", "text", "number", "account", "category"]
)
def test_confirmed_source_patch_is_blocked(source, ready, c, club, setup, field):
    statement = issue(c, ready, source)
    booking = source["booking"]
    values = {
        "amount": "50.00",
        "date": (timezone.localdate() - datetime.timedelta(days=1)).isoformat(),
        "counterparty": "Andere erfundene Person",
        "text": "Anderer erfundener Text",
        "number": booking["number"] + 100,
        "account": setup["cash"],
        "category": setup["cat"],
    }
    response = c.patch(
        f"{ready}/bookings/{booking['id']}/", {field: values[field]}, content_type=JSON
    )
    assert response.status_code == 400, response.json()
    assert statement["number"] in str(response.json())
    fresh = c.get(f"{ready}/bookings/{booking['id']}/").json()
    assert fresh[field] == booking[field]
    with tenant_context(club.pk):
        donation = Donation.objects.get(pk=source["donation"])
        assert donation.booking_id == booking["id"]
        assert donation.statement_id == statement["id"]


def test_confirmed_source_delete_is_blocked(source, ready, c, club):
    statement = issue(c, ready, source)
    response = c.delete(f"{ready}/bookings/{source['booking']['id']}/")
    assert response.status_code == 400, response.content
    assert statement["number"] in str(response.json())
    with tenant_context(club.pk):
        assert Booking.objects.filter(pk=source["booking"]["id"]).exists()
        assert Donation.objects.get(pk=source["donation"]).booking_id == source["booking"]["id"]


@pytest.mark.parametrize("force", [False, True])
def test_confirmed_source_old_undo_is_blocked(source, ready, c, club, force):
    response = c.patch(
        f"{ready}/bookings/{source['booking']['id']}/", {"amount": "50.00"}, content_type=JSON
    )
    assert response.status_code == 200, response.json()
    change = response["X-Change-Set"]
    assert (
        c.patch(
            f"{ready}/donations/{source['donation']}/", {"amount": "50.00"}, content_type=JSON
        ).status_code
        == 200
    )
    statement = issue(c, ready, source)
    response = c.post(
        f"{ready.removesuffix('/finance')}/changes/{change}/undo/",
        {"force": force},
        content_type=JSON,
    )
    assert response.status_code == 409, response.json()
    assert statement["number"] in str(response.json())
    assert response.json()["can_force"] is False
    with tenant_context(club.pk):
        assert Booking.objects.get(pk=source["booking"]["id"]).amount == Decimal("50.00")


@pytest.mark.parametrize("operation", ["patch", "delete", "storno"])
def test_statement_cancellation_releases_source(source, ready, c, club, operation):
    statement = issue(c, ready, source)
    pdf_before = c.get(f"{ready}/donation-statements/{statement['id']}/pdf/").content
    cancelled = c.post(
        f"{ready}/donation-statements/{statement['id']}/cancel/",
        {"reason": "Erfundene Korrektur"},
        content_type=JSON,
    )
    assert cancelled.status_code == 200, cancelled.json()
    url = f"{ready}/bookings/{source['booking']['id']}/"
    if operation == "patch":
        response = c.patch(url, {"amount": "50.00"}, content_type=JSON)
        assert response.status_code == 200, response.json()
    elif operation == "delete":
        assert c.delete(url).status_code == 204
    else:
        response = c.post(url + "storno/", {"reason": "Erfundene Korrektur"}, content_type=JSON)
        assert response.status_code == 201, response.json()
    with tenant_context(club.pk):
        assert DonationStatement.objects.get(pk=statement["id"]).cancelled_at is not None
    assert c.get(f"{ready}/donation-statements/{statement['id']}/pdf/").content == pdf_before


def test_unconfirmed_source_remains_editable(source, ready, c):
    response = c.patch(
        f"{ready}/bookings/{source['booking']['id']}/", {"amount": "50.00"}, content_type=JSON
    )
    assert response.status_code == 200, response.json()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["patch", "delete"])
def test_source_waits_for_concurrent_statement(source, ready, api, board_a, club, operation):
    def issuing():
        with tenant_context(club.pk):
            return donations.issue(club, [Donation.objects.get(pk=source["donation"])], board_a).pk

    def editing():
        client = api(board_a)
        url = f"{ready}/bookings/{source['booking']['id']}/"
        if operation == "patch":
            return client.patch(url, {"amount": "50.00"}, content_type=JSON)
        return client.delete(url)

    waited, second = hold_then(issuing, editing)
    assert waited, "Die Buchungsänderung muss auf die laufende Bestätigung warten."
    assert "error" not in second, second
    assert second["value"].status_code == 400, second["value"].content
    with tenant_context(club.pk):
        assert Booking.objects.get(pk=source["booking"]["id"]).amount == Decimal("100.00")
        assert Donation.objects.get(pk=source["donation"]).statement_id is not None
