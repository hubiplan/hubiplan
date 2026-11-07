"""Personal opt-in, retry safety and protection of manually edited tasks."""
# ruff: noqa: F811

import datetime

import pytest
from django.utils import timezone

from core.tenancy import tenant_context
from music.custody_reminders import custody_reminders, synchronize
from music.models import (
    Equipment,
    EquipmentLoan,
    MusicReminderPreference,
    MusicReminderTask,
    ScoreLoan,
)
from todos.models import Todo

from .factories import give_role, make_user
from .test_music import JSON, c, club, music  # noqa: F401
from .test_music_equipment import equipment, issue, register  # noqa: F401
from .test_music_practice import practice  # noqa: F401

pytestmark = pytest.mark.django_db


def enable(c, club):
    response = c.post(
        f"/api/orgs/{club.pk}/music/custody-reminders/",
        {"enabled": True, "days_ahead": 7, "scores": True, "equipment": True},
        content_type=JSON,
    )
    assert response.status_code == 200, response.content
    with tenant_context(club.pk):
        return MusicReminderPreference.objects.get()


def test_score_tasks_are_private_idempotent_and_resolved(c, club, practice):
    _, _, musician, _, _, part = practice
    with tenant_context(club.pk):
        loan = ScoreLoan.objects.create(
            organization=club, musician=musician, part=part, quantity=1, due_on=timezone.localdate()
        )
    pref = enable(c, club)
    assert custody_reminders() == 0
    response = c.get(f"/api/orgs/{club.pk}/todos/")
    assert response.status_code == 200, response.content
    assert response.json()["items"][0]["music_url"] == f"/musik/proben?notenausgabe={loan.pk}"
    with tenant_context(club.pk, pref.user_id):
        link = MusicReminderTask.objects.get()
        todo = link.todo
        from music.custody_reminders import task_link
        from todos.access import Scope

        assert task_link(todo, Scope(club, None, {"todos.view"})) == ""
        assert not todo.shared and todo.owner_id == pref.user_id and todo.due_date == loan.due_on
        assert f"notenausgabe={loan.pk}" in todo.description
        assert musician.name not in todo.title if musician.name else True
        loan.returned = 1
        loan.save()
        synchronize(pref.pk)
        todo.refresh_from_db()
        assert todo.status == "done"


def test_user_edits_and_deletions_are_preserved(c, club, practice):
    _, _, musician, _, _, part = practice
    with tenant_context(club.pk):
        loan = ScoreLoan.objects.create(
            organization=club, musician=musician, part=part, quantity=1, due_on=timezone.localdate()
        )
    pref = enable(c, club)
    with tenant_context(club.pk, pref.user_id):
        todo = MusicReminderTask.objects.get().todo
        todo.title = "Eigene Nachbearbeitung"
        todo.version += 1
        todo.save()
        loan.returned = 1
        loan.save()
        synchronize(pref.pk)
        todo.refresh_from_db()
        assert todo.status == "open" and todo.title == "Eigene Nachbearbeitung"
        todo.delete()
        loan.returned = 0
        loan.save()
        assert synchronize(pref.pk) == 0
        assert not Todo.objects.exists()
        loan.due_on += datetime.timedelta(days=1)
        loan.save()
        assert synchronize(pref.pk) == 1


def test_equipment_return_and_maintenance_follow_actual_source(c, club, equipment):
    identifier = register(c, equipment)
    assert issue(c, equipment).status_code == 200
    with tenant_context(club.pk):
        Equipment.objects.filter(pk=identifier).update(maintenance_due=timezone.localdate())
    pref = enable(c, club)
    with tenant_context(club.pk, pref.user_id):
        assert Todo.objects.count() == 2
        EquipmentLoan.objects.filter(equipment_id=identifier).update(returned_at=timezone.now())
        Equipment.objects.filter(pk=identifier).update(
            maintenance_due=timezone.localdate() + datetime.timedelta(days=60)
        )
        synchronize(pref.pk)
        assert Todo.objects.filter(status="done").count() == 2


def test_preferences_cannot_target_other_users(api, club, music):
    user = make_user("reminder-reader@example.org")
    give_role(user, club, ["music.view", "todos.view"], name="Musikerinnerungen lesen")
    client = api(user)
    url = f"/api/orgs/{club.pk}/music/custody-reminders/"
    assert client.get(url).json()["enabled"] is False
    assert client.post(url, {"enabled": True}, content_type=JSON).status_code == 403


def test_reactivation_only_reopens_automatically_closed_tasks(c, club, practice):
    _, _, musician, _, _, part = practice
    with tenant_context(club.pk):
        ScoreLoan.objects.create(
            organization=club, musician=musician, part=part, quantity=1, due_on=timezone.localdate()
        )
    pref = enable(c, club)
    with tenant_context(club.pk, pref.user_id):
        todo = MusicReminderTask.objects.get().todo
        pref.enabled = False
        pref.save()
        synchronize(pref.pk)
        todo.refresh_from_db()
        assert todo.status == "done"
        pref.enabled = True
        pref.save()
        synchronize(pref.pk)
        todo.refresh_from_db()
        assert todo.status == "open"
        todo.status = "done"
        todo.version += 1
        todo.save()
        pref.enabled = False
        pref.save()
        synchronize(pref.pk)
        pref.enabled = True
        pref.save()
        synchronize(pref.pk)
        todo.refresh_from_db()
        assert todo.status == "done"
