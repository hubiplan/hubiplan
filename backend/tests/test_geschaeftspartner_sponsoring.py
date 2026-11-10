"""Geschäftspartner P4 (Konzept geschaeftspartner.md): Vereinbarungen mit Erinnerung,
Dankesbrief und Einwilligung für die Webseite."""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest

from billing.models import PartnerAgreement
from core.tenancy import tenant_context
from todos.models import Todo

from .test_geschaeftspartner import JSON, base, c, club, create  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def with_todos(club):
    modules = list(club.enabled_modules or [])
    if "todos" not in modules:
        club.enabled_modules = [*modules, "todos"]
        club.save(update_fields=["enabled_modules"])
    return club


def agreements(base, partner):
    return f"{base}{partner['id']}/agreements/"


def test_vereinbarung_mit_erinnerung(c, base, with_todos):
    partner = create(c, base, roles=["sponsor"])
    response = c.post(
        agreements(base, partner),
        {
            "title": "Hauptsponsor Schützenfest",
            "start": "2026-01-01",
            "end": "2026-12-31",
            "amount": "1500.00",
            "benefits": ["website", "banner", "website"],
            "tax_kind": "advertising",
        },
        content_type=JSON,
    )
    assert response.status_code == 201, response.content
    data = response.json()
    assert data["benefits"] == ["banner", "website"]
    assert data["reminder_due"] == "2026-11-01"
    with tenant_context(with_todos.pk):
        todo = Todo.objects.get(pk=data["reminder"])
        assert "Getränke Beispiel GmbH" in todo.title
    # Neues Enddatum verschiebt die Aufgabe, ohne Ende verschwindet sie
    moved = c.patch(
        f"{agreements(base, partner)}{data['id']}/", {"end": "2027-03-31"}, content_type=JSON
    )
    assert moved.json()["reminder_due"] == "2027-01-30"
    cleared = c.patch(f"{agreements(base, partner)}{data['id']}/", {"end": None}, content_type=JSON)
    assert cleared.json()["reminder_due"] is None
    with tenant_context(with_todos.pk):
        assert Todo.objects.get(pk=data["reminder"]).deleted_at is not None


def test_ende_vor_beginn_abgelehnt(c, base):
    partner = create(c, base)
    response = c.post(
        agreements(base, partner),
        {"title": "X", "start": "2026-05-01", "end": "2026-04-01"},
        content_type=JSON,
    )
    assert response.status_code == 400


def test_dankesbrief_als_pdf(c, base, club):
    partner = create(c, base, roles=["sponsor"])
    c.post(
        f"{base}{partner['id']}/contacts/",
        {"last_name": "Muster", "first_name": "Kim"},
        content_type=JSON,
    )
    made = c.post(
        agreements(base, partner),
        {"title": "Festschrift", "start": "2026-03-01", "in_kind": "zwei Fässer Bier"},
        content_type=JSON,
    ).json()
    response = c.post(f"{agreements(base, partner)}{made['id']}/thanks/", {}, content_type=JSON)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    with tenant_context(club.pk):
        assert PartnerAgreement.objects.get(pk=made["id"]).thanked_at is not None


def test_zusammenfuehren_nimmt_vereinbarungen_mit(c, base, club):
    keep = create(c, base)
    other = create(c, base, name="Getränke Beispiel")
    c.post(agreements(base, other), {"title": "Bande", "start": "2026-01-01"}, content_type=JSON)
    assert c.delete(f"{base}{other['id']}/").status_code == 400
    response = c.post(f"{base}{keep['id']}/merge/", {"other": other["id"]}, content_type=JSON)
    assert response.status_code == 200, response.content
    with tenant_context(club.pk):
        assert PartnerAgreement.objects.filter(partner_id=keep["id"]).count() == 1


def test_webseite_nur_mit_einwilligung(c, base, club):
    create(c, base, name="Ohne Einwilligung", roles=["sponsor"])
    create(
        c,
        base,
        name="Bäckerei Muster",
        roles=["sponsor"],
        website_consent=True,
        website_url="https://baeckerei.example.org",
    )
    response = c.get(f"/api/orgs/{club.pk}/website/partner-logos/")
    assert response.status_code == 200, response.content
    assert [(p["name"], p["url"]) for p in response.json()] == [
        ("Bäckerei Muster", "https://baeckerei.example.org")
    ]
