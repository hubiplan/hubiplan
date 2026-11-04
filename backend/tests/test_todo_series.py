import datetime
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch as mock_patch

import pytest
from django.db import IntegrityError, close_old_connections, transaction

from core.tenancy import rls_bypass, tenant_context
from todos.models import Todo, TodoPreference, TodoSeries
from todos.series import calendar_date, next_date

from .test_todos import create, patch, url

pytestmark = pytest.mark.django_db
UTC = datetime.UTC


def start(api, owner, org, *, day="2032-01-31", **rule):
    todo = create(api, owner, org, due_date=day)
    response = api(owner).patch(
        url(org, todo["id"]) + "series/",
        {
            "version": todo["version"],
            "repeat": "monthly",
            **rule,
        },
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    return api(owner).get(url(org, todo["id"])).json()


def complete(api, owner, org, todo, day="2032-01-31"):
    at = datetime.datetime.fromisoformat(day).replace(hour=12, tzinfo=UTC)
    with mock_patch("todos.views.timezone.now", return_value=at):
        response = patch(api, owner, org, todo, status="done")
    assert response.status_code == 200, response.content
    return response


def tasks(org):
    with tenant_context(org.pk), rls_bypass():
        return list(
            Todo.objects.filter(
                organization=org, withdrawn=False, deleted_at__isnull=True
            ).order_by("sequence_no")
        )


def test_monatsende_und_schaltjahranker_bleiben_erhalten():
    anchor = datetime.date(2032, 1, 31)
    assert calendar_date(anchor, "monthly", 1, 1) == datetime.date(2032, 2, 29)
    assert calendar_date(anchor, "monthly", 1, 2) == datetime.date(2032, 3, 31)
    anchor = datetime.date(2032, 2, 29)
    assert calendar_date(anchor, "yearly", 1, 1) == datetime.date(2033, 2, 28)
    assert calendar_date(anchor, "yearly", 1, 4) == datetime.date(2036, 2, 29)


def test_spaetes_erledigen_ueberspringt_termine_ohne_zaehlerverbrauch(api, board_a, orgs):
    org = orgs["a"]
    first = start(api, board_a, org, count=2)
    complete(api, board_a, org, first, "2032-05-15")
    rows = tasks(org)
    assert len(rows) == 2
    assert rows[1].due_date == datetime.date(2032, 5, 31)
    assert rows[1].sequence_no == 2
    current = api(board_a).get(url(org, rows[1].pk)).json()
    complete(api, board_a, org, current, "2032-05-31")
    assert len(tasks(org)) == 2


def test_ab_erledigung_und_inklusives_enddatum():
    series = TodoSeries(
        anchor_date=datetime.date(2032, 1, 31),
        repeat="monthly",
        interval=1,
        basis="done",
        due_time=datetime.time(15),
        timezone="Europe/Berlin",
        ends_on=datetime.date(2032, 3, 15),
    )
    todo = Todo(due_date=datetime.date(2032, 1, 31))
    now = datetime.datetime(2032, 2, 15, 12, tzinfo=UTC)
    assert next_date(series, todo, now) == datetime.date(2032, 3, 15)
    series.ends_on = datetime.date(2032, 3, 14)
    assert next_date(series, todo, now) is None


def test_wiedereroeffnen_nimmt_nur_unberuehrte_folge_zurueck(api, board_a, orgs):
    org = orgs["a"]
    first = start(api, board_a, org)
    done = complete(api, board_a, org, first).json()
    successor_id = tasks(org)[1].pk
    reopened = patch(api, board_a, org, done, status="open")
    assert reopened.status_code == 200, reopened.content
    assert len(tasks(org)) == 1
    with rls_bypass():
        assert Todo.objects.get(pk=successor_id).withdrawn
    complete(api, board_a, org, reopened.json())
    rows = tasks(org)
    assert rows[1].pk != successor_id
    assert rows[1].sequence_no == 2
    successor = api(board_a).get(url(org, rows[1].pk)).json()
    assert patch(api, board_a, org, successor, description="Bearbeitet").status_code == 200
    current = api(board_a).get(url(org, first["id"])).json()
    assert patch(api, board_a, org, current, status="open").status_code == 400


def test_rueckgaengig_atomisch_und_force_umgeht_keine_serienregeln(api, board_a, orgs):
    org = orgs["a"]
    first = start(api, board_a, org)
    done = complete(api, board_a, org, first)
    undo_url = f"/api/orgs/{org.pk}/changes/{done.headers['X-Change-Set']}/undo/"
    undone = api(board_a).post(undo_url)
    assert undone.status_code == 200, undone.content
    assert len(tasks(org)) == 1 and tasks(org)[0].status == "open"
    current = api(board_a).get(url(org, first["id"])).json()
    done = complete(api, board_a, org, current)
    successor = api(board_a).get(url(org, tasks(org)[1].pk)).json()
    patch(api, board_a, org, successor, title="Schon bearbeitet")
    undo_url = f"/api/orgs/{org.pk}/changes/{done.headers['X-Change-Set']}/undo/"
    assert api(board_a).post(
        undo_url, {"force": True}, content_type="application/json"
    ).status_code in {400, 403, 409}
    assert len(tasks(org)) == 2 and tasks(org)[0].status == "done"


def test_nur_diese_oder_alle_folgenden_und_beenden(api, board_a, orgs):
    org = orgs["a"]
    first = start(api, board_a, org)
    changed = patch(api, board_a, org, first, title="Nur heute", following=False).json()
    complete(api, board_a, org, changed)
    second = api(board_a).get(url(org, tasks(org)[1].pk)).json()
    assert second["title"] == first["title"]
    second = patch(api, board_a, org, second, title="Neue Vorlage", following=True).json()
    complete(api, board_a, org, second, "2032-02-29")
    third = api(board_a).get(url(org, tasks(org)[2].pk)).json()
    assert third["title"] == "Neue Vorlage"
    response = api(board_a).patch(
        url(org, third["id"]) + "series/",
        {"version": third["version"], "active": False},
        content_type="application/json",
    )
    assert response.status_code == 200
    third = api(board_a).get(url(org, third["id"])).json()
    complete(api, board_a, org, third, "2032-03-31")
    assert len(tasks(org)) == 3
    current = api(board_a).get(url(org, third["id"])).json()
    reopened = patch(api, board_a, org, current, status="open")
    assert reopened.status_code == 200 and not reopened.json()["series"]["active"]


def test_ganze_serie_papierkorb_und_historie_von_aufbewahrung_ausgenommen(api, board_a, orgs):
    from todos.cleanup import completed

    org = orgs["a"]
    first = start(api, board_a, org)
    done = complete(api, board_a, org, first).json()
    with rls_bypass():
        TodoPreference.objects.update_or_create(user=board_a, defaults={"purge_done": True})
    assert completed(datetime.datetime(2035, 1, 1, tzinfo=UTC)) == 0
    response = api(board_a).patch(
        url(org, done["id"]) + "series/",
        {"version": done["version"], "deleted": True},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    assert tasks(org) == []
    trash = api(board_a).get(url(org) + "?trash=1").json()["items"]
    assert len(trash) == 2
    response = api(board_a).patch(
        url(org, trash[0]["id"]) + "series/",
        {"version": trash[0]["version"], "deleted": False},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    assert len(tasks(org)) == 2


def test_datenbank_verhindert_zweite_offene_ausgabe(api, board_a, orgs):
    first = start(api, board_a, orgs["a"])
    with rls_bypass(), pytest.raises(IntegrityError), transaction.atomic():
        Todo.objects.bulk_create(
            [
                Todo(
                    organization=orgs["a"],
                    created_by=board_a,
                    owner=board_a,
                    title="Doppelt",
                    due_date=datetime.date(2032, 2, 29),
                    series_id=first["series"]["id"],
                    sequence_no=2,
                )
            ]
        )


@pytest.mark.django_db(transaction=True)
def test_paralleles_erledigen_erzeugt_genau_eine_folge(api, board_a, orgs):
    first = start(api, board_a, orgs["a"])

    def finish():
        try:
            return patch(api, board_a, orgs["a"], first, status="done").status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: finish(), range(2))) == [200, 409]
    assert len(tasks(orgs["a"])) == 2


def test_erinnerungseinstellungen_werden_vererbt_und_geaenderte_folge_blockiert_ruecknahme(
    api, board_a, orgs
):
    from todos.models import TodoReminderConfig

    org = orgs["a"]
    first = start(api, board_a, org)
    response = api(board_a).patch(
        url(org, first["id"]) + "reminders/",
        {"days": [0, 7], "mail": False},
        content_type="application/json",
    )
    assert response.status_code == 200
    done = complete(api, board_a, org, first).json()
    successor = tasks(org)[1]
    config = TodoReminderConfig.objects.get(todo=successor, user=board_a)
    assert config.days == [0, 7] and config.mail is False and not config.customized
    api(board_a).patch(
        url(org, successor.pk) + "reminders/", {"enabled": False}, content_type="application/json"
    )
    assert patch(api, board_a, org, done, status="open").status_code == 400


def test_beteiligter_bearbeiter_kann_unter_rls_folge_erzeugen(api, board_a, orgs):
    from .factories import give_role, make_user
    from .test_rls import as_app_role

    org = orgs["a"]
    reader = make_user("serie-bearbeiten@example.org")
    give_role(reader, org, permissions=["todos.view"], name="Serienbearbeitung")
    first = start(api, board_a, org)
    first = patch(
        api, board_a, org, first, shares=[{"user": reader.pk, "level": "edit"}], following=True
    ).json()
    with as_app_role():
        complete(api, reader, org, first)
        response = api(reader).get(url(org))
        assert response.status_code == 200
        assert len(response.json()["items"]) == 2


def test_dokumentverweise_werden_vererbt_dateien_nicht(api, board_a, orgs):
    from .test_documents import base, folder, upload
    from .test_todo_attachments import add, endpoint

    org = orgs["a"]
    first = start(api, board_a, org)
    response = add(api, board_a, org, first)
    assert response.status_code == 201
    f = folder(api(board_a), base(org))
    doc = upload(api(board_a), base(org), f["id"])
    response = api(board_a).post(
        endpoint(org, first),
        {"version": response.json()["version"], "document": doc["id"], "following": True},
        content_type="application/json",
    )
    assert response.status_code == 201
    first = api(board_a).get(url(org, first["id"])).json()
    complete(api, board_a, org, first)
    attachments = tasks(org)[1].attachments.all()
    assert attachments.count() == 1
    assert attachments.get().kind == "document" and attachments.get().document_id == doc["id"]


def test_serienverantwortung_wird_als_ganzes_uebertragen_aber_nicht_private_historie(
    api, board_a, orgs
):
    from .factories import give_role, make_user

    org = orgs["a"]
    reader = make_user("seriennachfolge@example.org")
    give_role(reader, org, permissions=["todos.view"], name="Nachfolge")
    first = start(api, board_a, org)
    complete(api, board_a, org, first)
    second = api(board_a).get(url(org, tasks(org)[1].pk)).json()
    second = patch(
        api, board_a, org, second, shares=[{"user": reader.pk, "level": "edit"}], following=True
    ).json()
    assert patch(api, board_a, org, second, owner=reader.pk).status_code == 400
    assert api(reader).get(url(org, first["id"])).status_code == 404
    first = api(board_a).get(url(org, first["id"])).json()
    assert (
        patch(api, board_a, org, first, shares=[{"user": reader.pk, "level": "edit"}]).status_code
        == 200
    )
    response = patch(api, board_a, org, second, owner=reader.pk)
    assert response.status_code == 200, response.content
    with rls_bypass():
        assert set(
            Todo.objects.filter(series_id=first["series"]["id"], withdrawn=False).values_list(
                "owner_id", flat=True
            )
        ) == {reader.pk}
