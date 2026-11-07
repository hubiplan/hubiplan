"""Untereinheiten: Teilmenge der Module des Vereins (Modulverzeichnis, M5).

Erfundene Daten."""

import pytest

from access.modules import module_on
from access.views import organization_summary
from core.tenancy import rls_bypass
from organizations.models import Department

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "todos", "finance", "tax"]
    org.save()
    return org


def test_teilmenge_je_untereinheit(club, board_a, api):
    with rls_bypass():
        zug = Department.objects.create(
            organization=club, name="Jägerzug", founding_year=1950, own_workspace=True
        )
        gruppe = Department.objects.create(
            organization=club, parent=zug, name="Fahnengruppe", founding_year=1970
        )
    assert module_on(zug, "todos") and module_on(gruppe, "todos")
    assert "tax" in organization_summary(zug, set())["modules"]
    url = f"/api/orgs/{club.pk}/departments/{zug.pk}/"
    resp = api(board_a).patch(url, {"unit_hidden_modules": ["tax", "todos", "todos"]}, JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["unit_hidden_modules"] == ["tax", "todos"]
    with rls_bypass():
        zug.refresh_from_db()
        gruppe = Department.objects.get(pk=gruppe.pk)
    # Ausgeblendet gilt auch darunter; der Verein selbst ist nicht betroffen
    assert not module_on(zug, "todos") and not module_on(gruppe, "todos")
    assert module_on(zug, "events") and module_on(club, "todos")
    # Im Arbeitsbereich mit eigener Kasse fehlt jetzt Steuern & Gemeinnützigkeit
    assert "tax" not in organization_summary(zug, set())["modules"]
    # Eigene Module der Untereinheit (Kasse) und Unbekanntes lassen sich nicht ausblenden
    for wrong in (["finance"], ["gibt_es_nicht"]):
        resp = api(board_a).patch(url, {"unit_hidden_modules": wrong}, JSON)
        assert resp.status_code == 400, wrong
