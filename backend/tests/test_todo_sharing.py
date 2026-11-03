import datetime
from unittest.mock import patch

import pytest
from django.db import connection
from django.utils import timezone

from access.models import RoleAssignment
from core.tenancy import tenant_context
from todos.models import TodoPreference
from todos.notify import notify_shared

from .factories import give_role, make_user
from .test_todos import create, url
from .test_todos import patch as change

pytestmark = pytest.mark.django_db


@pytest.fixture
def reader(orgs):
    user = make_user("aufgaben-lesen@example.org")
    give_role(user, orgs["a"], permissions=["todos.view"], name="Aufgaben lesen")
    return user


def share(api, owner, org, todo, reader, level="view"):
    response = change(
        api, owner, org, todo, shares=[{"user": reader.pk, "level": level, "responsible": True}]
    )
    assert response.status_code == 200, response.content
    return response.json()


def test_personenfreigabe_lesen_bearbeiten_und_entzug(api, board_a, orgs, reader):
    org = orgs["a"]
    todo = create(api, board_a, org)
    shared = share(api, board_a, org, todo, reader)
    assert api(reader).get(url(org, todo["id"])).status_code == 200
    assert change(api, reader, org, shared, status="done").status_code == 403
    shared = share(api, board_a, org, shared, reader, "edit")
    done = change(api, reader, org, shared, status="done").json()
    assert done["status"] == "done"
    assert change(api, reader, org, done, deleted=True).status_code == 403
    assert change(api, reader, org, done, shares=[]).status_code == 403
    assert change(api, board_a, org, done, shares=[]).status_code == 200
    assert api(reader).get(url(org, todo["id"])).status_code == 404


def test_leserecht_erlaubt_keine_freigabe(api, reader, board_a, orgs):
    todo = create(api, reader, orgs["a"])
    assert (
        change(
            api, reader, orgs["a"], todo, shares=[{"user": board_a.pk, "level": "edit"}]
        ).status_code
        == 403
    )
    assert not api(reader).get(url(orgs["a"], todo["id"])).json()["shared"]


def test_rollenfreigabe_folgt_aktiven_rolleninhabern(api, board_a, orgs, reader):
    org = orgs["a"]
    assignment = RoleAssignment.objects.get(user=reader, organization=org)
    todo = create(api, board_a, org)
    response = change(
        api, board_a, org, todo, shares=[{"role": assignment.role_id, "level": "edit"}]
    )
    assert response.status_code == 200
    assert api(reader).get(url(org, todo["id"])).status_code == 200
    successor = make_user("nachfolge@example.org")
    RoleAssignment.objects.create(organization=org, role=assignment.role, user=successor)
    assignment.valid_until = timezone.localdate() - datetime.timedelta(days=1)
    assignment.save()
    assert api(reader).get(url(org, todo["id"])).status_code == 403
    assert api(successor).get(url(org, todo["id"])).status_code == 200


def test_freigabe_nur_an_gueltige_empfaenger(api, board_a, board_b, orgs):
    todo = create(api, board_a, orgs["a"])
    assert change(api, board_a, orgs["a"], todo, shares=[{"user": board_b.pk}]).status_code == 400
    assert (
        change(api, board_a, orgs["a"], todo, shares=[{"user": board_a.pk, "role": 1}]).status_code
        == 400
    )
    assert (
        change(
            api, board_a, orgs["a"], todo, shares=[{"user": board_a.pk}, {"user": board_a.pk}]
        ).status_code
        == 400
    )


def test_verantwortung_nur_an_beteiligten_bearbeiter(api, board_a, orgs, reader):
    org = orgs["a"]
    todo = share(api, board_a, org, create(api, board_a, org), reader)
    assert change(api, board_a, org, todo, owner=reader.pk).status_code == 400
    todo = share(api, board_a, org, todo, reader, "edit")
    moved = change(api, board_a, org, todo, owner=reader.pk)
    assert moved.status_code == 200
    assert moved.json()["owner"] == reader.pk
    assert change(api, board_a, org, moved.json(), deleted=True).status_code == 403
    assert change(api, reader, org, moved.json(), deleted=True).status_code == 200


def test_versand_nur_einmal_und_nach_heutiger_freigabe(api, board_a, orgs, reader):
    org = orgs["a"]
    todo = share(api, board_a, org, create(api, board_a, org), reader)
    with patch("todos.notify.mail.send") as mail, patch("todos.notify.send_to_user") as push:
        notify_shared(todo["id"], reader.pk, todo["version"])
        notify_shared(todo["id"], reader.pk, todo["version"])
        assert mail.call_count == push.call_count == 1
        change(api, board_a, org, todo, shares=[])
        notify_shared(todo["id"], reader.pk, todo["version"] + 1)
        assert mail.call_count == 1


