import datetime
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.db import close_old_connections, connection
from django.utils import timezone

from access.models import RoleAssignment
from core.tenancy import tenant_context
from todos.models import Todo, TodoPreference, TodoReminder, TodoReminderConfig
from todos.reminders import (
    current_recipients,
    deadline,
    deliver,
    highlight,
    local_time,
    run,
    sync,
    times,
)

from .factories import give_role, make_user
from .test_todos import create, url
from .test_todos import patch as change

pytestmark = pytest.mark.django_db
ZONE = ZoneInfo("Europe/Berlin")
DUE = datetime.date(2028, 5, 10)
AT = datetime.datetime(2028, 5, 9, 8, tzinfo=ZONE)


def task(api, board_a, orgs, **values):
    result = create(api, board_a, orgs["a"], due_date=str(DUE), **values)
    return Todo.objects.get(pk=result["id"])


def test_tagesfrist_und_erinnerung_getrennt(api, board_a, orgs):
    todo = task(api, board_a, orgs)
    assert deadline(todo) == datetime.datetime(2028, 5, 11, 0, tzinfo=ZONE)
    assert dict(times(todo, [1]))["before:1"] == AT
    assert dict(times(todo, [1]))["overdue_once"] == datetime.datetime(2028, 5, 11, 8, tzinfo=ZONE)
    assert not highlight(todo, board_a, AT - datetime.timedelta(seconds=1))["highlight"]
    assert highlight(todo, board_a, AT)["highlight"]


def test_uhrzeitfrist_hat_24_stunden_vorlauf_auch_beim_zeitwechsel(api, board_a, orgs):
    result = create(api, board_a, orgs["a"], due_date="2028-03-26", due_time="10:00")
    todo = Todo.objects.get(pk=result["id"])
    at = dict(times(todo, [1]))["before:1"]
    assert deadline(todo).astimezone(datetime.UTC) - at == datetime.timedelta(hours=24)
    assert local_time(datetime.date(2028, 3, 26), datetime.time(2, 30), "Europe/Berlin").hour == 3
    assert local_time(datetime.date(2028, 3, 26), datetime.time(2, 30), "Europe/Berlin").minute == 0
    repeated = local_time(datetime.date(2028, 10, 29), datetime.time(2, 30), "Europe/Berlin")
    assert repeated.fold == 0


def test_job_versendet_pro_kanal_nur_einmal(api, board_a, orgs):
    todo = task(api, board_a, orgs)
    with (
        patch("todos.reminders.mail.send", return_value=True) as mail,
        patch("todos.reminders.send_to_user", return_value=1) as push,
    ):
        assert run(AT) == 2
        assert run(AT + datetime.timedelta(minutes=5)) == 0
        assert mail.call_count == push.call_count == 1
    assert TodoReminder.objects.filter(todo=todo, result="sent").count() == 2


def test_ein_fehler_verhindert_anderen_kanal_nicht(api, board_a, orgs):
    todo = task(api, board_a, orgs)
    with (
        patch("todos.reminders.mail.send", side_effect=OSError("Testfehler")),
        patch("todos.reminders.send_to_user", return_value=1) as push,
    ):
        assert run(AT) == 1
        assert push.call_count == 1
        assert run(AT) == 0
    assert TodoReminder.objects.filter(todo=todo, result="failed").count() == 1


def test_ueberfaellig_nur_einmal_am_folgetag(api, board_a, orgs):
    task(api, board_a, orgs)
    at = datetime.datetime(2028, 5, 11, 8, tzinfo=ZONE)
    with (
        patch("todos.reminders.mail.send", return_value=True) as mail,
        patch("todos.reminders.send_to_user", return_value=1),
    ):
        assert run(at) == 2
        assert run(at + datetime.timedelta(days=1)) == 0
        assert mail.call_count == 1


def test_erledigt_und_geloescht_werden_nicht_erinnert(api, board_a, orgs):
    todo = task(api, board_a, orgs)
    with tenant_context(orgs["a"].pk, board_a.pk):
        todo.status = "done"
        todo.save()
    with patch("todos.reminders.mail.send") as mail, patch("todos.reminders.send_to_user") as push:
        assert run(AT) == 0
        assert not mail.called and not push.called


def test_spaetere_frist_behaelt_versandnachweise(api, board_a, orgs):
    todo = task(api, board_a, orgs)
    with (
        patch("todos.reminders.mail.send", return_value=True),
        patch("todos.reminders.send_to_user", return_value=1),
    ):
        assert run(AT) == 2
    response = change(
        api, board_a, orgs["a"], {"id": todo.pk, "version": todo.version}, due_date="2028-05-20"
    )
    assert response.status_code == 200
    assert TodoReminder.objects.filter(todo=todo, due_revision=1, result="sent").count() == 2
    assert TodoReminder.objects.filter(todo=todo, due_revision=2, result="pending").exists()


def test_zustaendige_statt_aller_beteiligten(api, board_a, orgs):
    reader = make_user("zustaendig@example.org")
    give_role(reader, orgs["a"], ["todos.view"], name="Lesen")
    todo = task(api, board_a, orgs)
    response = change(
        api,
        board_a,
        orgs["a"],
        {"id": todo.pk, "version": todo.version},
        shares=[{"user": reader.pk, "level": "view", "responsible": True}],
    )
    assert response.status_code == 200
    todo.refresh_from_db()
    assert set(current_recipients(todo)) == {reader.pk}


