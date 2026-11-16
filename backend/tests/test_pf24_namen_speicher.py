"""Mitgliederliste: entschlüsselte Namen im Arbeitsspeicher (Gesamtaudit 15.11., PF-24).

Jede Seite und jede Suche entschlüsselte alle Namen der Einheit neu. Jetzt hält ein kleiner
Zwischenspeicher je Prozess die entschlüsselten Werte, Schlüssel ist das Chiffrat. Namen bleiben
in der Datenbank vollständig verschlüsselt (Fachfrage F1). Erfundene Daten.
"""

import pytest

from core.tenancy import rls_bypass
from members import personsearch
from members.models import Membership, Person

from .factories import give_role, make_member, make_org, make_user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def leer():
    personsearch.PLAIN.clear()
    yield
    personsearch.PLAIN.clear()


@pytest.fixture
def verein(api):
    club = make_org("Namensverein")
    chef = make_user("vorstand-namen@example.org")
    give_role(chef, club)
    for first, last in (("Erika", "Geheim"), ("Max", "Muster"), ("Ida", "Beispiel")):
        make_member(club, first, last)
    return club, api(chef)


def _names(resp):
    return [f"{r['first_name']} {r['last_name']}" for r in resp.json()["results"]]


def test_wie_ohne_zwischenspeicher(verein):
    club, _c = verein
    with rls_bypass():
        qs = Membership.objects.filter(organization=club)
        expected = sorted(qs.values_list("pk", "person__last_name", "person__first_name"))
        got = sorted(personsearch.plain_values(qs, "person__last_name", "person__first_name"))
        assert got == expected
        # Zweiter Durchlauf aus dem Speicher: gleiches Ergebnis
        assert (
            sorted(personsearch.plain_values(qs, "person__last_name", "person__first_name"))
            == expected
        )


def test_nur_chiffrat_als_schluessel(verein):
    club, c = verein
    assert c.get(f"/api/orgs/{club.pk}/members/").status_code == 200
    keys = list(personsearch.PLAIN.items)
    assert keys
    for _label, _attname, value in keys:
        assert value.startswith("enc1:") and "Geheim" not in value


def test_geaenderter_name_nicht_mehr_gefunden(verein):
    club, c = verein
    base = f"/api/orgs/{club.pk}/members/"
    assert _names(c.get(base + "?suche=Geheim")) == ["Erika Geheim"]
    with rls_bypass():
        target = next(
            p
            for p in Person.objects.filter(memberships__organization=club)
            if p.last_name == "Geheim"
        )
        target.last_name = "Anonym"
        target.first_name = "Anonym"
        target.save()
    assert c.get(base + "?suche=Geheim").json()["results"] == []
    assert "Erika Geheim" not in _names(c.get(base))
    assert "Anonym Anonym" in _names(c.get(base))


def test_obergrenze_und_ablauf(monkeypatch):
    cache = personsearch._PlainCache(size=2, ttl=10)
    now = [100.0]
    monkeypatch.setattr(personsearch.time, "monotonic", lambda: now[0])
    cache.put("a", "1")
    cache.put("b", "2")
    cache.put("c", "3")
    assert cache.get("a") is None and len(cache.items) == 2
    assert cache.get("c") == "3"
    now[0] += 11
    assert cache.get("c") is None and cache.get("b") is None
