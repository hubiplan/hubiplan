"""Erlaubte Aufgabenabläufe ohne Schreibregel unter dem Zeilenschutz (Gesamtaudit 15.11., AZ-04).

``lock_task`` sperrt mit ``SELECT ... FOR UPDATE``. Unter der Rolle der Anwendung verlangt
PostgreSQL dafür zusätzlich die Schreibregel ``task_update`` (verantwortliches Konto oder
Bearbeitungsfreigabe). Zwei fachlich erlaubte Abläufe ohne diese Regel scheiterten im Betrieb
deshalb mit 404: die Übernahme einer verwaisten Aufgabe und eigene Erinnerungseinstellungen bei
Lesefreigabe. Bejaht die Prüfung des Aufrufers den Zugriff auf die sichtbare Aufgabe, sperrt
``lock_task`` jetzt genau diese Zeile ohne Zeilenschutz. Gegenproben: ohne Recht 403, unsichtbar
404, und Erinnerungen öffnen keine Aufgabenfelder. Die Anfragen laufen wie im Betrieb unter der
Rolle der Anwendung. Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime

import pytest

from access.models import RoleAssignment
from core.tenancy import tenant_context
from todos.models import Todo, TodoReminderConfig

from .factories import give_role, make_user
from .test_todo_sharing import reader, share  # noqa: F401
from .test_todos import create, url
from .test_todos import patch as change

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anfragen_unter_app_rolle")]


def orphaned(api, board_a, org, *others):
    """Geteilte Aufgabe, deren verantwortliches Konto keinen Zugang mehr hat; der Vorstand
    (und gegebenenfalls weitere Konten) sieht sie nur über eine Lesefreigabe."""
    original = make_user("ersteller-sperre@example.org")
    give_role(original, org, name="Ersteller")
    todo = create(api, original, org)
    shares = [{"user": u.pk, "level": "view", "responsible": True} for u in (board_a, *others)]
    response = change(api, original, org, todo, shares=shares)
    assert response.status_code == 200, response.content
    with tenant_context(org.pk, original.pk):
        RoleAssignment.objects.filter(user=original, organization=org).delete()
    return original, response.json()


def test_verwaiste_aufgabe_per_bearbeitung_uebernehmen(api, board_a, orgs):
    """Übernahme einer verwaisten geteilten Aufgabe über PATCH ``owner`` = eigenes Konto.

    Erlaubt nach ``can_take_over`` (todos/access.py): geteilt, Aufgabe der eigenen Einheit,
    Rechte ``todos.edit`` und ``roles.edit``, verantwortliches Konto ohne Zugang. Der Vorstand
    hat nur eine Lesefreigabe, also keine Schreibregel; die Übernahme gelingt trotzdem.
    """
    org = orgs["a"]
    _, todo = orphaned(api, board_a, org)
    assert api(board_a).get(url(org, todo["id"])).status_code == 200
    response = change(api, board_a, org, todo, owner=board_a.pk)
    assert response.status_code == 200, response.content
    assert response.json()["owner"] == board_a.pk
    assert Todo.objects.get(pk=todo["id"]).owner_id == board_a.pk


def test_uebernahme_ohne_berechtigung_ist_403(api, board_a, orgs):
    """Gegenprobe: Das verantwortliche Konto hat noch Zugang, ``can_take_over`` verneint.
    Sichtbar über die Lesefreigabe, also 403; die Verantwortung bleibt."""
    org = orgs["a"]
    original = make_user("ersteller-aktiv@example.org")
    give_role(original, org, name="Ersteller")
    todo = share(api, original, org, create(api, original, org), board_a, "view")
    response = change(api, board_a, org, todo, owner=board_a.pk)
    assert response.status_code == 403, response.content
    assert Todo.objects.get(pk=todo["id"]).owner_id == original.pk


def test_uebernahme_ohne_fachrechte_ist_403(api, board_a, orgs, reader):
    """Gegenprobe: verwaiste Aufgabe, sichtbar über eine Lesefreigabe, aber dem Konto fehlen
    ``todos.edit`` und ``roles.edit``. Also 403; die Verantwortung bleibt."""
    org = orgs["a"]
    original, todo = orphaned(api, board_a, org, reader)
    assert api(reader).get(url(org, todo["id"])).status_code == 200
    response = change(api, reader, org, todo, owner=reader.pk)
    assert response.status_code == 403, response.content
    assert Todo.objects.get(pk=todo["id"]).owner_id == original.pk


def test_unsichtbare_aufgabe_uebernehmen_bleibt_404(api, board_a, orgs):
    """Gegenprobe: private Aufgabe eines Kontos ohne Zugang, ohne Freigabe für den Vorstand."""
    org = orgs["a"]
    original = make_user("ersteller-privat@example.org")
    give_role(original, org, name="Ersteller")
    todo = create(api, original, org)
    with tenant_context(org.pk, original.pk):
        RoleAssignment.objects.filter(user=original, organization=org).delete()
    assert api(board_a).get(url(org, todo["id"])).status_code == 404
    response = change(api, board_a, org, todo, owner=board_a.pk)
    assert response.status_code == 404, response.content
    assert Todo.objects.get(pk=todo["id"]).owner_id == original.pk


def test_eigene_erinnerung_mit_lesefreigabe(api, board_a, orgs, reader):
    """Eigene Erinnerungseinstellungen zu einer nur lesbar geteilten Aufgabe.

    Die Einstellung gehört allein dem Konto (``TodoReminderConfig.user``), die Ansicht prüft
    nur die Sichtbarkeit, und laut Hilfe kann jede Person in einer Aufgabe mit Frist ihre
    Erinnerungszeitpunkte und Kanäle ändern. Zuständige mit Lesefreigabe werden auch erinnert.
    """
    org = orgs["a"]
    todo = create(api, board_a, org, due_date=str(datetime.date(2028, 5, 10)))
    todo = share(api, board_a, org, todo, reader)
    endpoint = url(org, todo["id"]) + "reminders/"
    assert api(reader).get(endpoint).status_code == 200
    response = api(reader).patch(
        endpoint, {"days": [7, 1], "mail": False}, content_type="application/json"
    )
    assert response.status_code == 200, response.content
    assert response.json()["days"] == [1, 7]
    config = TodoReminderConfig.objects.get(todo_id=todo["id"], user=reader)
    assert config.days == [1, 7] and config.mail is False and config.customized


def test_erinnerung_oeffnet_keine_aufgabenfelder(api, board_a, orgs, reader):
    """Gegenprobe: Nach der eigenen Erinnerung darf das lesende Konto weiterhin keine
    Aufgabenfelder ändern."""
    org = orgs["a"]
    todo = create(api, board_a, org, due_date=str(datetime.date(2028, 5, 10)))
    todo = share(api, board_a, org, todo, reader)
    endpoint = url(org, todo["id"]) + "reminders/"
    response = api(reader).patch(endpoint, {"days": [1]}, content_type="application/json")
    assert response.status_code == 200, response.content
    before = Todo.objects.get(pk=todo["id"])
    current = api(reader).get(url(org, todo["id"])).json()
    assert change(api, reader, org, current, status="done").status_code == 403
    assert change(api, reader, org, current, title="Erfundener Titel").status_code == 403
    after = Todo.objects.get(pk=todo["id"])
    assert (after.status, after.title, after.version) == (
        before.status,
        before.title,
        before.version,
    )
    assert after.status != "done" and after.title == "Sitzung vorbereiten"


def test_erinnerung_unsichtbarer_aufgabe_bleibt_404(api, board_a, orgs, reader):
    """Gegenprobe: Ohne Sichtbarkeit gibt es auch keine eigene Erinnerung."""
    org = orgs["a"]
    todo = create(api, board_a, org, due_date=str(datetime.date(2028, 5, 10)))
    endpoint = url(org, todo["id"]) + "reminders/"
    response = api(reader).patch(endpoint, {"days": [1]}, content_type="application/json")
    assert response.status_code == 404, response.content
    assert not TodoReminderConfig.objects.filter(todo_id=todo["id"], user=reader).exists()
