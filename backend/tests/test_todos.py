"""Aufgaben: Privatheit auf allen Wegen und konfliktgeschützte Zustandswechsel."""

import datetime

import pytest
from django.db import connection

from access.models import RoleAssignment
from audit.models import AuditEntry
from changes.models import ChangeSet
from core.tenancy import tenant_context
from todos.models import Todo

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db


def url(org, pk=None):
    return f"/api/orgs/{org.pk}/todos/" + (f"{pk}/" if pk else "")


def create(api, user, org, **values):
    response = api(user).post(
        url(org), {"title": "Sitzung vorbereiten", **values}, content_type="application/json"
    )
    assert response.status_code == 201, response.content
    return response.json()


def patch(api, user, org, todo, **values):
    return api(user).patch(
        url(org, todo["id"]),
        {"version": todo["version"], **values},
        content_type="application/json",
    )


def test_privates_crud_und_papierkorb(api, board_a, orgs):
    org = orgs["a"]
    todo = create(api, board_a, org, due_date="2026-12-01")
    assert len(api(board_a).get(url(org)).json()["items"]) == 1
    response = patch(api, board_a, org, todo, status="done")
    assert response.status_code == 200
    done = response.json()
    assert done["done_by"] == board_a.pk
    reopened = patch(api, board_a, org, done, status="open").json()
    assert reopened["done_at"] is None
    deleted = patch(api, board_a, org, reopened, deleted=True).json()
    assert api(board_a).get(url(org)).json()["items"] == []
    assert len(api(board_a).get(url(org) + "?trash=1").json()["items"]) == 1
    assert patch(api, board_a, org, deleted, deleted=False).status_code == 200


def test_fremder_vorstand_sieht_keine_privaten_aufgaben(api, board_a, orgs):
    org = orgs["a"]
    other = make_user("andere@example.org")
    give_role(other, org, name="Andere Verwaltung")
    todo = create(api, board_a, org)
    assert api(other).get(url(org)).json()["items"] == []
    assert api(other).get(url(org, todo["id"])).status_code == 404
    assert patch(api, other, org, todo, title="Fremd").status_code == 404
    assert not AuditEntry.objects.filter(organization=org).exists()


def test_fremde_einheit_erhaelt_keine_aufgabe(api, board_a, board_b, orgs):
    todo = create(api, board_a, orgs["a"])
    assert api(board_b).get(url(orgs["b"], todo["id"])).status_code == 404


def test_lesen_erlaubt_eigene_aufgaben(api, orgs):
    user = make_user("leserin@example.org")
    give_role(user, orgs["a"], permissions=["todos.view"], name="Lesen")
    todo = create(api, user, orgs["a"])
    assert patch(api, user, orgs["a"], todo, title="Geändert").status_code == 200


def test_rollenvorgaben_respektieren_ausdrueckliche_auswahl(api, board_a, orgs):
    roles = f"/api/orgs/{orgs['a'].pk}/roles/"
    reader = api(board_a).post(
        roles, {"name": "Neue Leserrolle", "is_board": False}, content_type="application/json"
    )
    assert reader.status_code == 201
    assert "todos.view" in reader.json()["permissions"]
    board = api(board_a).post(
        roles, {"name": "Neuer Vorstand", "is_board": True}, content_type="application/json"
    )
    assert "todos.edit" in board.json()["permissions"]
    office = api(board_a).post(
        roles,
        {"name": "Reines Amt", "permissions": [], "is_board": False},
        content_type="application/json",
    )
    assert office.json()["permissions"] == []


def test_veraltete_version_ueberschreibt_nichts(api, board_a, orgs):
    todo = create(api, board_a, orgs["a"])
    assert patch(api, board_a, orgs["a"], todo, title="Aktuell").status_code == 200
    assert patch(api, board_a, orgs["a"], todo, title="Veraltet").status_code == 409
    assert api(board_a).get(url(orgs["a"], todo["id"])).json()["title"] == "Aktuell"


@pytest.mark.parametrize(
    "values", [{"title": ""}, {"due_time": "12:00"}, {"timezone": "Unbekannt/Ort"}]
)
def test_ungueltige_angaben(api, board_a, orgs, values):
    response = api(board_a).post(
        url(orgs["a"]), {"title": "Titel", **values}, content_type="application/json"
    )
    assert response.status_code == 400


def test_verschluesselte_inhalte(api, board_a, orgs):
    todo = create(api, board_a, orgs["a"], description="Vertrauliche Notiz")
    with connection.cursor() as cursor:
        cursor.execute("SELECT title, description FROM todos_todo WHERE id = %s", [todo["id"]])
        row = cursor.fetchone()
    assert all(value.startswith("enc1:") for value in row)


