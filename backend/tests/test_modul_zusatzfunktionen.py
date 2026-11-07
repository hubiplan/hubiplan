"""Zusatzfunktionen der Module unter Einstellungen › Module (Modulverzeichnis, M4).

Erfundene Daten."""

import pytest

from access.modules import EXTRAS, MODULE_BY_ID
from billing.models import BillingSettings
from organizations.models import Organization

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _extras(data):
    return {e["id"]: e["on"] for g in data["groups"] for m in g["modules"] for e in m["extras"]}


def test_verzeichnis_der_zusatzfunktionen():
    for extra in EXTRAS:
        assert extra.module in MODULE_BY_ID, extra.id
        if extra.store == "org":
            Organization._meta.get_field(extra.field)
        else:
            BillingSettings._meta.get_field(extra.field)


def test_zusatzfunktionen_schalten(orgs, board_a, api):
    org = orgs["a"]
    org.enabled_modules = ["members", "finance", "tax", "billing"]
    org.released_modules = list(org.enabled_modules)
    org.save()
    c = api(board_a)
    base = f"/api/orgs/{org.pk}/modules/"
    state = _extras(c.get(base).json())
    assert state["cash_counts"] is False and state["sepa"] is False
    assert "contact_approval" not in state or state["contact_approval"] is False
    resp = c.patch(base, {"extras": {"cash_counts": True, "sepa": True, "reserves": True}}, JSON)
    assert resp.status_code == 200, resp.content
    state = _extras(resp.json())
    assert state["cash_counts"] and state["sepa"] and state["reserves"]
    org.refresh_from_db()
    assert org.cash_counts_enabled and org.reserves_enabled
    assert BillingSettings.objects.get(organization=org).sepa_enabled
    # Modul aus: Zusatzfunktion nicht schaltbar
    resp = c.patch(base, {"extras": {"photo_approval": True, "contact_approval": True}}, JSON)
    assert resp.status_code == 400
    resp = c.patch(base, {"extras": {"gibt_es_nicht": True}}, JSON)
    assert resp.status_code == 400
    resp = c.patch(base, {"extras": {"datev": "ja"}}, JSON)
    assert resp.status_code == 400
