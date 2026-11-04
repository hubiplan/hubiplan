"""Zwei getrennte Instanzidentitäten, echte Signaturen und RLS auf dem Empfangsweg."""

import datetime

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, transaction

from core.tenancy import rls_bypass, tenant_context
from peering import services
from todos.access import scope_for
from todos.models import Todo, TodoRemoteShare, TodoRemoteTask

from .factories import give_role, make_user
from .test_rls import as_app_role
from .test_todos import create, url
from .test_verbund_kopplung import JSON, VERBAND, VEREIN, api, couple
from .test_verbund_kopplung import _setup as _setup
from .test_verbund_kopplung import net as net
from .test_verbund_kopplung import world as world
from .verbund_netz import release

pytestmark = pytest.mark.django_db


@pytest.fixture
def linked(net, world):
    lower, upper = couple(net, world)
    with net.on(VERBAND):
        release(upper, {"unit": "on", "todos": "on"})
    lower.refresh_from_db()
    upper.refresh_from_db()
    return lower, upper


def distribute(net, world, linked, mode="copy", **extra):
    with net.on(VERBAND):
        task = create(api, world["fed_board"], world["fed"], title="Material vorbereiten")
        response = api(world["fed_board"]).put(
            url(world["fed"], task["id"]) + "remote/",
            {
                "version": task["version"],
                "coupling": linked[1].pk,
                "mode": mode,
                **extra,
            },
            content_type=JSON,
        )
        assert response.status_code == 200, response.content
    with net.on(VEREIN):
        inbox = api(world["club_board"]).get(url(world["club"]) + "remote/")
        assert inbox.status_code == 200, inbox.content
        item = next(x for x in inbox.json()["items"] if x["title"] == task["title"])
        response = api(world["club_board"]).post(
            url(world["club"]) + f"remote/{item['id']}/adopt/", {}, content_type=JSON
        )
        assert response.status_code == 201, response.content
        return task, response.json()


def change(net, world, todo, **values):
    with net.on(VEREIN):
        return api(world["club_board"]).patch(
            url(world["club"], todo["id"]),
            {"version": todo["version"], **values},
            content_type=JSON,
        )


def test_nur_ausdrueckliche_freigabe_und_lokale_kopie(net, world, linked):
    with net.on(VERBAND):
        private = create(api, world["fed_board"], world["fed"], title="Privater Entwurf")
        services.sync(linked[1])
    source, target = distribute(net, world, linked)
    assert target["remote_mode"] == "copy" and target["distributed"]
    assert target["title"] == source["title"] and not target["shared"]
    assert not TodoRemoteTask.objects.filter(uid=str(private["id"])).exists()
    assert change(net, world, target, title="Unerlaubt").status_code == 403
    result = change(net, world, target, local_note="Nur vor Ort")
    assert result.status_code == 200, result.content
    result = change(net, world, result.json(), status="done")
    assert result.status_code == 200, result.content
    with rls_bypass():
        assert Todo.objects.get(pk=source["id"]).status == "open"
        progress = TodoRemoteShare.objects.get(todo_id=source["id"]).progress
        assert progress[0]["status"] == "done"
        assert "Nur vor Ort" not in str(progress)
        assert set(progress[0]) == {
            "sequence_no",
            "due_date",
            "status",
            "done_at",
            "ended",
            "deleted",
        }


def test_gemeinsam_bestaetigt_quelle_und_erkennt_versionskonflikt(net, world, linked):
    source, target = distribute(net, world, linked, "common")
    result = change(net, world, target, status="done")
    assert result.status_code == 200, result.content
    assert result.json()["status"] == "done"
    with rls_bypass():
        assert Todo.objects.get(pk=source["id"]).status == "done"
    assert change(net, world, target, status="open").status_code == 409
    assert change(net, world, result.json(), status="open").status_code == 200


def test_gemeinsamer_stand_wird_frisch_geprueft_und_offline_nicht_vorgetaeuscht(net, world, linked):
    source, target = distribute(net, world, linked, "common")
    with net.on(VERBAND):
        current = api(world["fed_board"]).get(url(world["fed"], source["id"])).json()
        response = api(world["fed_board"]).patch(
            url(world["fed"], source["id"]),
            {"version": current["version"], "title": "Aktualisierte Quelle"},
            content_type=JSON,
        )
        assert response.status_code == 200
    assert change(net, world, target, status="done").status_code == 409
    with net.on(VEREIN):
        current = api(world["club_board"]).get(url(world["club"], target["id"])).json()
        assert current["title"] == "Aktualisierte Quelle"
    net.down.add(VERBAND)
    with net.on(VEREIN):
        assert api(world["club_board"]).get(url(world["club"], target["id"])).status_code == 503
        assert api(world["club_board"]).get(url(world["club"])).json()["items"] == []
    assert change(net, world, current, status="done").status_code == 503
    with rls_bypass():
        assert Todo.objects.get(pk=source["id"]).status == "open"