def test_rueckgaengig_nur_fuer_eigene_aktuell_berechtigte_aufgabe(api, board_a, orgs):
    org = orgs["a"]
    todo = create(api, board_a, org)
    response = patch(api, board_a, org, todo, title="Neu")
    set_id = response.headers["X-Change-Set"]
    other = make_user("protokoll@example.org")
    give_role(other, org, name="Protokoll")
    undo_url = f"/api/orgs/{org.pk}/changes/{set_id}/undo/"
    assert api(other).post(undo_url).status_code == 403
    assert api(board_a).post(undo_url).status_code == 200
    assert api(board_a).get(url(org, todo["id"])).json()["title"] == todo["title"]
    assert not AuditEntry.objects.filter(organization=org).exists()


def test_rollenverlust_sperrt_auch_rueckgaengig(api, board_a, orgs):
    org = orgs["a"]
    todo = create(api, board_a, org)
    response = patch(api, board_a, org, todo, title="Neu")
    set_id = response.headers["X-Change-Set"]
    with tenant_context(org.pk, board_a.pk):
        RoleAssignment.objects.filter(user=board_a, organization=org).delete()
    assert api(board_a).post(f"/api/orgs/{org.pk}/changes/{set_id}/undo/").status_code in {403, 404}


def test_persoenlicher_export(api, board_a, board_b, orgs):
    create(api, board_a, orgs["a"], description="Meine Notiz")
    assert (
        api(board_a).get("/api/me/todos/export/").json()["tasks"][0]["description"] == "Meine Notiz"
    )
    assert api(board_b).get("/api/me/todos/export/").json()["tasks"] == []


def test_kachel_und_kontoloeschung(api, board_a, orgs):
    org = orgs["a"]
    todo = create(api, board_a, org)
    assert api(board_a).get(f"/api/orgs/{org.pk}/open-tasks/").json()["items"][0]["kind"] == "todo"
    board_a.delete()
    with tenant_context(org.pk):
        assert not Todo.objects.filter(pk=todo["id"]).exists()
        assert not ChangeSet.objects.filter(records__model="todos.todo").exists()


def test_papierkorb_wird_nach_30_tagen_bereinigt(api, board_a, orgs):
    from django.utils import timezone

    from todos.tasks import purge_deleted

    todo = create(api, board_a, orgs["a"])
    with tenant_context(orgs["a"].pk, board_a.pk):
        Todo.objects.filter(pk=todo["id"]).update(
            deleted_at=timezone.now() - datetime.timedelta(days=31)
        )
    assert purge_deleted() == 1


def test_anlegen_rueckgaengig_und_wiederherstellen(api, board_a, orgs):
    org = orgs["a"]
    response = api(board_a).post(url(org), {"title": "Probe"}, content_type="application/json")
    undo_url = f"/api/orgs/{org.pk}/changes/{response.headers['X-Change-Set']}/undo/"
    undone = api(board_a).post(undo_url)
    assert undone.status_code == 200
    assert api(board_a).get(url(org)).json()["items"] == []
    redo_url = f"/api/orgs/{org.pk}/changes/{undone.headers['X-Change-Set']}/undo/"
    assert api(board_a).post(redo_url).status_code == 200
    assert api(board_a).get(url(org)).json()["items"][0]["title"] == "Probe"


def test_rueckgaengig_setzt_versionsnummer_nicht_zurueck(api, board_a, orgs):
    org = orgs["a"]
    todo = create(api, board_a, org)
    changed = patch(api, board_a, org, todo, title="Neu")
    set_id = changed.headers["X-Change-Set"]
    assert api(board_a).post(f"/api/orgs/{org.pk}/changes/{set_id}/undo/").status_code == 200
    assert patch(api, board_a, org, todo, title="Veraltet").status_code == 409


@pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL-RLS")
def test_rls_sperrt_fremde_private_aufgaben_auch_innerhalb_der_einheit(api, board_a, orgs):
    from core.tenancy import set_rls

    from .test_rls import as_app_role

    org = orgs["a"]
    todo = create(api, board_a, org)
    other = make_user("zweiter-vorstand@example.org")
    give_role(other, org, name="Zweiter Vorstand")
    with as_app_role():
        set_rls(org.pk, other.pk)
        assert not Todo.objects.filter(pk=todo["id"]).exists()
        assert Todo.objects.filter(pk=todo["id"]).update(status="done") == 0
        set_rls(org.pk, board_a.pk)
        assert Todo.objects.filter(pk=todo["id"]).exists()