def test_kanaleinstellungen_und_push_ohne_titel(api, board_a, orgs, reader):
    org = orgs["a"]
    todo = share(api, board_a, org, create(api, board_a, org), reader)
    TodoPreference.objects.create(user=reader, share_mail=False, push_title=False)
    with patch("todos.notify.mail.send") as mail, patch("todos.notify.send_to_user") as push:
        notify_shared(todo["id"], reader.pk, todo["version"])
        assert not mail.called
        assert push.call_args.args[1]["title"] == "Neue Aufgabe"


@pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL-RLS")
def test_freigabe_funktioniert_unter_rls(api, board_a, orgs, reader):
    from .test_rls import as_app_role

    org = orgs["a"]
    with as_app_role():
        todo = create(api, board_a, org)
        todo = share(api, board_a, org, todo, reader, "edit")
        assert api(reader).get(url(org, todo["id"])).status_code == 200
        assert change(api, reader, org, todo, status="done").status_code == 200


def test_export_enthaelt_nur_berechtigte_geteilte_aufgaben(api, board_a, orgs, reader):
    from datatransfer.tables import dump_rows
    from todos.exports import for_actor
    from todos.models import Todo

    org = orgs["a"]
    private = create(api, board_a, org)
    todo = share(api, board_a, org, create(api, board_a, org), reader)
    with tenant_context(org.pk), for_actor(reader):
        rows = dump_rows(Todo, org, None)
    assert [r["id"] for r in rows] == [todo["id"]]
    assert private["id"] not in [r["id"] for r in rows]


def test_nachfolge_eroeffnet_keinen_zugriff_auf_private_aufgaben(api, board_a, orgs, reader):
    org = orgs["a"]
    original = make_user("ersteller@example.org")
    give_role(original, org, name="Ersteller")
    private = create(api, original, org)
    shared = share(api, original, org, create(api, original, org), reader, "edit")
    with tenant_context(org.pk, original.pk):
        RoleAssignment.objects.filter(user=original, organization=org).delete()
    assert api(board_a).get(url(org, shared["id"])).status_code == 404
    orphans = api(board_a).get(url(org) + "orphans/")
    assert orphans.status_code == 200
    assert orphans.json()["items"] == [{"id": shared["id"]}]
    response = api(board_a).post(
        url(org, shared["id"]) + "take-over/", {}, content_type="application/json"
    )
    assert response.status_code == 200
    assert api(board_a).get(url(org, shared["id"])).json()["owner"] == board_a.pk
    assert api(board_a).get(url(org, private["id"])).status_code == 404


def test_persoenlicher_export_enthaelt_aktuelle_geteilte_aufgaben(api, board_a, orgs, reader):
    todo = share(api, board_a, orgs["a"], create(api, board_a, orgs["a"]), reader)
    assert api(reader).get("/api/me/todos/export/").json()["tasks"][0]["id"] == todo["id"]


def test_postausgang_speichert_keine_aufgabeninhalte(orgs):
    from django.core.mail import EmailMessage

    from outbox.backend import OutboxBackend
    from outbox.models import OutgoingMail

    message = EmailMessage(
        "Vertraulicher Titel",
        "Vertrauliche Beschreibung",
        to=["test@example.org"],
        headers={"X-Hubiplan-Org": str(orgs["a"].pk), "X-Hubiplan-Kind": "aufgabe"},
    )
    assert OutboxBackend().send_messages([message]) == 1
    mail = OutgoingMail.objects.get(kind="aufgabe")
    assert "Vertraulich" not in mail.subject
    assert "Vertraulich" not in mail.body


@pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL-RLS")
def test_rollenvorschau_zeigt_nur_rollenfreigaben_auch_unter_rls(api, board_a, orgs, reader):
    from .test_rls import as_app_role

    org = orgs["a"]
    maker = make_user("aufgaben-erstellen@example.org")
    give_role(maker, org, name="Erstellen")
    assignment = RoleAssignment.objects.get(user=reader, organization=org)
    todo = create(api, maker, org)
    change(api, maker, org, todo, shares=[{"role": assignment.role_id}])
    create(api, board_a, org)
    client = api(board_a)
    with as_app_role():
        response = client.post(
            f"/api/orgs/{org.pk}/ansicht/",
            {"role": assignment.role_id},
            content_type="application/json",
        )
        assert response.status_code == 200
        listed = client.get(url(org)).json()["items"]
        assert [item["id"] for item in listed] == [todo["id"]]
        assert not listed[0]["can_edit"]
