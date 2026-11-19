# ruff: noqa: F811  (Fixtures aus test_m9_billing und test_anmeldungen)
"""Kassen-Link: Kassenpersonal ohne Konto nimmt offene Teilnahmegebühren bar an
(Anmeldung A6, Konzept 3.11). Alle Daten erfunden."""

import uuid

import pytest
from django.test import Client

from billing.models import Invoice, Payment
from core.tenancy import tenant_context
from registrations import tickets
from registrations.models import Participant

from .test_anmeldungen import JSON, einrichten, fest, ok, soon  # noqa: F401
from .test_anmeldungen_scanlinks import _anmelden, _token
from .test_m9_billing import base, c, club, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db


def test_kassen_link_nimmt_bar_an(c, fest, club, setup):
    einrichten(c, fest)
    _anmelden(fest, "Anna", meal=False)
    links = f"{fest['url']}scan-links/"
    listing = ok(c.get(links))
    assert [a["id"] for a in listing["cash_accounts"]] == [setup["cash"]]
    # Nur Barkassen
    resp = c.post(
        links,
        {"label": "Abendkasse", "cash_account": setup["bank"], "cashier": "Kim Kasse"},
        content_type=JSON,
    )
    assert resp.status_code == 400
    link = ok(
        c.post(
            links,
            {"label": "Abendkasse", "cash_account": setup["cash"], "cashier": "Kim Kasse"},
            content_type=JSON,
        )
    )
    assert link["cash"] and link["cash_total"] == "0.00"
    staff = Client()
    api = f"/api/public/scan/{_token(link['url'])}/"
    assert ok(staff.get(api))["cash"] is True
    with tenant_context(club.pk):
        anna = Participant.objects.select_related("registration__invoice").get(
            membership=fest["anna"]
        )
        code = tickets.code(anna)
        open_amount = anna.registration.invoice.outstanding
    scanned = ok(staff.post(api, {"code": code}, content_type=JSON))
    assert scanned["card"]["open_amount"] == str(open_amount)
    key = str(uuid.uuid4())
    body = {"participant": scanned["card"]["id"], "request_key": key}
    paid = ok(staff.post(f"{api}cash/", body, content_type=JSON))
    assert paid["result"] == "paid" and paid["card"]["open_amount"] is None
    assert paid["card"]["paid_state"] == "paid"
    # Doppelt getippt: keine zweite Zahlung
    ok(staff.post(f"{api}cash/", body, content_type=JSON))
    with tenant_context(club.pk):
        pays = list(Payment.objects.filter(invoice_id=anna.registration.invoice_id))
        assert len(pays) == 1 and pays[0].method == "cash"
        assert pays[0].booking.account_id == setup["cash"]
        assert "Abendkasse" in pays[0].booking.text and "Kim Kasse" in pays[0].booking.text
        assert Invoice.objects.get(pk=anna.registration.invoice_id).status == "paid"
    # Nichts mehr offen
    again = staff.post(
        f"{api}cash/",
        {"participant": scanned["card"]["id"], "request_key": str(uuid.uuid4())},
        content_type=JSON,
    )
    assert again.status_code == 400
    # Kassenabschluss je Link
    row = ok(c.get(links))["links"][0]
    assert row["cash_total"] == str(open_amount) and len(row["cash_takes"]) == 1
    assert row["cash_takes"][0]["name"] == "Anna Muster"


def test_ohne_kasse_kein_bargeld(c, fest, club, setup):
    einrichten(c, fest)
    _anmelden(fest, "Anna", meal=False)
    link = ok(c.post(f"{fest['url']}scan-links/", {"label": "Eingang"}, content_type=JSON))
    staff = Client()
    api = f"/api/public/scan/{_token(link['url'])}/"
    with tenant_context(club.pk):
        anna = Participant.objects.get(membership=fest["anna"])
    resp = staff.post(
        f"{api}cash/",
        {"participant": anna.pk, "request_key": str(uuid.uuid4())},
        content_type=JSON,
    )
    assert resp.status_code == 404
