"""Abrechnung: Freigabe, Zahlung, Storno, Rechte und Rechnungsoriginale."""
# ruff: noqa: F811

import datetime
import uuid

import pytest
from django.db import transaction
from django.utils import timezone

from core.tenancy import tenant_context
from finance import services
from finance.models import Booking
from music.models import (
    Assignment,
    Musician,
    MusicianClaim,
    Performance,
    PerformanceAccount,
    Position,
)
from portal.models import PortalAccess

from .factories import give_role, make_member, make_user
from .test_einvoice_workflow import payload  # noqa: F401
from .test_m9_billing import base  # noqa: F401
from .test_music import JSON, c, club, music  # noqa: F401
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db


def test_export_uses_fixed_period_and_retention_clears_notes(c, club, settlement):
    from finance.retention import _anonymize_records
    from music.finance_export import export_tables

    url, assignment = settlement
    post(
        c, url, action="agreement", fee="100", travel="0", extras="0", note="Vereinbarung Beispiel"
    )
    post(
        c,
        url,
        action="claim",
        assignment=assignment.pk,
        fee="50",
        allowance="0",
        expenses="0",
        attended=True,
        note="Auslagen Beispiel",
    )
    with tenant_context(club.pk):
        account = PerformanceAccount.objects.get(performance=assignment.performance)
        start, end = club.fiscal_range(club.fiscal_year_of(account.date))
        event = assignment.performance.event
        event.starts_at += datetime.timedelta(days=800)
        event.ends_at += datetime.timedelta(days=800)
        event.save()
        tables = export_tables(club, start, end)
        assert len(tables[0].rows) == len(tables[1].rows) == 1
        assert "Vereinbarung Beispiel" in tables[0].content().decode("utf-8-sig")
        _anonymize_records(club, start, end)
        account.refresh_from_db()
        assert account.note == ""
        assert MusicianClaim.objects.get(assignment=assignment).note == ""


@pytest.fixture
def settlement(c, club, music):
    _, event = music
    with tenant_context(club.pk):
        event.starts_at = timezone.now() - datetime.timedelta(days=2)
        event.ends_at = timezone.now() - datetime.timedelta(days=1)
        event.save()
        musician = Musician.objects.create(organization=club, name="Alex Beispiel")
        performance = Performance.objects.create(organization=club, event=event)
        position = Position.objects.create(
            organization=club, performance=performance, instrument="Tuba"
        )
        assignment = Assignment.objects.create(
            organization=club, performance=performance, position=position, musician=musician
        )
    return f"/api/orgs/{club.pk}/music/performances/{performance.pk}/settlement/", assignment


def post(c, url, **data):
    return c.post(url, data, content_type=JSON)


def expense(c, club, amount):
    base = f"/api/orgs/{club.pk}/finance"
    account = post(
        c, f"{base}/accounts/", name="Musterkonto", kind="cash", opening_date="2025-01-01"
    ).json()["id"]
    category = post(c, f"{base}/categories/", name="Musikvergütungen", kind="expense").json()["id"]
    result = post(
        c,
        f"{base}/bookings/",
        kind="expense",
        account=account,
        category=category,
        date=timezone.localdate().isoformat(),
        amount=amount,
        text="Auszahlung Beispiel",
    )
    assert result.status_code == 201, result.content
    return result.json()["id"]


def test_claim_payment_storno_and_overview(c, club, settlement):
    url, assignment = settlement
    assert post(c, url, action="agreement", fee="100", travel="20", extras="0").status_code == 200
    values = dict(
        action="claim",
        assignment=assignment.pk,
        fee="40",
        allowance="5",
        expenses="5",
        attended=False,
    )
    r = post(c, url, **values)
    assert r.status_code == 200, r.content
    claim = r.json()["claims"][0]["id"]
    assert post(c, url, action="approve", claim=claim).status_code == 400
    values["attended"] = True
    assert post(c, url, **values).status_code == 200
    assert post(c, url, action="approve", claim=claim).status_code == 200
    assert post(c, url, **values).status_code == 400
    booking = expense(c, club, "50")
    assert post(c, url, action="payment", claim=claim, booking=booking).status_code == 200
    # Wiederholung bleibt genau eine Zuordnung.
    result = post(c, url, action="payment", claim=claim, booking=booking).json()
    assert len(result["payments"]) == 1
    assert result["expenses"] == "50.00" and result["result"] == "-50.00"
    assert result["claims"][0]["paid"] is True
    assert post(c, url, action="void", claim=claim).status_code == 400
    assert (
        c.patch(
            f"/api/orgs/{club.pk}/finance/bookings/{booking}/", {"amount": "1"}, content_type=JSON
        ).status_code
        == 400
    )
    assert post(c, url, action="replace_invoice").status_code == 400
    with tenant_context(club.pk), transaction.atomic():
        services.cancel_booking(Booking.objects.get(pk=booking), None, "Auszahlung korrigieren")
    result = c.get(url).json()
    assert result["expenses"] == "0" and not result["claims"][0]["paid"]
    assert post(c, url, action="void", claim=claim).status_code == 200
    assert post(c, url, action="reopen", claim=claim).status_code == 200


