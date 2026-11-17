"""Schreibversuche an Aufgaben unter dem Zeilenschutz (Gesamtaudit 15.11., AZ-04).

``lock_task`` sperrt mit ``SELECT ... FOR UPDATE``. PostgreSQL wendet dabei zusätzlich die
Schreibregel an. Wer eine Aufgabe nur lesen darf, fand deshalb im Betrieb keine Zeile und
bekam 404 statt 403. Sichtbar, aber nicht beschreibbar ist jetzt 403; Aufgaben, die gar nicht
sichtbar sind, und Dokumente ohne Ablagerecht bleiben 404. Die Anfragen laufen wie im Betrieb
unter der Rolle der Anwendung. Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest

from todos.models import Todo, TodoAttachment

from .test_documents import base as docs_base
from .test_documents import folder, upload
from .test_todo_attachments import add, endpoint, private_root  # noqa: F401
from .test_todo_sharing import reader, share  # noqa: F401
from .test_todos import create, url
from .test_todos import patch as change

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anfragen_unter_app_rolle")]


def test_lesefreigabe_sichtbar_aber_nicht_beschreibbar_ist_403(api, board_a, orgs, reader):
    org = orgs["a"]
    todo = share(api, board_a, org, create(api, board_a, org), reader)
    assert api(reader).get(url(org, todo["id"])).status_code == 200
    assert change(api, reader, org, todo, status="done").status_code == 403
    assert change(api, reader, org, todo, deleted=True).status_code == 403
    assert add(api, reader, org, todo).status_code == 403
    stored = Todo.objects.get(pk=todo["id"])
    assert stored.status != "done" and stored.deleted_at is None
    assert not TodoAttachment.objects.exists()


def test_fremde_verantwortung_loeschen_ist_403(api, board_a, orgs, reader):
    org = orgs["a"]
    todo = share(api, board_a, org, create(api, board_a, org), reader, "edit")
    moved = change(api, board_a, org, todo, owner=reader.pk)
    assert moved.status_code == 200, moved.content
    # Der Vorstand hat die Aufgabe angelegt und sieht sie, verantwortet sie aber nicht mehr.
    assert api(board_a).get(url(org, todo["id"])).status_code == 200
    assert change(api, board_a, org, moved.json(), deleted=True).status_code == 403
    assert Todo.objects.get(pk=todo["id"]).deleted_at is None


def test_unsichtbare_aufgabe_bleibt_404(api, board_a, orgs, reader):
    org = orgs["a"]
    private = create(api, board_a, org)
    assert api(reader).get(url(org, private["id"])).status_code == 404
    assert change(api, reader, org, private, status="done").status_code == 404
    assert change(api, reader, org, private, deleted=True).status_code == 404
    assert add(api, reader, org, private).status_code == 404
    assert Todo.objects.get(pk=private["id"]).status != "done"
    assert not TodoAttachment.objects.exists()


def test_dokument_ohne_ablagerecht_bleibt_404(api, board_a, orgs, reader):
    org = orgs["a"]
    client = api(board_a)
    doc = upload(
        client, docs_base(org), folder(client, docs_base(org))["id"], title="Erfundenes Protokoll"
    )
    todo = share(api, board_a, org, create(api, board_a, org), reader, "edit")
    response = api(reader).post(
        endpoint(org, todo),
        {"version": todo["version"], "document": doc["id"]},
        content_type="application/json",
    )
    assert response.status_code == 404
    assert b"Erfundenes Protokoll" not in response.content
    assert not TodoAttachment.objects.exists()
