"""Gesamtaudit 11.11., P-06: Die Auswahl für Aufgaben-Freigaben prüft jedes Konto je Einheit
nur einmal (vorher die eigene Einheit doppelt und je Konto mit Sitzungsvariablen). Erfundene
Daten."""

from collections import Counter
from unittest.mock import patch

import pytest

from access.permissions import permissions_in
from organizations.models import Department
from todos import sharing

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db


def test_auswahl_richtig_und_jedes_konto_einmal_je_einheit(api, board_a, orgs):
    org = orgs["a"]
    Department.objects.create(organization=org, parent=org, name="Jägerzug")
    reader = make_user("aufgaben-lesen@example.org", first_name="Lea", last_name="Muster")
    give_role(reader, org, permissions=["todos.view"], name="Aufgaben lesen")
    other = make_user("ohne-aufgaben@example.org")
    give_role(other, org, permissions=["members.view"], name="Mitglieder lesen")

    calls: Counter = Counter()

    def counting(user, unit):
        calls[(user.pk, unit.pk)] += 1
        return permissions_in(user, unit)

    with patch.object(sharing, "permissions_in", counting):
        resp = api(board_a).get(f"/api/orgs/{org.pk}/todos/choices/")
    assert resp.status_code == 200, resp.content
    data = resp.json()
    ids = {u["id"] for u in data["users"]}
    assert {board_a.pk, reader.pk} <= ids and other.pk not in ids
    own = next(u for u in data["units"] if u["organization"] == org.pk and not u["department"])
    assert {u["id"] for u in own["users"]} == ids
    assert any(u["department"] for u in data["units"])
    assert any(u["organization"] == orgs["federation"].pk for u in data["units"])
    # Vorher wurde die eigene Einheit zweimal berechnet
    assert calls and max(calls.values()) == 1
