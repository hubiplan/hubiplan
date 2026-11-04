import datetime
import json

import pytest
from django.db import DatabaseError, transaction

from core.tenancy import rls_bypass, tenant_context
from todos.models import Todo, TodoProgress

from .factories import give_role, make_user
from .test_rls import as_app_role
from .test_todo_attachments import add, endpoint
from .test_todo_series import complete, start
from .test_todos import create, patch, url

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def private_root(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def sender(orgs):
    user = make_user("aufgaben-dachverband@example.org")
    give_role(user, orgs["federation"])
    return user


def distribute(api, sender, org, todo, targets, *, per_unit=True):
    response = patch(
        api,
        sender,
        org,
        todo,
        shares=[
            {
                "user": user.pk,
                "target_org": target.pk,
                "level": "edit",
                "responsible": True,
            }
            for user, target in targets
        ],
        per_unit=per_unit,
    )
    assert response.status_code == 200, response.content
    return response.json()


def listed(api, user, org):
    response = api(user).get(url(org))
    assert response.status_code == 200, response.content
    return response.json()["items"]


def test_gemeinsame_aufgabe_aus_zielkontext_mit_rls_und_ruecknahme(
    api, sender, board_a, board_b, orgs
):
    source, target = orgs["federation"], orgs["a"]
    with as_app_role():
        todo = create(api, sender, source)
        todo = distribute(api, sender, source, todo, [(board_a, target)], per_unit=False)
        received = listed(api, board_a, target)
        assert [row["id"] for row in received] == [todo["id"]]
        assert listed(api, board_b, orgs["b"]) == []
        assert api(board_a).get(url(source, todo["id"])).status_code == 403
        response = patch(api, board_a, target, received[0], status="done")
        assert response.status_code == 200, response.content
        assert response["X-Change-Task"] == str(todo["id"])
        undo_url = url(target, todo["id"]) + f"changes/{response['X-Change-Set']}/undo/"
        assert api(board_a).post(undo_url).status_code == 200
        assert listed(api, sender, source)[0]["status"] == "open"
        current = listed(api, sender, source)[0]
        assert patch(api, sender, source, current, shares=[]).status_code == 200
        assert api(board_a).get(url(target, todo["id"])).status_code == 404
        assert api(board_a).post(undo_url).status_code == 404


def test_graph_begrenzt_zieleinheiten_auch_in_der_datenbank(api, sender, board_a, board_c, orgs):
    from todos.models import TodoShare

    source = orgs["federation"]
    todo = create(api, sender, source)
    bad = {"user": board_c.pk, "target_org": orgs["c"].pk, "level": "edit"}
    assert patch(api, sender, source, todo, shares=[bad]).status_code == 400
    with as_app_role(), tenant_context(source.pk, sender.pk):
        with pytest.raises(DatabaseError), transaction.atomic():
            TodoShare.objects.create(
                organization=source,
                todo_id=todo["id"],
                user=board_c,
                target_org=orgs["c"],
                level="edit",
            )
    from organizations.models import Organization
    from todos.access import Scope
    from todos.targets import allowed_scopes

    platform = Organization.objects.get(type="platform")
    assert (orgs["c"].pk, None) in allowed_scopes(Scope(platform, None, set()))
    assert (source.pk, None) in allowed_scopes(Scope(orgs["a"], None, set()))
    assert (orgs["b"].pk, None) not in allowed_scopes(Scope(orgs["a"], None, set()))


def test_kopien_trennen_lokale_notizen_dateien_und_zentrale_aenderungen(
    api, sender, board_a, board_b, orgs
):
    source = orgs["federation"]
    with as_app_role():
        todo = create(api, sender, source, due_date="2032-01-31")
        added = add(api, sender, source, todo)
        assert added.status_code == 201, added.content
        source_attachment = added.json()["attachment"]["id"]
        todo = listed(api, sender, source)[0]
        todo = distribute(api, sender, source, todo, [(board_a, orgs["a"]), (board_b, orgs["b"])])
        a = listed(api, board_a, orgs["a"])[0]
        b = listed(api, board_b, orgs["b"])[0]
        assert a["id"] != b["id"] != todo["id"]
        assert a["central_readonly"] and a["can_complete"]
        assert patch(api, board_a, orgs["a"], a, title="Eigener Titel").status_code == 403
        a = patch(api, board_a, orgs["a"], a, local_note="Nur der Verein liest dies").json()
        assert a["local_note"] == "Nur der Verein liest dies"
        local_upload = add(api, board_a, orgs["a"], a)
        assert local_upload.status_code == 201, local_upload.content
        local_id = local_upload.json()["attachment"]["id"]
        response = api(board_a).get(endpoint(orgs["a"], a) + f"{source_attachment}/")
        assert response.status_code == 200
        assert b"erfundener Anhang" in b"".join(response.streaming_content)
        assert api(sender).get(url(source, a["id"])).status_code == 404
        assert api(sender).get(endpoint(source, a) + f"{local_id}/").status_code == 404
        b = patch(api, board_b, orgs["b"], b, status="done").json()
        changed = patch(api, sender, source, todo, title="Neue zentrale Überschrift")
        assert changed.status_code == 200, changed.content
        a = listed(api, board_a, orgs["a"])[0]
        b = listed(api, board_b, orgs["b"])[0]
        assert (
            a["title"] == "Neue zentrale Überschrift"
            and a["local_note"] == "Nur der Verein liest dies"
        )
        assert b["title"] == todo["title"]
        progress = api(sender).get(url(source, todo["id"]) + "progress/")
        assert progress.status_code == 200
        rows = progress.json()["items"]
        assert {row["status"] for row in rows} == {"open", "done"}
        assert "Nur der Verein" not in json.dumps(rows)
        assert not any(
            set(row) & {"copy_id", "title", "description", "local_note", "attachments"}
            for row in rows
        )


def test_zielserien_laufen_unabhaengig_und_quellloeschung_erhaelt_lokale_historie(
    api, sender, board_a, board_b, orgs
):
    source = orgs["federation"]
    with as_app_role():
        todo = start(api, sender, source)
        todo = distribute(api, sender, source, todo, [(board_a, orgs["a"]), (board_b, orgs["b"])])
        a = listed(api, board_a, orgs["a"])[0]
        complete(api, board_a, orgs["a"], a)
        assert len(listed(api, board_a, orgs["a"])) == 2
        assert len(listed(api, board_b, orgs["b"])) == 1
        rows = api(sender).get(url(source, todo["id"]) + "progress/").json()["items"]
        assert sorted(row["sequence_no"] for row in rows) == [1, 1, 2]
        assert len(listed(api, sender, source)) == 1
    with rls_bypass():
        Todo.objects.get(pk=todo["id"]).delete()
    with as_app_role():
        rows = listed(api, board_a, orgs["a"])
        assert len(rows) == 2
        assert all(not row["series"]["active"] for row in rows)
        assert not TodoProgress.objects.filter(source_id=todo["id"]).exists()


def test_rls_verbietet_umwaengung_und_fremde_fortschrittsabfragen(
    api, sender, board_a, board_b, orgs
):
    source = orgs["federation"]
    todo = distribute(api, sender, source, create(api, sender, source), [(board_a, orgs["a"])])
    with as_app_role():
        a = listed(api, board_a, orgs["a"])[0]
        assert api(board_a).get(url(orgs["a"], todo["id"]) + "progress/").status_code == 404
        assert api(board_b).get(url(orgs["b"], a["id"])).status_code == 404
        with tenant_context(orgs["a"].pk, board_a.pk):
            assert TodoProgress.objects.count() == 0
            with pytest.raises(DatabaseError), transaction.atomic():
                Todo.objects.filter(pk=a["id"]).update(organization=orgs["b"])
            with pytest.raises(DatabaseError), transaction.atomic():
                Todo.objects.filter(pk=a["id"]).update(due_date=datetime.date(2033, 1, 1))


def test_private_serienvorlage_wird_durch_einzelfreigabe_nicht_exportiert(api, board_a, orgs):
    from datatransfer.dump import Packer
    from datatransfer.tables import dump_tables
    from todos.exports import for_actor
    from todos.models import TodoSeries

    reader = make_user("einzelausgabe@example.org")
    give_role(reader, orgs["a"], permissions=["todos.view"], name="Einzelausgabe")
    first = start(api, board_a, orgs["a"])
    with rls_bypass():
        from core.encfields import update_encrypted

        update_encrypted(
            TodoSeries.objects.filter(pk=first["series"]["id"]),
            title="Vertrauliche Zukunftsvorlage",
        )
    first = patch(
        api,
        board_a,
        orgs["a"],
        first,
        title="Freigegebene Einzelausgabe",
        shares=[{"user": reader.pk}],
        following=False,
    ).json()
    with as_app_role(), tenant_context(orgs["a"].pk, reader.pk):
        assert TodoSeries.objects.filter(pk=first["series"]["id"]).count() == 0
    with tenant_context(orgs["a"].pk), rls_bypass(), for_actor(reader):
        tables = dump_tables(orgs["a"], Packer(False))
    assert tables["todos.todoseries"][0]["title"] == "Freigegebene Einzelausgabe"
    assert "Vertrauliche Zukunftsvorlage" not in json.dumps(tables)


def test_private_loeschung_nach_rollenverlust_funktioniert_mit_rls(api, board_a, orgs):
    from access.models import RoleAssignment

    first = start(api, board_a, orgs["a"])
    RoleAssignment.objects.filter(user=board_a).delete()
    with as_app_role():
        assert api(board_a).get("/api/me/todos/export/").status_code == 200
        assert api(board_a).delete(f"/api/me/todos/{first['id']}/").status_code == 204