def test_financial_permissions_and_tenant_scope(api, c, club, orgs, settlement):
    url, assignment = settlement
    user = make_user("musik-leser@example.org")
    give_role(user, club, permissions=["music.view", "events.view"], name="Musikplanung")
    assert api(user).get(url).status_code == 403
    user2 = make_user("kassenpruefung@example.org")
    give_role(
        user2, club, permissions=["music.view", "events.view", "finance.view"], name="Musikprüfung"
    )
    assert api(user2).get(url).status_code == 200
    assert (
        post(api(user2), url, action="agreement", fee="1", travel="0", extras="0").status_code
        == 403
    )
    assert (
        post(
            c,
            url,
            action="claim",
            assignment=assignment.pk,
            fee="-1",
            allowance="0",
            expenses="0",
            attended=True,
        ).status_code
        == 400
    )
    with tenant_context(club.pk):
        account = PerformanceAccount.objects.create(
            organization=club, performance=assignment.performance
        )
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert not PerformanceAccount.objects.filter(pk=account.pk).exists()


def test_performance_invoice_is_single_and_bound_to_agreement(c, club, settlement, payload):
    url, assignment = settlement
    with tenant_context(club.pk):
        performance = assignment.performance
        performance.customer_id = payload["partner"]
        performance.save()
    from billing.einvoice_schema import CommercialInvoiceSerializer
    from billing.einvoice_xml import calculate

    schema = CommercialInvoiceSerializer(data=payload)
    schema.is_valid(raise_exception=True)
    amount = str(calculate(schema.validated_data["lines"])["gross"])
    assert post(c, url, action="agreement", fee=amount, travel="0", extras="0").status_code == 200
    invoice_url = url.replace("settlement/", "invoice/")
    r = c.post(invoice_url, payload, content_type=JSON, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert r.status_code == 201, r.content
    invoice = r.json()["id"]
    retry = c.post(invoice_url, payload, content_type=JSON, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert retry.json()["id"] == invoice
    assert post(c, url, action="agreement", fee="5", travel="0", extras="0").status_code == 400
    changed = dict(
        payload, partner=payload["partner"], lines=[{**payload["lines"][0], "unit_price": "999"}]
    )
    assert (
        c.patch(
            f"/api/orgs/{club.pk}/billing/electronic/{invoice}/", changed, content_type=JSON
        ).status_code
        == 400
    )


def test_personal_claim_is_private(api, c, club, settlement):
    url, assignment = settlement
    user = make_user("musiker@example.org")
    member = make_member(club, "Mika", "Beispiel")
    with tenant_context(club.pk):
        musician = assignment.musician
        musician.membership = member
        musician.save()
        access = PortalAccess.objects.create(organization=club, membership=member, user=user)
    result = post(
        c,
        url,
        action="claim",
        assignment=assignment.pk,
        fee="50",
        allowance="0",
        expenses="0",
        attended=True,
    )
    claim = result.json()["claims"][0]["id"]
    portal_url = f"/api/portal/{access.pk}/music/"
    assert api(user).get(portal_url).json()[0]["settlement"] is None
    assert post(c, url, action="approve", claim=claim).status_code == 200
    personal = api(user).get(portal_url).json()[0]["settlement"]
    assert personal["total"] == "50.00" and "note" not in personal
    assert api(user).get(url).status_code in (403, 404)
