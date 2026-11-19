"""Rechnung über die Miete aus einer Buchung für ein Mitglied („Rechnung anlegen“)."""

from decimal import Decimal

import pytest

from billing.models import Invoice
from bookings.models import Booking

from .factories import give_role, make_user
from .test_belegung_mitglied import mitglied  # noqa: F401  (Fixture)
from .test_buchungen import JSON, at, book, setup  # noqa: F401  (Fixture)

pytestmark = pytest.mark.django_db


@pytest.fixture
def kasse(mitglied, api):  # noqa: F811
    s = mitglied
    org = s["org"]
    org.enabled_modules = sorted(set(org.enabled_modules) | {"billing"})
    org.save(update_fields=["enabled_modules"])
    user = make_user("kasse@example.org")
    give_role(
        user,
        org,
        permissions=["infrastructure.edit", "members.view", "billing.view", "billing.edit"],
        name="Kasse",
    )
    s["kasse"] = api(user)
    rules = {**s["hall"].booking_rules, "price": "12.50", "price_unit": "hour"}
    s["hall"].booking_rules = rules
    s["hall"].save(update_fields=["booking_rules"])
    return s


def test_rechnungsentwurf_an_das_mitglied(kasse):
    s = kasse
    booking = book(
        s["kasse"], s["url"], s["hall"], at(2, 18), at(2, 22), member=s["membership"].pk
    ).json()
    assert booking["can_invoice"] is True
    assert booking["price_suggestion"] == "50.00"
    response = s["kasse"].post(
        f"{s['url']}{booking['id']}/invoice/",
        {"amount": booking["price_suggestion"], "version": booking["version"]},
        content_type=JSON,
    )
    assert response.status_code == 201, response.content
    data = response.json()
    invoice = Invoice.objects.get(pk=data["invoice"])
    assert invoice.status == Invoice.Status.DRAFT
    assert invoice.recipient_kind == Invoice.Recipient.MEMBER
    assert invoice.membership_id == s["membership"].pk
    assert invoice.total == Decimal("50.00")
    assert invoice.subject == "Miete Saal"
    line = invoice.lines.get()
    assert line.text == "Saal: Training"
    assert "18:00–22:00" in line.detail
    assert data["invoice_number"] == "Entwurf" and data["can_invoice"] is False
    # Kein zweiter Entwurf für dieselbe Buchung
    again = s["kasse"].post(
        f"{s['url']}{booking['id']}/invoice/",
        {"amount": "50.00", "version": data["version"]},
        content_type=JSON,
    )
    assert again.status_code == 400
    # Entwurf gelöscht: die Buchung ist wieder abrechenbar
    invoice.delete()
    assert Booking.objects.get(pk=booking["id"]).invoice_id is None


def test_ohne_rechnungsrecht_oder_ohne_mitglied(kasse):
    s = kasse
    # Verwalter ohne Rechnungsrecht sieht weder Rechnung noch Knopf
    own = book(
        s["vorstand"], s["url"], s["hall"], at(3, 18), at(3, 20), member=s["membership"].pk
    ).json()
    assert own["can_invoice"] is False and "price_suggestion" not in own
    denied = s["vorstand"].post(
        f"{s['url']}{own['id']}/invoice/",
        {"amount": "10.00", "version": own["version"]},
        content_type=JSON,
    )
    assert denied.status_code == 403
    # Ohne Mitglied gibt es keine Rechnung aus der Buchung
    plain = book(s["kasse"], s["url"], s["hall"], at(4, 18), at(4, 20)).json()
    assert plain["can_invoice"] is False
    refused = s["kasse"].post(
        f"{s['url']}{plain['id']}/invoice/",
        {"amount": "10.00", "version": plain["version"]},
        content_type=JSON,
    )
    assert refused.status_code == 400
    assert not Invoice.objects.filter(organization=s["org"]).exists()


def test_mietpreis_je_tag_und_einstellung(kasse):
    from bookings.rules import RulesInput
    from bookings.views import price_suggestion

    s = kasse
    form = RulesInput(data={"enabled": True, "price": "30", "price_unit": "day"})
    assert form.is_valid(), form.errors
    assert form.validated_data["price"] == "30.00"
    empty = RulesInput(data={"enabled": True, "price": None})
    assert empty.is_valid() and empty.validated_data["price"] == ""
    s["hall"].booking_rules = {**s["hall"].booking_rules, "price": "30.00", "price_unit": "day"}
    s["hall"].save(update_fields=["booking_rules"])
    booking = book(
        s["kasse"],
        s["url"],
        s["hall"],
        at(5, 0),
        at(6, 0),
        all_day=True,
        member=s["membership"].pk,
    ).json()
    assert price_suggestion(Booking.objects.get(pk=booking["id"])) == "60.00"
