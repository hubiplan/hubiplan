import datetime

import pytest
from django.utils import timezone

from core.tenancy import tenant_context
from events.models import Event

from .factories import give_role, make_user
from .test_todos import create, patch, url

pytestmark = pytest.mark.django_db


def event(org, visibility="members"):
    org.enabled_modules = [*org.enabled_modules, "events"]
    org.save(update_fields=["enabled_modules"])
    with tenant_context(org.pk):
        return Event.objects.create(
            organization=org,
            title="Versammlung",
            starts_at=timezone.now(),
            ends_at=timezone.now() + datetime.timedelta(hours=1),
            visibility=visibility,
        )


def test_termin_verknuepfen_ohne_frist_oder_freigabe_aenderung(api, board_a, orgs):
    appointment = event(orgs["a"])
    task = create(api, board_a, orgs["a"], event=appointment.pk)
    assert task["event"]["title"] == "Versammlung"
    assert task["shared"] is False and task["due_date"] is None
    response = patch(api, board_a, orgs["a"], task, event=None)
    assert response.status_code == 200 and response.json()["event"] is None


def test_aufgabenrechte_geben_keine_terminrechte(api, orgs):
    appointment = event(orgs["a"], "board")
    reader = make_user("aufgaben@example.org")
    give_role(reader, orgs["a"], permissions=["todos.view"], name="Aufgaben lesen")
    response = api(reader).post(
        url(orgs["a"]), {"title": "Probe", "event": appointment.pk}, content_type="application/json"
    )
    assert response.status_code == 403
    assert api(reader).get(url(orgs["a"]) + "events/").json()["items"] == []


def test_fremder_termin_wird_nicht_verknuepft(api, board_a, orgs):
    event(orgs["a"])
    other = event(orgs["b"])
    response = api(board_a).post(
        url(orgs["a"]), {"title": "Probe", "event": other.pk}, content_type="application/json"
    )
    assert response.status_code == 404


def test_geteilte_aufgabe_verraet_keinen_internen_termin(api, board_a, orgs):
    appointment = event(orgs["a"], "board")
    reader = make_user("beteiligte@example.org")
    give_role(reader, orgs["a"], permissions=["todos.view"], name="Aufgaben lesen")
    task = create(api, board_a, orgs["a"], event=appointment.pk, shares=[{"user": reader.pk}])
    response = api(reader).get(url(orgs["a"], task["id"]))
    assert response.status_code == 200
    assert response.json()["event"] == {"available": False}
    assert not api(reader).get(url(orgs["a"]) + "events/").json()["items"]


def test_termin_loeschen_entfernt_auch_unsichtbare_private_links(api, board_a, orgs):
    appointment = event(orgs["a"])
    second = make_user("zweite@example.org")
    give_role(second, orgs["a"])
    task = create(api, second, orgs["a"], event=appointment.pk)
    with tenant_context(orgs["a"].pk, board_a.pk):
        Event.objects.get(pk=appointment.pk).delete()
    response = api(second).get(url(orgs["a"], task["id"]))
    assert response.json()["event"] is None
    assert response.json()["version"] > task["version"]
