"""Inventory identity, scopes, custody changes, return location and maintenance."""
# ruff: noqa: F811

import datetime
import uuid
from types import SimpleNamespace

import pytest
from django.db import connection
from django.utils import timezone

from core.tenancy import tenant_context
from materials.models import MaterialItem
from music.models import Equipment, EquipmentLoan, EquipmentMaintenance, Musician

from .factories import give_role, make_member, make_user
from .test_materials import create
from .test_music import JSON, c, club, music  # noqa: F401
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db


@pytest.fixture
def equipment(c, club, music):
    club.enabled_modules.append("material")
    club.save()
    base = f"/api/orgs/{club.pk}/materials/"
    item = create(c, base, title="Vereinstuba")
    with tenant_context(club.pk):
        musician = Musician.objects.create(organization=club, name="Muster Gast")
    return SimpleNamespace(
        org=club,
        item=item,
        musician=musician,
        url=f"{music[0]}/equipment/",
        material_url=f"{base}{item['id']}/",
    )


def post(c, e, action, key=None, **values):
    with tenant_context(e.org.pk):
        version = MaterialItem.objects.get(pk=e.item["id"]).version
    payload = {"action": action, "item": e.item["id"], "version": version, **values}
    return c.post(e.url, payload, content_type=JSON, HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))


def register(c, e):
    result = post(c, e, "register", kind="instrument", instrument="Tuba", size="B")
    assert result.status_code == 200, result.content
    return result.json()["id"]


def issue(c, e, **values):
    return post(
        c,
        e,
        "issue",
        musician=e.musician.pk,
        due_date=(timezone.localdate() + datetime.timedelta(days=7)).isoformat(),
        **values,
    )


def test_inventory_guest_custody_return_maintenance_and_history(c, equipment):
    e = equipment
    identifier = register(c, e)
    assert issue(c, e).status_code == 200
    assert issue(c, e).status_code == 400
    with tenant_context(e.org.pk):
        item = MaterialItem.objects.get(pk=e.item["id"])
        assert item.location_kind == "unknown" and item.member_id is None and item.address == {}
        loan = EquipmentLoan.objects.get(equipment_id=identifier)
        assert loan.issue_condition == "ready"
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT location_before FROM music_equipmentloan WHERE id = %s", [loan.pk]
            )
            raw = cursor.fetchone()[0]
            assert "enc1" in str(raw) and "Musterweg" not in str(raw)
    material = c.get(e.material_url).json()
    assert material["music_equipment"]["loaned"] is True
    assert (
        c.delete(e.material_url, {"version": material["version"]}, content_type=JSON).status_code
        == 400
    )
    history = c.get(e.material_url + "history/").json()
    assert history[0]["can_undo"] is False
    assert (
        c.post(
            e.material_url + "history/",
            {"version": material["version"], "revision": history[0]["id"]},
            content_type=JSON,
        ).status_code
        == 400
    )
    result = post(
        c,
        e,
        "return",
        loan=loan.pk,
        restore_location=True,
        condition="defective",
        condition_note="Ventil prüfen",
        note="Rückgabe bestätigt",
    )
    assert result.status_code == 200, result.content
    with tenant_context(e.org.pk):
        item.refresh_from_db()
        loan.refresh_from_db()
        assert item.location_kind == "address" and item.address["street"] == "Musterweg 1"
        assert (
            item.condition == "defective"
            and loan.returned_at
            and loan.return_note == "Rückgabe bestätigt"
        )
    assert issue(c, e).status_code == 400
    assert (
        post(
            c,
            e,
            "maintenance",
            date=timezone.localdate().isoformat(),
            next_due="2027-12-01",
            condition="ready",
            note="Ventil repariert",
        ).status_code
        == 200
    )
    assert issue(c, e).status_code == 200
    with tenant_context(e.org.pk):
        assert EquipmentMaintenance.objects.get(equipment_id=identifier).note == "Ventil repariert"
        assert Equipment.objects.get(pk=identifier).maintenance_due == datetime.date(2027, 12, 1)


def test_member_custody_uses_inventory_member_rights(c, api, equipment):
    e = equipment
    member = make_member(e.org, "Muster", "Musiker")
    with tenant_context(e.org.pk):
        e.musician.membership = member
        e.musician.save()
    register(c, e)
    user = make_user("musikinventar@example.org")
    give_role(
        user,
        e.org,
        permissions=["music.edit", "material.edit"],
        name="Musikinventar ohne Mitglieder",
    )
    assert issue(api(user), e).status_code == 400
    assert issue(c, e).status_code == 200
    with tenant_context(e.org.pk):
        assert MaterialItem.objects.get(pk=e.item["id"]).member_id == member.pk


def test_retries_and_versions(c, equipment):
    e = equipment
    register(c, e)
    version = c.get(e.material_url).json()["version"]
    key = str(uuid.uuid4())
    assert issue(c, e, key=key, version=version).status_code == 200
    assert issue(c, e, key=key, version=version).status_code == 200
    assert post(c, e, "profile", version=version, kind="uniform").status_code == 409
    with tenant_context(e.org.pk):
        assert EquipmentLoan.objects.filter(equipment__item_id=e.item["id"]).count() == 1


def test_permission_module_tenant_and_deleted_scopes(c, api, equipment, orgs):
    e = equipment
    identifier = register(c, e)
    for permissions in [["music.view"], ["material.view"]]:
        user = make_user(f"leser{len(permissions[0])}@example.org")
        give_role(user, e.org, permissions=permissions, name=permissions[0])
        assert api(user).get(e.url).status_code == 403
    reader = make_user("inventarleser@example.org")
    give_role(
        reader, e.org, permissions=["music.view", "material.view"], name="Musikinventar lesen"
    )
    assert api(reader).get(e.url).status_code == 200
    assert issue(api(reader), e).status_code == 403
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert not Equipment.objects.filter(pk=identifier).exists()
    material_only = make_user("materialleser@example.org")
    give_role(material_only, e.org, permissions=["material.view"], name="Nur Material")
    assert "music_equipment" not in api(material_only).get(e.material_url).json()
    with tenant_context(e.org.pk):
        MaterialItem.objects.filter(pk=e.item["id"]).update(deleted_at=timezone.now())
    assert c.get(e.url).json()["items"] == []
    assert issue(c, e).status_code == 404
    e.org.enabled_modules.remove("material")
    e.org.save()
    assert c.get(e.url).status_code == 404


def test_return_to_new_address_and_future_maintenance_rejected(c, equipment):
    e = equipment
    register(c, e)
    assert issue(c, e).status_code == 200
    loan = c.get(e.url).json()["items"][0]["active_loan"]
    assert (
        post(
            c, e, "return", loan=loan, restore_location=False, address={}, condition="ready"
        ).status_code
        == 400
    )
    address = {
        "street": "Neuer Musterweg 2",
        "postal_code": "12345",
        "city": "Musterstadt",
        "country": "DE",
    }
    assert (
        post(
            c, e, "return", loan=loan, restore_location=False, address=address, condition="ready"
        ).status_code
        == 200
    )
    assert c.get(e.material_url).json()["address"] == address
    assert (
        post(
            c,
            e,
            "maintenance",
            date=(timezone.localdate() + datetime.timedelta(days=1)).isoformat(),
            condition="ready",
        ).status_code
        == 400
    )
