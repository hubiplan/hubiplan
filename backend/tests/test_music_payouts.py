"""Reservation, immutable bank exports and reconciliation through actual bookings."""
# ruff: noqa: F811

import pytest
from django.utils import timezone
from lxml import etree

from core.tenancy import tenant_context
from finance.models import Account, Booking
from music.models import PayoutRun

from .test_m9_billing import JSON, c, club  # noqa: F401
from .test_music import music  # noqa: F401
from .test_music_settlement import expense, post, settlement  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def approved(c, club, settlement):
    url, assignment = settlement
    response = post(
        c,
        url,
        action="claim",
        assignment=assignment.pk,
        fee="50",
        allowance="0",
        expenses="0",
        attended=True,
    )
    claim = response.json()["claims"][0]["id"]
    assert post(c, url, action="approve", claim=claim).status_code == 200
    with tenant_context(club.pk):
        bank = Account.objects.create(
            organization=club,
            name="Auszahlungen",
            kind="bank",
            iban="DE89370400440532013000",
            opening_date="2025-01-01",
        )
    base = f"/api/orgs/{club.pk}/music/payout-runs/"
    values = {
        "bank_account": bank.pk,
        "execution_date": timezone.localdate().isoformat(),
        "items": [{"claim": claim, "holder": "Alex Beispiel", "iban": "DE89370400440532013000"}],
    }
    return base, values, url, claim


def create(c, base, values, key="f4d16420-a528-46dc-a90a-548f4b81b2cf"):
    return c.post(base, values, content_type=JSON, HTTP_IDEMPOTENCY_KEY=key)


def test_export_does_not_pay_and_reserves_claim(c, club, approved):
    base, values, url, claim = approved
    response = create(c, base, values)
    assert response.status_code == 201, response.content
    run = response.json()["id"]
    assert create(c, base, values).json()["id"] == run
    assert create(c, base, values, "e165965e-7dc6-4405-a306-9cb9eb3b76ef").status_code == 400
    assert post(c, url, action="void", claim=claim).status_code == 400
    first = post(c, f"{base}{run}/", action="export")
    assert first.status_code == 200, first.content
    assert post(c, f"{base}{run}/", action="export").content == first.content
    tree = etree.fromstring(first.content)
    assert tree.xpath("string(//*[local-name()='CtrlSum'])") == "50.00"
    assert tree.xpath("string(//*[local-name()='BtchBookg'])") == "false"
    assert not c.get(url).json()["claims"][0]["paid"]
    assert first["Cache-Control"] == "no-store"
    # A cash booking cannot silently settle an exported bank transfer.
    booking = expense(c, club, "50")
    assert post(c, url, action="payment", claim=claim, booking=booking).status_code == 400
    assert post(c, f"{base}{run}/", action="cancel").status_code == 200
    assert post(c, f"{base}{run}/", action="export").status_code == 400
    assert post(c, url, action="payment", claim=claim, booking=booking).status_code == 200


def test_invalid_account_and_payee_roll_back(c, club, approved):
    base, values, *_ = approved
    values["items"][0]["iban"] = "DE00000000000000000000"
    assert create(c, base, values).status_code == 400
    with tenant_context(club.pk):
        assert not PayoutRun.objects.exists()


def test_bank_reconciliation_and_reversal(c, club, approved):
    from django.db import transaction

    from finance.services import cancel_booking

    base, values, url, claim = approved
    booking_id = expense(c, club, "50")
    with tenant_context(club.pk):
        booking = Booking.objects.get(pk=booking_id)
        Account.objects.filter(pk=booking.account_id).update(
            kind="bank", iban="DE89370400440532013000"
        )
        values["bank_account"] = booking.account_id
    response = create(c, base, values)
    assert response.status_code == 201, response.content
    run = response.json()["id"]
    assert post(c, f"{base}{run}/", action="export").status_code == 200
    assert post(c, url, action="payment", claim=claim, booking=booking_id).status_code == 200
    assert post(c, url, action="payment", claim=claim, booking=booking_id).status_code == 200
    assert c.get(base).json()["runs"][0]["completed"]
    with tenant_context(club.pk), transaction.atomic():
        cancel_booking(Booking.objects.get(pk=booking_id), None, "Musterkorrektur")
    assert not c.get(base).json()["runs"][0]["completed"]
    assert post(c, f"{base}{run}/", action="export").status_code == 400
