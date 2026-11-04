import datetime

import pytest
from django.db import DatabaseError, transaction

from core.tenancy import tenant_context
from members.models import MembershipPeriod
from portal.models import PortalAccess
from todos.models import Todo
from todos.portal import portal_scope

from .factories import make_member, make_user
from .test_rls import as_app_role
from .test_todos import create, url

pytestmark = pytest.mark.django_db
JSON = "application/json"


def member(org, suffix="eins"):
    org.member_portal_enabled = True
    org.save(update_fields=["member_portal_enabled"])
    user = make_user(f"mitglied-{suffix}@example.org")
    membership = make_member(org, "Erika", suffix, user.email)
    with tenant_context(org.pk):
        access = PortalAccess.objects.create(organization=org, membership=membership, user=user)
    return user, access


def portal_url(access, pk=None):
    return f"/api/portal/{access.pk}/todos/" + (f"{pk}/" if pk else "")


def publish(api, board, org, todo, **values):
    response = api(board).put(
        url(org, todo["id"]) + "portal/", {"version": todo["version"], **values}, content_type=JSON
    )
    assert response.status_code == 200, response.content
    return response.json()


def change(api, user, access, task, **values):
    return api(user).patch(
        portal_url(access, task["id"]), {"version": task["version"], **values}, content_type=JSON
    )


def test_portal_sieht_nur_ausdruecklich_zugewiesene_aufgabe(api, board_a, orgs):
    user, access = member(orgs["a"])
    other, other_access = member(orgs["a"], "zwei")
    private = create(api, board_a, orgs["a"])
    assigned = create(api, board_a, orgs["a"], title="Aufbauen")
    publish(api, board_a, orgs["a"], assigned, recipients=[{"access_id": access.pk}])
    rows = api(user).get(portal_url(access)).json()["items"]
    assert [r["id"] for r in rows] == [assigned["id"]]
    assert api(user).get(portal_url(access, private["id"])).status_code == 404
    assert api(other).get(portal_url(other_access)).json()["items"] == []
    assert api(other).get(portal_url(access)).status_code == 404
    assert api(user).get(url(orgs["a"])).status_code == 403
    done = change(api, user, access, rows[0], status="done")
    assert done.status_code == 200, done.content
    assert done.json()["status"] == "done"


def test_leserecht_im_portal_ist_keine_bearbeitung(api, board_a, orgs):
    user, access = member(orgs["a"])
    task = create(api, board_a, orgs["a"])
    publish(
        api, board_a, orgs["a"], task, recipients=[{"access_id": access.pk, "can_complete": False}]
    )
    row = api(user).get(portal_url(access, task["id"])).json()
    assert not row["can_complete"]
    assert change(api, user, access, row, status="done").status_code == 403
    assert change(api, user, access, row, title="Fremde Änderung").status_code == 400


def test_angebot_wird_einmal_uebernommen_und_kann_freigegeben_werden(api, board_a, orgs):
    first, a = member(orgs["a"])
    second, b = member(orgs["a"], "zwei")
    task = create(api, board_a, orgs["a"])
    publish(api, board_a, orgs["a"], task, mode="offer")
    initial = api(first).get(portal_url(a, task["id"])).json()
    assert initial["can_claim"] and not initial["can_complete"]
    claimed = change(api, first, a, initial, action="claim")
    assert claimed.status_code == 200, claimed.content
    assert claimed.json()["can_complete"]
    assert change(api, second, b, initial, action="claim").status_code == 409
    current = api(second).get(portal_url(b, task["id"])).json()
    assert not current["can_complete"]
    assert change(api, second, b, current, action="release").status_code == 403
    released = change(api, first, a, claimed.json(), action="release")
    assert released.status_code == 200
    assert released.json()["can_claim"]


def test_entzug_portal_und_mitgliedschaft_sperren_alle_wege(api, board_a, orgs):
    user, access = member(orgs["a"])
    task = create(api, board_a, orgs["a"])
    saved = publish(api, board_a, orgs["a"], task, recipients=[{"access_id": access.pk}])
    row = api(user).get(portal_url(access, task["id"])).json()
    publish(api, board_a, orgs["a"], {**task, "version": saved["version"]}, active=False)
    assert api(user).get(portal_url(access, task["id"])).status_code == 404
    assert change(api, user, access, row, status="done").status_code == 404
    current = api(board_a).get(url(orgs["a"], task["id"])).json()
    publish(api, board_a, orgs["a"], current, mode="offer")
    with tenant_context(orgs["a"].pk):
        MembershipPeriod.objects.filter(membership_id=access.membership_id).update(
            exit_date=datetime.date(2020, 1, 1)
        )
    assert api(user).get(portal_url(access)).status_code == 404


