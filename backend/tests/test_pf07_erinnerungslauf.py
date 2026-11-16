"""Aufgaben-Erinnerungslauf mit wenigen Abfragen (Gesamtaudit 15.11., PF-07).

Vorher glich der Lauf alle 5 Minuten jede offene Aufgabe mit Frist der Instanz neu ab
(Messung: zweiter, unveränderter Lauf mit mindestens drei Abfragen je Aufgabe; 500 Aufgaben
rund 9.000 Abfragen). Erfundene Daten.
"""

import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.core.cache import cache
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext

from core.tenancy import tenant_context
from todos import reminders
from todos.models import Todo, TodoReminder

from .factories import give_role, make_org, make_user

pytestmark = pytest.mark.django_db
ZONE = ZoneInfo("Europe/Berlin")
NOW = datetime.datetime(2028, 6, 1, 9, tzinfo=ZONE)


def _club(n_far: int, n_near: int):
    club = make_org(f"Aufgabenverein {n_far}-{n_near}")
    club.enabled_modules = sorted({*(club.enabled_modules or []), "todos"})
    club.save()
    owner = make_user(f"erinnerung-{n_far}-{n_near}@example.org")
    give_role(owner, club)
    far = datetime.date(2028, 7, 15)  # außerhalb des Erinnerungsfensters
    near = datetime.date(2028, 6, 3)
    with tenant_context(club.pk):
        for i in range(n_far):
            Todo.objects.create(organization=club, title=f"Später {i}", owner=owner, due_date=far)
        for i in range(n_near):
            Todo.objects.create(organization=club, title=f"Bald {i}", owner=owner, due_date=near)
    return club, owner


def _queries(now=NOW) -> int:
    with CaptureQueriesContext(connection) as q:
        reminders.run(now)
    return len(q)


def test_aufgaben_ausserhalb_des_fensters_kosten_nichts():
    cache.clear()
    _club(5, 0)
    small = _queries()
    _club(300, 0)
    large = _queries()
    print(f"PF-MESSUNG PF-07 ferne Aufgaben 5={small} 305={large} Abfragen")
    assert large == small  # unabhängig von der Zahl ferner Aufgaben
    assert large <= 10


def test_zweiter_lauf_im_fenster_mit_wenigen_abfragen():
    cache.clear()
    _club(0, 100)
    first = _queries()
    second = _queries(NOW + datetime.timedelta(minutes=5))
    print(f"PF-MESSUNG PF-07 100 Aufgaben im Fenster: erster Lauf={first}, zweiter={second}")
    assert second <= 10  # vorher mindestens 300


def test_erinnerung_wird_trotzdem_zugestellt():
    cache.clear()
    club, owner = _club(0, 1)
    todo = Todo.objects.get(organization=club)
    at = datetime.datetime(2028, 6, 2, 8, tzinfo=ZONE)  # ein Tag vor der Frist, 8 Uhr
    with (
        patch("todos.reminders.mail.send", return_value=True) as mail,
        patch("todos.reminders.send_to_user", return_value=0),
    ):
        reminders.run(NOW)
        assert reminders.run(at) == 1
    assert mail.call_count == 1
    assert TodoReminder.objects.filter(todo=todo, channel="mail", result="sent").exists()


def test_ein_fehler_haelt_die_uebrigen_nicht_auf():
    cache.clear()
    club, _ = _club(0, 3)
    todos = list(Todo.objects.filter(organization=club).order_by("pk"))
    original = reminders.sync
    calls = []

    def first_fails(todo, now=None):
        calls.append(todo.pk)
        if len(calls) == 1:
            raise RuntimeError("erfundener Einzelfehler")
        return original(todo, now)

    TodoReminder.objects.filter(todo__in=todos).delete()
    with patch.object(reminders, "sync", first_fails):
        reminders.run(NOW)
    assert len(calls) == 3
    assert TodoReminder.objects.filter(todo=todos[1]).exists()
    assert TodoReminder.objects.filter(todo=todos[2]).exists()


def test_ueberlappender_lauf_endet_sofort():
    other = connections.create_connection("default")
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [reminders.RUN_LOCK])
        with patch.object(reminders, "sync") as sync:
            assert reminders.run(NOW) == 0
        sync.assert_not_called()
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [reminders.RUN_LOCK])
    finally:
        other.close()