def test_rollenverlust_storniert_und_nachfolge_sendet_nichts_nach(api, board_a, orgs):
    reader = make_user("erinnerung@example.org")
    give_role(reader, orgs["a"], ["todos.view"], name="Lesen")
    todo = task(api, board_a, orgs)
    change(
        api,
        board_a,
        orgs["a"],
        {"id": todo.pk, "version": todo.version},
        shares=[{"user": reader.pk, "responsible": True}],
    )
    todo.refresh_from_db()
    old_revision = TodoReminderConfig.objects.get(todo=todo, user=reader).revision
    RoleAssignment.objects.filter(user=reader, organization=orgs["a"]).delete()
    sync(todo, AT - datetime.timedelta(hours=1))
    assert not TodoReminder.objects.filter(todo=todo, user=reader, result="pending").exists()
    give_role(reader, orgs["a"], ["todos.view"], name="Lesen")
    sync(todo, AT + datetime.timedelta(minutes=10))
    config = TodoReminderConfig.objects.get(todo=todo, user=reader)
    assert config.revision > old_revision
    assert not TodoReminder.objects.filter(
        todo=todo, user=reader, result="pending", scheduled_at__lte=AT
    ).exists()


def test_persoenliche_einstellungen_und_validierung(api, board_a, orgs):
    todo = task(api, board_a, orgs)
    endpoint = url(orgs["a"], todo.pk) + "reminders/"
    assert (
        api(board_a).patch(endpoint, {"days": [-1]}, content_type="application/json").status_code
        == 400
    )
    response = api(board_a).patch(
        endpoint, {"days": [7, 1, 1], "mail": False, "push": True}, content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["days"] == [1, 7]


def test_deaktivierter_kanal_bleibt_auch_zur_uhrzeitfrist_aus(api, board_a, orgs):
    todo = task(api, board_a, orgs, due_time="12:00")
    config = TodoReminderConfig.objects.get(todo=todo, user=board_a)
    config.days = [0]
    config.mail = False
    config.push = False
    config.revision += 1
    config.save()
    sync(todo, AT)
    with patch("todos.reminders.mail.send") as mail, patch("todos.reminders.send_to_user") as push:
        assert run(deadline(todo)) == 0
        assert not mail.called and not push.called


def test_private_loeschung_bleibt_nach_rollenverlust_moeglich(api, board_a, board_b, orgs):
    todo = task(api, board_a, orgs)
    RoleAssignment.objects.filter(user=board_a, organization=orgs["a"]).delete()
    assert api(board_b).delete(f"/api/me/todos/{todo.pk}/").status_code == 404
    assert api(board_a).delete(f"/api/me/todos/{todo.pk}/").status_code == 204
    assert not Todo.objects.filter(pk=todo.pk).exists()


def test_optionale_aufbewahrung_standardmaessig_aus(api, board_a, orgs):
    from todos.cleanup import completed

    todo = task(api, board_a, orgs)
    now = timezone.now()
    todo.status = "done"
    todo.done_at = now - datetime.timedelta(days=400)
    todo.save()
    assert completed(now) == 0
    TodoPreference.objects.filter(user=board_a).update(purge_done=True)
    assert completed(now) == 1
    todo.refresh_from_db()
    assert todo.deleted_at == now


def test_gemeinsame_aufbewahrung_braucht_auch_rollenrecht(api, orgs):
    user = make_user("aufgaben-teilen@example.org")
    give_role(user, orgs["a"], ["todos.edit"], name="Aufgaben teilen")
    response = api(user).patch(
        url(orgs["a"]) + "cleanup/", {"purge_done": True}, content_type="application/json"
    )
    assert response.status_code == 403


def test_rollenansicht_gilt_nur_in_der_gewaehlten_einheit(api, board_a, orgs):
    from access.models import Role

    give_role(board_a, orgs["b"], name="Zweiter Vorstand")
    personal = create(api, board_a, orgs["b"])
    role = Role.objects.get(organization=orgs["a"], name="Vorstand")
    client = api(board_a)
    assert (
        client.post(
            f"/api/orgs/{orgs['a'].pk}/ansicht/", {"role": role.pk}, content_type="application/json"
        ).status_code
        == 200
    )
    assert client.get(url(orgs["b"], personal["id"])).status_code == 200


@pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL-RLS")
def test_verantwortung_auch_unter_rls_uebertragen(api, board_a, orgs):
    from .test_rls import as_app_role

    other = make_user("neue-verantwortung@example.org")
    give_role(other, orgs["a"], ["todos.view"], name="Neue Verantwortung")
    with as_app_role():
        todo = create(api, board_a, orgs["a"])
        shared = change(
            api, board_a, orgs["a"], todo, shares=[{"user": other.pk, "level": "edit"}]
        ).json()
        transferred = change(api, board_a, orgs["a"], shared, owner=other.pk)
        assert transferred.status_code == 200
        assert transferred.json()["owner"] == other.pk


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL-Zeilensperren")
def test_parallele_jobs_beanspruchen_einen_versuch_nur_einmal(api, board_a, orgs):
    todo = task(api, board_a, orgs)
    item = TodoReminder.objects.get(todo=todo, channel="mail", rule="before:1")

    def send():
        close_old_connections()
        try:
            return deliver(item.pk, AT)
        finally:
            close_old_connections()

    with (
        patch("todos.reminders.mail.send", return_value=True) as mail,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        results = list(pool.map(lambda _: send(), range(2)))
    assert sum(results) == 1
    assert mail.call_count == 1