def test_portal_rls_verhindert_private_inhalte_und_titelaenderung(api, board_a, orgs):
    user, access = member(orgs["a"])
    private = create(api, board_a, orgs["a"])
    task = create(api, board_a, orgs["a"])
    publish(api, board_a, orgs["a"], task, recipients=[{"access_id": access.pk}])
    with as_app_role(), tenant_context(orgs["a"].pk, user.pk):
        portal_scope(user, access.pk)
        assert not Todo.objects.filter(pk=private["id"]).exists()
        assert Todo.objects.filter(pk=task["id"]).exists()
        protected = Todo.objects.get(pk=task["id"])
        protected.title = "Nicht erlaubt"
        with pytest.raises(DatabaseError), transaction.atomic():
            protected.save(update_fields=["title"])


def test_portal_api_mit_echter_datenbankrolle(api, board_a, orgs):
    user, access = member(orgs["a"])
    private = create(api, board_a, orgs["a"])
    task = create(api, board_a, orgs["a"])
    with as_app_role():
        publish(api, board_a, orgs["a"], task, recipients=[{"access_id": access.pk}])
        rows = api(user).get(portal_url(access))
        assert rows.status_code == 200, rows.content
        row = rows.json()["items"][0]
        response = change(api, user, access, row, status="done")
        assert response.status_code == 200, response.content
        assert api(user).get(portal_url(access, private["id"])).status_code == 404


def test_serienfreigabe_ist_ausdruecklich_und_offenes_angebot_startet_neu(api, board_a, orgs):
    user, access = member(orgs["a"])
    task = create(api, board_a, orgs["a"], due_date="2030-01-01")
    series = api(board_a).patch(
        url(orgs["a"], task["id"]) + "series/",
        {"version": task["version"], "repeat": "monthly"},
        content_type=JSON,
    )
    assert series.status_code == 200, series.content
    task = api(board_a).get(url(orgs["a"], task["id"])).json()
    publish(api, board_a, orgs["a"], task, mode="offer", following=True)
    row = api(user).get(portal_url(access, task["id"])).json()
    claimed = change(api, user, access, row, action="claim").json()
    completed = change(api, user, access, claimed, status="done")
    assert completed.status_code == 200, completed.content
    rows = api(user).get(portal_url(access)).json()["items"]
    following = next(row for row in rows if row["id"] != task["id"])
    assert following["can_claim"] and not following["claimed_by_me"]


def test_reine_aufgabenleser_veroeffentlichen_nicht(api, board_a, orgs):
    from .factories import give_role

    user, access = member(orgs["a"])
    give_role(user, orgs["a"], permissions=["todos.view"], name="Lesen")
    task = create(api, user, orgs["a"])
    response = api(user).put(
        url(orgs["a"], task["id"]) + "portal/",
        {"version": task["version"], "mode": "offer"},
        content_type=JSON,
    )
    assert response.status_code == 403


def test_fremde_mitgliedschaft_ist_keine_zulaessige_freigabe(api, board_a, orgs):
    _, access = member(orgs["b"])
    task = create(api, board_a, orgs["a"])
    response = api(board_a).put(
        url(orgs["a"], task["id"]) + "portal/",
        {"version": task["version"], "recipients": [{"access_id": access.pk}]},
        content_type=JSON,
    )
    assert response.status_code == 400


def test_mitglieder_export_beachtet_heutige_freigabe(api, board_a, orgs):
    user, access = member(orgs["a"])
    task = create(api, board_a, orgs["a"])
    saved = publish(api, board_a, orgs["a"], task, recipients=[{"access_id": access.pk}])
    exported = api(user).get("/api/me/todos/export/")
    assert exported.status_code == 200
    assert task["id"] in [row["id"] for row in exported.json()["tasks"]]
    publish(api, board_a, orgs["a"], {**task, "version": saved["version"]}, active=False)
    assert not api(user).get("/api/me/todos/export/").json()["tasks"]


def test_mitglieder_erinnerungen_enden_mit_der_freigabe(api, board_a, orgs):
    from core.tenancy import rls_bypass
    from todos.reminders import current_recipients

    user, access = member(orgs["a"])
    task = create(api, board_a, orgs["a"], due_date="2030-01-01")
    saved = publish(api, board_a, orgs["a"], task, recipients=[{"access_id": access.pk}])
    with rls_bypass():
        current = Todo.objects.get(pk=task["id"])
        assert user.pk in current_recipients(current)
    publish(api, board_a, orgs["a"], {**task, "version": saved["version"]}, active=False)
    with rls_bypass():
        assert user.pk not in current_recipients(Todo.objects.get(pk=task["id"]))
