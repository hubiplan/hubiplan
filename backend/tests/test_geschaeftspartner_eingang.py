"""Geschäftspartner P3 (Konzept geschaeftspartner.md): Partner im E-Rechnungseingang,
Vorschlag, „Als Geschäftspartner anlegen“ und IBAN-Abgleich bei der Freigabe."""
# ruff: noqa: F811  (Fixtures als Parameter)

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from billing import einvoice_validator, incoming_mail
from billing.incoming_check import check_org
from billing.models import BusinessPartner, PartnerContact
from core.tenancy import tenant_context
from finance.models import Booking

from .test_m9_billing import JSON, base, c, club, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db

XML = (Path(__file__).parent / "data" / "einvoice-en16931.xml").read_bytes()
# Aus der Beispielrechnung
SELLER, VAT, IBAN = "Lieferant Beispiel", "DE123456789", "DE89370400440532013000"


@pytest.fixture(autouse=True)
def checks(monkeypatch, settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"
    monkeypatch.setattr(
        einvoice_validator,
        "validate",
        lambda xml, timeout=None: ({"status": "valid", "validator": "Test", "messages": []}, b""),
    )


def fin(club) -> str:
    return f"/api/orgs/{club.pk}/finance"


def upload(c, club) -> dict:
    response = c.post(
        f"{fin(club)}/incoming/",
        {"file": SimpleUploadedFile("rechnung.xml", XML, content_type="application/xml")},
    )
    assert response.status_code == 201, response.content
    check_org(club.pk)
    return c.get(f"{fin(club)}/incoming/{response.json()['id']}/").json()


def partner(club, **kwargs) -> BusinessPartner:
    values = {"name": "Anderer Name", "roles": ["supplier"], "details": {}, "bank": {}}
    values.update(kwargs)
    with tenant_context(club.pk):
        return BusinessPartner.objects.create(organization=club, **values)


def approve(c, club, item, **extra):
    return c.post(
        f"{fin(club)}/incoming/{item['id']}/review/",
        {"status": "approved", "note": "Leistung geprüft", **extra},
        content_type=JSON,
    )


def test_vorschlag_ueber_ust_id_vor_name(c, club):
    partner(club, name=SELLER)
    by_vat = partner(club, details={"vat_id": "de 123 456 789"})
    item = upload(c, club)
    assert item["partner"] is None
    assert item["suggested_partner"] == {"id": by_vat.pk, "name": "Anderer Name", "by": "vat_id"}


def test_vorschlag_ueber_iban_und_name(c, club):
    by_iban = partner(club, bank={"iban": "DE89 3704 0044 0532 0130 00"})
    item = upload(c, club)
    assert item["suggested_partner"]["id"] == by_iban.pk
    assert item["suggested_partner"]["by"] == "iban"
    with tenant_context(club.pk):
        BusinessPartner.objects.filter(pk=by_iban.pk).update(is_active=False)
    by_name = partner(club, name="lieferant beispiel")
    again = c.get(f"{fin(club)}/incoming/{item['id']}/").json()
    assert again["suggested_partner"]["id"] == by_name.pk
    assert again["suggested_partner"]["by"] == "name"


def test_als_partner_anlegen_und_zuordnen(c, club):
    item = upload(c, club)
    assert item["suggested_partner"] is None
    response = c.post(f"{fin(club)}/incoming/{item['id']}/create-partner/", {}, content_type=JSON)
    assert response.status_code == 201, response.content
    data = response.json()
    assert data["partner_name"] == SELLER and data["suggested_partner"] is None
    with tenant_context(club.pk):
        made = BusinessPartner.objects.get(pk=data["partner"])
        assert made.details["vat_id"] == VAT
        assert made.bank["iban"] == IBAN
        assert made.roles == ["supplier"] and made.is_supplier
        assert made.number
    # Zweites Anlegen nicht möglich, Lösen und erneut zuordnen schon
    again = c.post(f"{fin(club)}/incoming/{item['id']}/create-partner/", {}, content_type=JSON)
    assert again.status_code == 400
    path = f"{fin(club)}/incoming/{item['id']}/partner/"
    assert c.post(path, {"partner": None}, content_type=JSON).json()["partner"] is None
    assert c.post(path, {"partner": made.pk}, content_type=JSON).json()["partner"] == made.pk


def test_fremder_partner_nicht_zuordenbar(c, club, orgs):
    other = orgs["b"]
    with tenant_context(other.pk):
        foreign = BusinessPartner.objects.create(organization=other, name="Fremd", details={})
    item = upload(c, club)
    response = c.post(
        f"{fin(club)}/incoming/{item['id']}/partner/", {"partner": foreign.pk}, content_type=JSON
    )
    assert response.status_code == 404


def test_neue_iban_braucht_bestaetigung(c, club):
    known = partner(club, name=SELLER, bank={"iban": "DE02120300000000202051"})
    item = upload(c, club)
    assert item["iban_changed"] is True
    c.post(f"{fin(club)}/incoming/{item['id']}/partner/", {"partner": known.pk}, content_type=JSON)
    refused = approve(c, club, item)
    assert refused.status_code == 400
    assert "iban_confirmed" in refused.json()
    accepted = approve(c, club, item, iban_confirmed=True)
    assert accepted.status_code == 200, accepted.content
    assert accepted.json()["iban_changed"] is False
    with tenant_context(club.pk):
        known.refresh_from_db()
        assert known.bank["iban"] == IBAN and known.bank["changed_at"]


def test_gleiche_iban_ohne_bestaetigung(c, club):
    partner(club, name=SELLER, bank={"iban": IBAN})
    item = upload(c, club)
    assert item["iban_changed"] is False
    assert approve(c, club, item).status_code == 200


def test_buchung_uebernimmt_partner(c, club, setup):
    known = partner(club, name=SELLER, bank={"iban": IBAN})
    item = upload(c, club)
    c.post(f"{fin(club)}/incoming/{item['id']}/partner/", {"partner": known.pk}, content_type=JSON)
    assert approve(c, club, item).status_code == 200
    category = c.post(
        f"{fin(club)}/categories/", {"name": "Leistungen", "kind": "expense"}, content_type=JSON
    ).json()["id"]
    booking = c.post(
        f"{fin(club)}/bookings/",
        {
            "date": "2026-11-04",
            "amount": "119.00",
            "kind": "expense",
            "category": category,
            "account": setup["bank"],
            "text": "Leistung bezahlt",
        },
        content_type=JSON,
    ).json()["id"]
    response = c.post(
        f"{fin(club)}/incoming/{item['id']}/link/", {"booking": booking}, content_type=JSON
    )
    assert response.status_code == 200, response.content
    with tenant_context(club.pk):
        assert Booking.objects.get(pk=booking).partner_id == known.pk


def test_zusammenfuehren_nimmt_eingang_mit(c, club):
    keep = partner(club, name="Bleibt")
    other = partner(club, name=SELLER)
    item = upload(c, club)
    c.post(f"{fin(club)}/incoming/{item['id']}/partner/", {"partner": other.pk}, content_type=JSON)
    response = c.post(
        f"/api/orgs/{club.pk}/billing/partners/{keep.pk}/merge/",
        {"other": other.pk},
        content_type=JSON,
    )
    assert response.status_code == 200, response.content
    assert c.get(f"{fin(club)}/incoming/{item['id']}/").json()["partner"] == keep.pk


def test_ansprechpartner_macht_absender_bekannt(club):
    known = partner(club, name=SELLER)
    with tenant_context(club.pk):
        PartnerContact.objects.create(
            organization=club,
            partner=known,
            last_name="Muster",
            email="Buchhaltung@Lieferant.example.com",
        )
        assert incoming_mail._known_sender(club, "buchhaltung@lieferant.example.com")
        assert not incoming_mail._known_sender(club, "jemand@lieferant.example.com")
