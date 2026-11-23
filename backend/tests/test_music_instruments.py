"""Musik: feste Instrumentenliste je Einheit (konzepte/instrumente.md).

Alles erfunden (Musterkapelle, Musterstadt).
"""
# ruff: noqa: F811

import importlib

import pytest
from django.apps import apps

from core.tenancy import tenant_context
from music.models import (
    EnsembleTemplate,
    EnsembleTemplatePosition,
    Instrument,
    Musician,
    Position,
    Skill,
)

from .test_music import JSON, c, club, music  # noqa: F401

pytestmark = pytest.mark.django_db


def post(c, url, data, status=201):
    r = c.post(url, data, content_type=JSON)
    assert r.status_code == status, r.content
    return r.json()


def patch(c, url, data, status=200):
    r = c.patch(url, data, content_type=JSON)
    assert r.status_code == status, r.content
    return r.json()


def names(club):
    with tenant_context(club.pk):
        return list(Instrument.objects.filter(organization=club).values_list("name", flat=True))


def test_vorbelegung_einmal_und_nach_gruppen(c, club, music):
    base, _ = music
    rows = c.get(f"{base}/instruments/").json()
    by_name = {r["name"]: r for r in rows}
    assert {"Trompete", "Klarinette", "Altsaxofon", "Lyra", "Marschtrommel", "Gesang"} <= set(
        by_name
    )
    assert by_name["Klarinette"]["group"] == "wood"
    assert by_name["Tenorhorn"]["group"] == "brass"
    assert by_name["Spielmannsflöte (Sopran)"]["group"] == "corps"
    assert [r["position"] for r in rows] == sorted(r["position"] for r in rows)
    assert all(r["used"] == 0 and r["active"] for r in rows)
    # Zweiter Abruf legt nichts doppelt an
    assert len(c.get(f"{base}/instruments/").json()) == len(rows)


def test_eingaben_auf_die_liste_gebracht(c, club, music):
    base, event = music
    musician = post(c, f"{base}/musicians/", {"name": "Alex Beispiel"})["id"]
    skill = post(c, f"{base}/skills/", {"musician": musician, "instrument": " trompete "})
    assert skill["instrument"] == "Trompete"
    assert (
        post(c, f"{base}/skills/", {"musician": musician, "instrument": "Altsaxophon"})[
            "instrument"
        ]
        == "Altsaxofon"
    )
    assert (
        post(c, f"{base}/skills/", {"musician": musician, "instrument": "Waldhorn"})["instrument"]
        == "Horn"
    )
    # Gleiches Instrument in anderer Schreibweise ist dieselbe Fähigkeit
    r = c.post(
        f"{base}/skills/", {"musician": musician, "instrument": "TROMPETE"}, content_type=JSON
    )
    assert r.status_code == 400
    # Unbekanntes kommt als neuer Eintrag in die Liste („Weitere“)
    new = post(c, f"{base}/skills/", {"musician": musician, "instrument": "Alphorn"})
    assert new["instrument"] == "Alphorn"
    rows = {r["name"]: r for r in c.get(f"{base}/instruments/").json()}
    assert rows["Alphorn"]["group"] == "other"
    assert rows["Trompete"]["used"] == 1
    performance = post(c, f"{base}/performances/", {"event": event.pk})["id"]
    position = post(
        c,
        f"{base}/positions/",
        {"performance": performance, "instrument": "trompete", "required": 1},
    )
    assert position["instrument"] == "Trompete"
    # Einteilen findet die Fähigkeit trotz anderer Schreibweise der Eingabe
    post(
        c,
        f"{base}/assignments/",
        {"performance": performance, "position": position["id"], "musician": musician},
    )


def test_umbenennen_zieht_mit_loeschen_nur_unbenutzt(c, club, music):
    base, event = music
    musician = post(c, f"{base}/musicians/", {"name": "Bea Beispiel"})["id"]
    post(c, f"{base}/skills/", {"musician": musician, "instrument": "Flügelhorn"})
    performance = post(c, f"{base}/performances/", {"event": event.pk})["id"]
    post(
        c,
        f"{base}/positions/",
        {"performance": performance, "instrument": "Flügelhorn", "required": 2},
    )
    rows = {r["name"]: r for r in c.get(f"{base}/instruments/").json()}
    horn = rows["Flügelhorn"]
    assert horn["used"] == 2
    # Name schon vergeben (auch in anderer Schreibweise)
    patch(c, f"{base}/instruments/{horn['id']}/", {"name": "trompete"}, status=400)
    patch(c, f"{base}/instruments/{horn['id']}/", {"name": "Flügelhorn in B"})
    with tenant_context(club.pk):
        assert Skill.objects.get(musician_id=musician).instrument == "Flügelhorn in B"
        assert Position.objects.get(performance_id=performance).instrument == "Flügelhorn in B"
    assert c.delete(f"{base}/instruments/{horn['id']}/").status_code == 400
    patch(c, f"{base}/instruments/{horn['id']}/", {"active": False})
    unused = rows["Harfe"]
    assert c.delete(f"{base}/instruments/{unused['id']}/").status_code == 204
    assert "Harfe" not in names(club)
    own = post(c, f"{base}/instruments/", {"name": "Dudelsack", "group": "other"})
    assert own["position"] == max(r["position"] for r in c.get(f"{base}/instruments/").json())
    post(c, f"{base}/instruments/", {"name": "dudelsack"}, status=400)


def test_reihenfolge(c, club, music):
    base, _ = music
    rows = c.get(f"{base}/instruments/").json()
    ids = [r["id"] for r in rows]
    post(c, f"{base}/instruments/order/", {"ids": ids[1:]}, status=400)
    post(c, f"{base}/instruments/order/", {"ids": list(reversed(ids))}, status=200)
    assert [r["id"] for r in c.get(f"{base}/instruments/").json()] == list(reversed(ids))


def test_ohne_musikmodul_keine_liste(c, club):
    assert c.get(f"/api/orgs/{club.pk}/music/instruments/").status_code == 404


def test_bestand_wird_uebernommen(club, music):
    migration = importlib.import_module("music.migrations.0023_instrumente")
    with tenant_context(club.pk):
        musician = Musician.objects.create(organization=club, name="Carla Beispiel")
        # Ohne Signal angelegt wie ein alter Bestand mit getippten Schreibweisen
        Skill.objects.bulk_create(
            [
                Skill(organization=club, musician=musician, instrument="Saxophon", primary=False),
                Skill(organization=club, musician=musician, instrument="saxofon ", primary=True),
                Skill(organization=club, musician=musician, instrument="trompete"),
            ]
        )
        template = EnsembleTemplate.objects.create(organization=club, name="Marsch")
        EnsembleTemplatePosition.objects.bulk_create(
            [
                EnsembleTemplatePosition(
                    organization=club, template=template, instrument="Tuba", required=1
                ),
                EnsembleTemplatePosition(
                    organization=club, template=template, instrument="tuba", required=3
                ),
            ]
        )
        Instrument.objects.filter(organization=club).delete()
    migration.bestand(apps, None)
    with tenant_context(club.pk):
        skills = list(Skill.objects.filter(musician=musician).order_by("instrument"))
        assert [(s.instrument, s.primary) for s in skills] == [
            ("Saxofon", True),
            ("Trompete", False),
        ]
        rows = list(template.positions.all())
        assert [(r.instrument, r.required) for r in rows] == [("Tuba", 3)]
    assert {"Trompete", "Saxofon", "Tuba", "Klarinette"} <= set(names(club))
