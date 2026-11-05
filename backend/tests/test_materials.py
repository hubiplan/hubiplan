import datetime
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from materials.models import MaterialItem, MaterialPhoto

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def material_setup(orgs, api, settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"
    org = orgs["a"]
    org.enabled_modules = sorted(set(org.enabled_modules) | {"material", "events"})
    org.save()
    user = make_user("material@example.org")
    give_role(
        user,
        org,
        permissions=[
            "material.edit",
            "members.view",
            "events.edit",
            "docs.edit",
            "todos.edit",
            "export.full",
        ],
    )
    return org, user, api(user), f"/api/orgs/{org.pk}/materials/"


def payload(**kwargs):
    return {
        "title": "Beamer",
        "description": "Schwarzer Beamer mit Koffer",
        "purpose": "Präsentationen",
        "location_kind": "address",
        "address": {
            "street": "Musterweg 1",
            "postal_code": "12345",
            "city": "Musterstadt",
            "country": "Deutschland",
        },
        **kwargs,
    }


def create(client, base, **kwargs):
    response = client.post(base, payload(**kwargs), content_type=JSON)
    assert response.status_code == 201, response.content
    return response.json()


def test_crud_conflicts_trash_undo(material_setup):
    org, user, client, base = material_setup
    item = create(client, base)
    url = f"{base}{item['id']}/"
    assert item["inventory_number"].startswith("MAT-")
    assert client.patch(url, {"version": 0, "title": "Neu"}, content_type=JSON).status_code == 409
    response = client.patch(url, {"version": item["version"], "title": "Neu"}, content_type=JSON)
    assert response.status_code == 200, response.content
    item = response.json()
    history = client.get(url + "history/").json()
    response = client.post(
        url + "history/",
        {"version": item["version"], "revision": history[0]["id"]},
        content_type=JSON,
    )
    assert response.status_code == 200, response.content
    item = response.json()
    assert item["title"] == "Beamer"
    assert client.delete(url, {"version": item["version"]}, content_type=JSON).status_code == 204
    assert client.get(url).status_code == 404
    trash = client.get(base + "?trash=1").json()["items"][0]
    assert (
        client.post(url + "restore/", {"version": trash["version"]}, content_type=JSON).status_code
        == 200
    )


def test_module_roles_and_foreign_objects(material_setup, orgs, api):
    org, user, client, base = material_setup
    item = create(client, base)
    other = make_user("leser@example.org")
    give_role(other, org, permissions=["material.view"], name="Lesen")
    reader = api(other)
    assert reader.get(base).status_code == 200
    assert reader.post(base, payload(), content_type=JSON).status_code == 403
    assert client.get(f"/api/orgs/{orgs['b'].pk}/materials/{item['id']}/").status_code in (403, 404)
    org.enabled_modules.remove("material")
    org.save()
    assert client.get(base).status_code == 404


def test_required_fields_and_exclusive_location(material_setup):
    org, user, client, base = material_setup
    assert client.post(base, payload(purpose=""), content_type=JSON).status_code == 400
    assert client.post(base, payload(address={}), content_type=JSON).status_code == 400
    assert (
        client.post(
            base, payload(location_kind="member", member=999999), content_type=JSON
        ).status_code
        == 400
    )
    item = create(client, base, member=999999)
    assert item["member"] is None


def event(org, **kwargs):
    from events.models import Event

    starts = timezone.now().replace(microsecond=0) + datetime.timedelta(days=1)
    return Event.objects.create(
        organization=org,
        title="Versammlung",
        starts_at=starts,
        ends_at=starts + datetime.timedelta(hours=2),
        **kwargs,
    )


def link(client, base, item, **kwargs):
    response = client.post(
        f"{base}{item['id']}/links/",
        {"version": item["version"], **kwargs},
        content_type=JSON,
    )
    assert response.status_code == 200, response.content
    return response.json()


def test_series_exception_move_cancel_and_rule_change(material_setup):
    from events.models import EventException

    org, user, client, base = material_setup
    series = event(org, repeat="weekly")
    item = create(client, base)
    item = link(client, base, item, type="event", event=series.pk, kind="series")
    assert item["uses"]
    item = link(
        client,
        base,
        item,
        type="event",
        event=series.pk,
        kind="exclude",
        original_start=series.starts_at.isoformat(),
    )
    assert not any(
        u["original_start"] == series.starts_at.isoformat().replace("+00:00", "Z")
        for u in item["uses"]
    )
    excluded = next(r for r in item["events"] if r["kind"] == "exclude")
    item = link(client, base, item, type="event", id=excluded["id"], remove=True)
    moved = series.starts_at + datetime.timedelta(days=2)
    EventException.objects.create(
        organization=org,
        event=series,
        original_start=series.starts_at,
        starts_at=moved,
        ends_at=moved + datetime.timedelta(hours=2),
    )
    item = client.get(f"{base}{item['id']}/").json()
    assert item["uses"][0]["starts_at"] == moved.isoformat().replace("+00:00", "Z")
    series.is_cancelled = True
    series.save()
    assert client.get(f"{base}{item['id']}/").json()["uses"] == []
    series.is_cancelled = False
    series.repeat_interval = 2
    series.save()
    changed = client.get(f"{base}{item['id']}/").json()
    assert changed["events"][0]["needs_review"]
    assert changed["uses"] == []


def test_private_todo_and_document_permissions(material_setup, api):
    from documents.models import Document, Folder
    from todos.models import Todo

    org, user, client, base = material_setup
    task = Todo.objects.create(organization=org, owner=user, created_by=user, title="Privat")
    folder = Folder.objects.create(
        organization=org, name="Anleitungen", public_key=Folder.new_key()
    )
    doc = Document.objects.create(organization=org, folder=folder, title="Bedienungsanleitung")
    item = create(client, base)
    item = link(client, base, item, type="todo", id=task.pk)
    item = link(client, base, item, type="document", id=doc.pk)
    other = make_user("inventarleser@example.org")
    give_role(
        other,
        org,
        permissions=["material.edit", "todos.view"],
        name="Material ohne Ziele",
    )
    reader = api(other)
    hidden = reader.get(f"{base}{item['id']}/").json()
    assert hidden["todos"] == []
    assert hidden["documents"] == []
    assert reader.get(base + f"?todo={task.pk}").status_code == 404
    assert reader.get(base + f"?document={doc.pk}").status_code == 404
    assert (
        reader.post(
            f"{base}{item['id']}/links/",
            {"version": item["version"], "type": "todo", "id": task.pk},
            content_type=JSON,
        ).status_code
        == 403
    )
    task.status = "done"
    task.save()
    fresh = client.get(f"{base}{item['id']}/").json()
    assert fresh["todos"][0]["status"] == "done"
    assert fresh["address"] == item["address"]


def test_common_tasks_require_current_source_confirmation(material_setup, monkeypatch):
    from core.tenancy import rls_bypass
    from materials.models import MaterialTodoLink
    from todos import remote
    from todos.models import Todo

    org, user, client, base = material_setup
    item = create(client, base)
    with rls_bypass():
        task = Todo.objects.create(
            organization=org,
            owner=user,
            created_by=user,
            title="Alter Titel",
            remote_mode="common",
        )
    MaterialTodoLink.objects.create(organization=org, item_id=item["id"], todo=task)
    calls = []

    def unavailable(rows):
        calls.append([row.pk for row in rows])
        return []

    monkeypatch.setattr(remote, "fresh_rows", unavailable)
    assert client.get(base).status_code == 200
    assert calls == []  # Eine normale Materialliste braucht keine fremde Aufgabenquelle.
    assert client.get(f"{base}{item['id']}/").json()["todos"] == []
    assert calls == [[task.pk]]
    assert client.get(f"{base}?todo={task.pk}").status_code == 404

    def confirmed(rows):
        for row in rows:
            row.title = "Aktuell bestätigter Titel"
            row.save(update_fields=["title"])
            yield row

    monkeypatch.setattr(remote, "fresh_rows", confirmed)
    assert client.get(f"{base}{item['id']}/").json()["todos"] == [
        {"id": task.pk, "title": "Aktuell bestätigter Titel", "status": "open"}
    ]


def test_photo_sanitized_private_replace_and_undo(material_setup, api, monkeypatch):
    from core import virenscan
    from documents.services import total_bytes

    monkeypatch.setattr(virenscan, "scan_bytes", lambda *a, **kw: None)
    org, user, client, base = material_setup
    item = create(client, base)
    stream = io.BytesIO()
    metadata = Image.Exif()
    metadata[315] = "Privater Bildautor"
    Image.new("RGB", (2000, 1000), "red").save(stream, "PNG", exif=metadata)
    url = f"{base}{item['id']}/photo/"
    response = client.post(
        url,
        {
            "version": item["version"],
            "file": SimpleUploadedFile("foto.png", stream.getvalue(), content_type="image/png"),
        },
    )
    assert response.status_code == 200, response.content
    item = response.json()
    result = client.get(item["photo_url"])
    assert result.status_code == 200
    image = Image.open(io.BytesIO(b"".join(result.streaming_content)))
    assert image.format == "JPEG" and image.width == 1600
    assert not image.getexif()
    assert result["Cache-Control"] == "private, no-store"
    assert api(make_user("ohne-recht@example.org")).get(url).status_code in (403, 404)
    invalid = client.post(
        url,
        {
            "version": item["version"],
            "file": SimpleUploadedFile("falsch.jpg", b"kein Bild"),
        },
    )
    assert invalid.status_code == 400
    assert MaterialPhoto.objects.count() == 1
    old_photo = MaterialPhoto.objects.get()
    replaced = client.post(
        url,
        {
            "version": item["version"],
            "file": SimpleUploadedFile("neu.png", stream.getvalue()),
        },
    )
    assert replaced.status_code == 200, replaced.content
    item = replaced.json()
    old_photo.refresh_from_db()
    assert old_photo.deleted_at is not None
    assert MaterialPhoto.objects.filter(deleted_at__isnull=True).count() == 1
    assert total_bytes(org) == sum(photo.size for photo in MaterialPhoto.objects.all())
    removed = client.delete(url, {"version": item["version"]}, content_type=JSON)
    assert removed.status_code == 200
    assert removed.json()["photo_url"] is None
    revision = client.get(f"{base}{item['id']}/history/").json()[0]
    undo = client.post(
        f"{base}{item['id']}/history/",
        {"version": removed.json()["version"], "revision": revision["id"]},
        content_type=JSON,
    )
    assert undo.status_code == 200 and undo.json()["photo_url"]
    assert MaterialPhoto.objects.count() == 2


def test_create_task_with_material_is_atomic(material_setup):
    from todos.models import Todo

    org, user, client, base = material_setup
    item = create(client, base)
    response = client.post(
        f"/api/orgs/{org.pk}/todos/",
        {"title": "Beamer abholen", "material": item["id"]},
        content_type=JSON,
    )
    assert response.status_code == 201, response.content
    assert client.get(f"{base}{item['id']}/").json()["todos"][0]["id"] == response.json()["id"]
    response = client.post(
        f"/api/orgs/{org.pk}/todos/",
        {"title": "Nicht anlegen", "material": 999999},
        content_type=JSON,
    )
    assert response.status_code == 404
    assert all(todo.title != "Nicht anlegen" for todo in Todo.objects.all())


def test_export_respects_material_permission(material_setup, api):
    from datatransfer.tables import dump_rows
    from organizations.models import Organization
    from todos.exports import for_actor

    org, user, client, base = material_setup
    create(client, base)
    assert client.get(base + "?export=1").status_code == 200
    other = make_user("export-ohne-material@example.org")
    give_role(other, org, permissions=["export.full", "settings.view"], name="Nur Export")
    with for_actor(other):
        assert dump_rows(MaterialItem, org, None) == []
    with for_actor(user):
        assert len(dump_rows(MaterialItem, org, None)) == 1
        assert dump_rows(MaterialItem, Organization.platform(), None) == []


def test_member_location_and_purge(material_setup):
    from .factories import make_member

    org, user, client, base = material_setup
    member = make_member(org, "Erika", "Beispiel")
    item = create(client, base, location_kind="member", member=member.pk)
    assert item["address"] == {} and "Erika" in item["member_name"]
    member.purged_at = timezone.now()
    member.save()
    item = client.get(f"{base}{item['id']}/").json()
    assert item["location_review"] and item["member"] is None
    assert item["location_kind"] == "unknown"


def test_department_isolation(material_setup, api):
    from organizations.models import Department

    from .test_m12_events import dept_role, member_with_access

    org, user, client, base = material_setup
    org.department_access_enabled = True
    org.member_portal_enabled = True
    org.save()
    department = Department.objects.create(
        organization=org, name="Materialgruppe", self_managed=True
    )
    member, dept_user, _ = member_with_access(org, "Mara", [department])
    dept_role(department, member, ["material.edit"])
    dept_client = api(dept_user)
    dept_base = f"/api/depts/{department.pk}/materials/"
    dept_item = create(dept_client, dept_base)
    assert client.get(f"{base}{dept_item['id']}/").status_code == 404
    org_item = create(client, base)
    assert dept_client.get(f"{dept_base}{org_item['id']}/").status_code == 404


def test_deleted_events_preserve_items(material_setup):
    org, user, client, base = material_setup
    first, second = event(org), event(org)
    item = create(
        client,
        base,
        purpose="",
        events=[
            {"event": first.pk, "kind": "event"},
            {"event": second.pk, "kind": "event"},
        ],
    )
    first.delete()
    second.delete()
    item = client.get(f"{base}{item['id']}/").json()
    assert item["usage_review"]
    assert item["events"] == []


def test_database_scope_and_cross_org_guard(material_setup, orgs):
    from django.db import IntegrityError, transaction

    from core.tenancy import set_rls
    from materials.models import MaterialEventLink

    from .test_rls import as_app_role

    org, user, client, base = material_setup
    data = create(client, base)
    with as_app_role():
        set_rls(orgs["b"].pk, user.pk)
        assert not MaterialItem.objects.filter(pk=data["id"]).exists()
        set_rls(org.pk, user.pk)
        assert MaterialItem.objects.filter(pk=data["id"]).exists()
        set_rls(org.pk, user.pk, todo_department_id=999999)
        assert not MaterialItem.objects.filter(pk=data["id"]).exists()
    set_rls(org.pk, user.pk)
    foreign = event(orgs["b"])
    with pytest.raises(IntegrityError), transaction.atomic():
        MaterialEventLink.objects.create(
            organization=org, item_id=data["id"], event=foreign, kind="event"
        )


def test_import_keeps_missing_member_as_review(material_setup):
    from datatransfer.tables import IdMap, load_tables

    org, user, client, base = material_setup
    rows = {
        "materials.materialitem": [
            {"id": 123, **payload(location_kind="member", member=456, address={})}
        ]
    }
    assert load_tables(rows, org, IdMap(), None, user=user) == 1
    item = MaterialItem.objects.get()
    assert item.location_kind == "unknown" and item.member_id is None


def test_uses_and_links_report_all_day(material_setup):
    org, user, client, base = material_setup
    fest = event(org, all_day=True)
    item = create(client, base)
    item = link(client, base, item, type="event", event=fest.pk, kind="event")
    assert item["uses"][0]["all_day"] is True
    assert item["events"][0]["all_day"] is True
