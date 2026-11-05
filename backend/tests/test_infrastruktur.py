"""Infrastruktur (Schießstand, Schützenhaus, Vereinsheim) im Bestand neben dem Material."""

import pytest

from materials.models import MaterialItem

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"

ADDRESS = {
    "street": "Musterweg 1",
    "postal_code": "12345",
    "city": "Musterstadt",
    "country": "Deutschland",
}


@pytest.fixture
def setup(orgs, api, settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"
    org = orgs["a"]
    org.enabled_modules = sorted(set(org.enabled_modules) | {"material", "infrastructure"})
    org.save()
    user = make_user("infra@example.org")
    give_role(
        user,
        org,
        permissions=["material.edit", "infrastructure.edit", "members.view", "export.full"],
    )
    base = f"/api/orgs/{org.pk}"
    return org, user, api(user), f"{base}/facilities/", f"{base}/materials/"


def facility(client, url, **kwargs):
    data = {
        "title": "Schützenhaus",
        "description": "Vereinsheim mit Saal",
        "location_kind": "address",
        "address": ADDRESS,
        "facility_type": "building",
        **kwargs,
    }
    response = client.post(url, data, content_type=JSON)
    assert response.status_code == 201, response.content
    return response.json()


def test_infrastruktur_mit_bereichen_und_material(setup):
    org, user, client, facilities, materials = setup
    house = facility(client, facilities, capacity=120, access_note="Schlüsselkasten")
    assert house["inventory_number"].startswith("INF-")
    assert house["kind"] == "facility"
    stand = facility(
        client,
        facilities,
        title="Luftgewehrstand",
        description="10 Bahnen",
        location_kind="facility",
        facility=house["id"],
        address={},
        facility_type="range",
        lanes=[{"facility": "lg10", "count": 10}],
    )
    assert stand["facility_title"] == "Schützenhaus"
    # Ein Bereich kann keine weiteren Bereiche haben
    response = client.post(
        facilities,
        {
            "title": "Bahn 1",
            "description": "x",
            "location_kind": "facility",
            "facility": stand["id"],
            "facility_type": "room",
        },
        content_type=JSON,
    )
    assert response.status_code == 400
    # Material im Schützenhaus gelagert, Schlüssel gehört dazu
    beamer = client.post(
        materials,
        {
            "title": "Beamer",
            "description": "im Koffer",
            "purpose": "Versammlungen",
            "location_kind": "facility",
            "facility": house["id"],
            "location_note": "Keller",
        },
        content_type=JSON,
    )
    assert beamer.status_code == 201, beamer.content
    key = client.post(
        materials,
        {
            "title": "Schlüssel Haupteingang",
            "description": "rot",
            "purpose": "Zugang",
            "location_kind": "address",
            "address": ADDRESS,
            "belongs_to": house["id"],
        },
        content_type=JSON,
    )
    assert key.status_code == 201, key.content
    detail = client.get(f"{facilities}{house['id']}/").json()
    assert [r["title"] for r in detail["areas"]] == ["Luftgewehrstand"]
    assert [r["title"] for r in detail["contents"]] == ["Beamer"]
    assert [r["title"] for r in detail["accessories"]] == ["Schlüssel Haupteingang"]
    # Listen trennen Material und Infrastruktur
    assert {r["title"] for r in client.get(facilities).json()["items"]} == {
        "Schützenhaus",
        "Luftgewehrstand",
    }
    assert [r["title"] for r in client.get(materials).json()["items"]] == [
        "Beamer",
        "Schlüssel Haupteingang",
    ]
    assert client.get(f"{materials}{house['id']}/").status_code == 404
    # Material-Angaben gelten nicht für Infrastruktur und umgekehrt
    response = client.patch(
        f"{materials}{beamer.json()['id']}/",
        {"version": beamer.json()["version"], "capacity": 3},
        content_type=JSON,
    )
    assert response.status_code == 400


def test_eigene_rechte_und_modul(setup, api):
    org, user, client, facilities, materials = setup
    reader = make_user("nur-material@example.org")
    give_role(reader, org, permissions=["material.view"], name="Materialwart")
    assert api(reader).get(facilities).status_code == 403
    org.enabled_modules = [m for m in org.enabled_modules if m != "infrastructure"]
    org.save()
    assert client.get(facilities).status_code == 404
    # Ohne Modul gibt es keine Infrastruktur als Standort
    response = client.post(
        materials,
        {
            "title": "Zelt",
            "description": "x",
            "purpose": "Fest",
            "location_kind": "facility",
            "facility": 1,
        },
        content_type=JSON,
    )
    assert response.status_code == 400


def test_schiessinfrastruktur_aus_der_infrastruktur(setup):
    org, user, client, facilities, materials = setup
    org.enabled_modules = sorted(set(org.enabled_modules) | {"competitions"})
    org.shooting_facilities = "infrastructure"
    org.save()
    facility(
        client,
        facilities,
        title="KK-Stand",
        facility_type="range",
        lanes=[{"facility": "kk50", "count": 6}],
    )
    from competitions.targets import available_facilities

    org.refresh_from_db()
    assert available_facilities(org) == ["kk50"]
    response = client.post(
        facilities,
        {
            "title": "Falsch",
            "description": "x",
            "location_kind": "address",
            "address": ADDRESS,
            "facility_type": "range",
            "lanes": [{"facility": "gibt-es-nicht", "count": 1}],
        },
        content_type=JSON,
    )
    assert response.status_code == 400


def test_bereich_nur_in_derselben_einheit(setup, orgs):
    org, user, client, facilities, materials = setup
    house = facility(client, facilities)
    other = MaterialItem.objects.create(
        organization=orgs["b"],
        kind="facility",
        title="Fremd",
        description="x",
        location_kind="address",
        address=ADDRESS,
        facility_type="building",
    )
    response = client.post(
        materials,
        {
            "title": "Zelt",
            "description": "x",
            "purpose": "Fest",
            "location_kind": "facility",
            "facility": other.pk,
        },
        content_type=JSON,
    )
    assert response.status_code == 400
    assert house["id"] != other.pk
