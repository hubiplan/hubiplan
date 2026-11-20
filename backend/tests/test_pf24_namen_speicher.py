"""Mitgliederliste: entschlüsselte Namen im Arbeitsspeicher (Gesamtaudit 15.11., PF-24).

Jede Suche entschlüsselte alle Namen der Einheit neu. Jetzt hält ein kleiner Zwischenspeicher
je Prozess die entschlüsselten Werte für die Suche, Schlüssel ist das Chiffrat. Namen bleiben
in der Datenbank vollständig verschlüsselt (Fachfrage F1). Erfundene Daten.
"""

import pytest

from core.tenancy import rls_bypass
from members import personsearch
from members.models import ContactPerson, Membership, Person

from .factories import give_role, make_member, make_org, make_user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def leer():
    personsearch.PLAIN.clear()
    personsearch.SORT_KEYS.clear()
    yield
    personsearch.PLAIN.clear()
    personsearch.SORT_KEYS.clear()


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
    assert c.get(f"/api/orgs/{club.pk}/members/?suche=Muster").status_code == 200
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


def test_obergrenze_und_gleitender_ablauf(monkeypatch):
    cache = personsearch._PlainCache(size=2, ttl=10)
    now = [100.0]
    monkeypatch.setattr(personsearch.time, "monotonic", lambda: now[0])
    cache.put("a", "1")
    cache.put("b", "2")
    cache.put("c", "3")
    assert cache.get("a") is None and len(cache.items) == 2  # Obergrenze
    now[0] += 8
    assert cache.get("c") == "3"  # benutzt: Ablauf beginnt neu
    now[0] += 8
    assert cache.get("b") is None  # ungenutzt: nach 16 s heraus
    assert cache.get("c") == "3"  # genutzt vor 8 s: bleibt
    now[0] += 11
    assert cache.get("c") is None


def test_altbestand_ohne_praefix_und_leere_werte(verein):
    """Altbestand im Klartext (ohne „enc1:“) und leere Werte wie bei values_list."""
    from django.db import connection

    club, _c = verein
    with rls_bypass():
        person_id = Membership.objects.filter(organization=club).values_list(
            "person_id", flat=True
        )[0]
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE members_person SET last_name = %s, first_name = %s WHERE id = %s",
                ["Altname", "", person_id],
            )
        qs = Membership.objects.filter(organization=club)
        expected = sorted(qs.values_list("pk", "person__last_name", "person__first_name"))
        got = sorted(personsearch.plain_values(qs, "person__last_name", "person__first_name"))
    assert got == expected
    assert any(row[1] == "Altname" and row[2] == "" for row in got)


def test_beziehung_ohne_person_liefert_none(verein):
    """Ansprechpartner ohne verknüpfte Person: der Pfad über die Person ist NULL."""
    club, _c = verein
    with rls_bypass():
        membership = Membership.objects.filter(organization=club).first()
        contact = ContactPerson.objects.create(
            organization=club, membership=membership, last_name="Frei", first_name="Hans"
        )
        rows = list(
            personsearch.plain_values(
                ContactPerson.objects.filter(pk=contact.pk), "person__last_name", "last_name"
            )
        )
    assert rows == [(contact.pk, None, "Frei")]


def test_abgelaufener_klartext_verlaesst_den_speicher(monkeypatch):
    """Nie mehr abgefragte Einträge (etwa anonymisierte Namen) bleiben nicht bis zur
    Obergrenze liegen: Nach Ablauf entfernt sie der nächste Zugriff."""
    cache = personsearch._PlainCache(size=1000, ttl=10)
    now = [100.0]
    monkeypatch.setattr(personsearch.time, "monotonic", lambda: now[0])
    cache.put(("m", "last_name", "enc1:alt"), "Erika Geheim")
    now[0] += 11
    cache.put(("m", "last_name", "enc1:neu"), "Anonym")
    assert all(value != "Erika Geheim" for _expires, value in cache.items.values())
    assert len(cache.items) == 1


def test_sortierung_aus_dem_speicher_wie_ohne(verein):
    """Gesamtaudit 19.11., P-04: Die Liste hält die Sortierschlüssel der Namen im Speicher.
    Reihenfolge wie beim ersten Aufruf, Schlüssel ist nur das Chiffrat."""
    club, c = verein
    base = f"/api/orgs/{club.pk}/members/"
    first = _names(c.get(base))
    assert first == ["Ida Beispiel", "Erika Geheim", "Max Muster"]
    keys = list(personsearch.SORT_KEYS.items)
    assert len(keys) == 6  # Vor- und Nachname von drei Mitgliedern
    for _label, _attname, value in keys:
        assert value.startswith("enc1:") and "Geheim" not in value
    # Zweiter Aufruf aus dem Speicher: gleiche Reihenfolge, auch absteigend
    assert _names(c.get(base)) == first
    assert _names(c.get(base + "?sortierung=-name")) == first[::-1]
    assert len(personsearch.SORT_KEYS.items) == 6


def test_geaenderter_name_sortiert_neu(verein):
    club, c = verein
    base = f"/api/orgs/{club.pk}/members/"
    assert _names(c.get(base))[0] == "Ida Beispiel"
    with rls_bypass():
        target = next(
            p
            for p in Person.objects.filter(memberships__organization=club)
            if p.last_name == "Muster"
        )
        target.last_name = "Ahorn"
        target.save()
    # Neues Chiffrat, neuer Schlüssel: der alte Eintrag wird nicht mehr getroffen
    assert _names(c.get(base)) == ["Max Ahorn", "Ida Beispiel", "Erika Geheim"]