@pytest.mark.parametrize("mode", ["copy", "common"])
def test_widerruf_erhaelt_eigene_kopie_und_entzieht_gemeinsamen_zugriff(net, world, linked, mode):
    source, target = distribute(net, world, linked, mode)
    with net.on(VERBAND):
        current = api(world["fed_board"]).get(url(world["fed"], source["id"])).json()
        result = api(world["fed_board"]).put(
            url(world["fed"], source["id"]) + "remote/",
            {
                "version": current["version"],
                "coupling": linked[1].pk,
                "mode": mode,
                "active": False,
            },
            content_type=JSON,
        )
        assert result.status_code == 200, result.content
    with net.on(VEREIN):
        result = api(world["club_board"]).get(url(world["club"], target["id"]))
        assert result.status_code == (200 if mode == "copy" else 404)


def test_lesefreigabe_ist_keine_erledigungsfreigabe(net, world, linked):
    _, target = distribute(net, world, linked, "common", can_complete=False)
    assert not target["can_complete"]
    assert change(net, world, target, status="done").status_code == 403


def test_uebernahme_bleibt_privater_lokaler_aufgaben_acl_unterstellt(net, world, linked):
    _, target = distribute(net, world, linked)
    other = make_user("anderer-vorstand@example.org")
    give_role(other, world["club"])
    with net.on(VEREIN), as_app_role():
        assert api(other).get(url(world["club"], target["id"])).status_code == 404
        assert api(other).get(url(world["club"]) + "remote/").json()["items"] == []
    with tenant_context(world["club"].pk, world["club_board"].pk), as_app_role():
        scope_for(world["club_board"], world["club"].pk)
        with pytest.raises(DatabaseError), transaction.atomic():
            Todo.objects.filter(pk=target["id"]).update(remote_mode="common")


def test_gemeinsamer_status_hat_auch_datenbankschutz(net, world, linked):
    _, target = distribute(net, world, linked, "common")
    with tenant_context(world["club"].pk, world["club_board"].pk), as_app_role():
        scope_for(world["club_board"], world["club"].pk)
        with pytest.raises(DatabaseError), transaction.atomic():
            Todo.objects.filter(pk=target["id"]).update(status="done")


def test_quellanhaenge_werden_autorisiert_und_nicht_lokale_ergaenzungen(net, world, linked):
    source, target = distribute(net, world, linked)
    content = b"%PDF-1.4 erfundene Aufgabenunterlage"
    with net.on(VERBAND):
        current = api(world["fed_board"]).get(url(world["fed"], source["id"])).json()
        result = api(world["fed_board"]).post(
            url(world["fed"], source["id"]) + "attachments/",
            {
                "version": current["version"],
                "file": SimpleUploadedFile("hinweise.pdf", content, "application/pdf"),
            },
        )
        assert result.status_code == 201, result.content
        services.sync(linked[1])
    with net.on(VEREIN):
        rows = (
            api(world["club_board"])
            .get(url(world["club"], target["id"]) + "attachments/")
            .json()["items"]
        )
        remote = next(x for x in rows if x.get("remote"))
        response = api(world["club_board"]).get(
            url(world["club"], target["id"]) + f"remote-files/{remote['id']}/"
        )
        assert response.status_code == 200, getattr(response, "content", "stream")
        assert b"".join(response.streaming_content) == content
        assert response["Cache-Control"] == "private, no-store"


def test_eigene_serien_fahren_nur_nach_ausdruecklicher_freigabe_fort(net, world, linked):
    with net.on(VERBAND):
        task = create(api, world["fed_board"], world["fed"], due_date="2030-01-01")
        result = api(world["fed_board"]).patch(
            url(world["fed"], task["id"]) + "series/",
            {"version": task["version"], "repeat": "monthly", "count": 3},
            content_type=JSON,
        )
        assert result.status_code == 200, result.content
        task = api(world["fed_board"]).get(url(world["fed"], task["id"])).json()
        result = api(world["fed_board"]).put(
            url(world["fed"], task["id"]) + "remote/",
            {
                "version": task["version"],
                "coupling": linked[1].pk,
                "mode": "copy",
                "following": True,
            },
            content_type=JSON,
        )
        assert result.status_code == 200, result.content
    with net.on(VEREIN):
        mapping = TodoRemoteTask.objects.get()
        result = api(world["club_board"]).post(
            url(world["club"]) + f"remote/{mapping.pk}/adopt/", {}, content_type=JSON
        )
        assert result.status_code == 201, result.content
        target = result.json()
    assert target["series"]["repeat"] == "monthly"
    result = change(net, world, target, status="done")
    assert result.status_code == 200, result.content
    with rls_bypass():
        successor = Todo.objects.get(series_id=target["series"]["id"], status="open")
        assert successor.due_date == datetime.date(2030, 2, 1)
        assert successor.remote_mode == "copy"
        assert Todo.objects.get(pk=task["id"]).status == "open"
