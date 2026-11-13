"""Fristenkalender: Pflichten des Vereins, Vorschläge, Erledigung, Erinnerung und die Aufgabe
nach einer Vorstandswahl."""

import datetime

import pytest
from django.utils import timezone

from access.models import Role
from core.tenancy import tenant_context
from obligations.models import Obligation, ObligationDone
from obligations.notify import send_reminders
from obligations.services import add_months

from .factories import give_role, make_user
from .test_versammlungen import new_meeting, release

pytestmark = pytest.mark.django_db
JSON = "application/json"


def ok(resp, code=(200, 201)):
    assert resp.status_code in ((code,) if isinstance(code, int) else code), resp.content
    return resp.json() if resp.content else None


@pytest.fixture
def setup(orgs, api):
    org = orgs["a"]
    org.enabled_modules = sorted(
        {*org.enabled_modules, "obligations", "meetings", "events", "todos"}
    )
    org.save()
    chef = make_user("vorsitz@example.org", first_name="Erika")
    give_role(
        chef,
        org,
        permissions=["obligations.edit", "meetings.edit", "todos.edit"],
        name="1. Vorsitzender",
    )
    Role.objects.filter(organization=org, name="1. Vorsitzender").update(represents=True)
    kasse = make_user("kasse@example.org", first_name="Karl")
    give_role(kasse, org, permissions=["obligations.view"], name="Kassierer")
    return {
        "org": org,
        "chef": api(chef),
        "kasse": api(kasse),
        "kasse_role": Role.objects.get(organization=org, name="Kassierer"),
        "base": f"/api/orgs/{org.pk}/obligations/",
        "url": f"/api/orgs/{org.pk}/meetings/",
    }


def test_monate_addieren():
    assert add_months(datetime.date(2026, 1, 31), 1) == datetime.date(2026, 2, 28)
    assert add_months(datetime.date(2026, 2, 28), 12) == datetime.date(2027, 2, 28)
    assert add_months(datetime.date(2026, 7, 15), 36) == datetime.date(2029, 7, 15)


def test_vorschlaege_uebernehmen_und_pflegen(setup):
    s = setup
    data = ok(s["chef"].get(s["base"]))
    assert data["items"] == [] and data["can_edit"] is True
    keys = [v["key"] for v in data["suggestions"]]
    # Ohne Registereintrag im Impressum fehlen die Vorschläge nur für eingetragene Vereine
    assert "tax_exemption" in keys and "cash_audit" in keys and "register_board" not in keys
    item = ok(
        s["chef"].post(
            s["base"],
            {"key": "tax_exemption", "role": s["kasse_role"].pk},
            content_type=JSON,
        ),
        201,
    )
    assert item["interval_months"] == 36 and item["role_name"] == "Kassierer"
    assert item["due_date"].endswith("-07-31") and item["status"] in ("planned", "soon")
    # Zweimal übernehmen geht nicht; der Vorschlag ist aus der Liste verschwunden
    assert s["chef"].post(s["base"], {"key": "tax_exemption"}, content_type=JSON).status_code == 400
    assert "tax_exemption" not in [v["key"] for v in ok(s["chef"].get(s["base"]))["suggestions"]]
    # Eigene Pflicht braucht Bezeichnung und Frist
    assert s["chef"].post(s["base"], {"title": "TÜV"}, content_type=JSON).status_code == 400
    own = ok(
        s["chef"].post(
            s["base"],
            {"title": "Schießstand abnehmen lassen", "due_date": "2030-05-01", "remind_days": 60},
            content_type=JSON,
        ),
        201,
    )
    assert own["interval_months"] is None and own["key"] == ""
    changed = ok(
        s["chef"].patch(
            f"{s['base']}{own['id']}/",
            {"version": own["version"], "interval_months": 48, "note": "alle vier Jahre"},
            content_type=JSON,
        )
    )
    assert changed["interval_months"] == 48 and changed["version"] == own["version"] + 1
    # Veralteter Stand: Konflikt
    resp = s["chef"].patch(
        f"{s['base']}{own['id']}/", {"version": own["version"], "title": "X"}, content_type=JSON
    )
    assert resp.status_code == 409
    # Lesende dürfen nichts ändern
    assert s["kasse"].post(s["base"], {"key": "insurance"}, content_type=JSON).status_code == 403
    assert s["kasse"].delete(f"{s['base']}{own['id']}/").status_code == 403
    assert s["chef"].delete(f"{s['base']}{own['id']}/").status_code == 204


def test_fremde_einheit_und_modul_aus(setup, orgs, api):
    s = setup
    other = make_user("fremd@example.org")
    give_role(other, orgs["b"], permissions=["obligations.edit"], name="Vorstand")
    assert api(other).get(s["base"]).status_code == 404
    org = s["org"]
    org.enabled_modules = sorted({*org.enabled_modules} - {"obligations"})
    org.save()
    assert s["chef"].get(s["base"]).status_code == 404


def test_rolle_einer_fremden_einheit_abgelehnt(setup, orgs):
    s = setup
    with tenant_context(orgs["b"].pk):
        foreign = Role.objects.create(organization=orgs["b"], name="Fremd", permissions=[])
    resp = s["chef"].post(
        s["base"],
        {"title": "Test", "due_date": "2030-01-01", "role": foreign.pk},
        content_type=JSON,
    )
    assert resp.status_code == 400


def test_erledigt_schiebt_frist_und_fuehrt_verlauf(setup):
    s = setup
    today = timezone.localdate()
    due = today + datetime.timedelta(days=5)
    item = ok(
        s["chef"].post(
            s["base"],
            {
                "title": "Kassenprüfung",
                "due_date": due.isoformat(),
                "interval_months": 12,
                "role": s["kasse_role"].pk,
            },
            content_type=JSON,
        ),
        201,
    )
    assert item["status"] == "soon"
    url = f"{s['base']}{item['id']}/done/"
    # Datum in der Zukunft wird abgelehnt
    future = (today + datetime.timedelta(days=1)).isoformat()
    assert s["chef"].post(url, {"done_on": future}, content_type=JSON).status_code == 400
    # Die Inhaberin der zuständigen Rolle darf erledigen, auch nur mit Leserecht
    done = ok(s["kasse"].post(url, {"note": "Bericht liegt vor"}, content_type=JSON))
    assert done["due_date"] == add_months(due, 12).isoformat() and done["status"] == "planned"
    assert done["history"][0]["note"] == "Bericht liegt vor"
    assert done["history"][0]["due_date"] == due.isoformat()
    # Einmalige Pflicht: nach Erledigung abgeschlossen
    once = ok(
        s["chef"].post(
            s["base"], {"title": "Einmalig", "due_date": due.isoformat()}, content_type=JSON
        ),
        201,
    )
    closed = ok(s["chef"].post(f"{s['base']}{once['id']}/done/", {}, content_type=JSON))
    assert closed["active"] is False and closed["status"] == "done"
    assert (
        s["chef"].post(f"{s['base']}{once['id']}/done/", {}, content_type=JSON).status_code == 400
    )
    with tenant_context(s["org"].pk):
        assert ObligationDone.objects.filter(organization=s["org"]).count() == 2


def test_erinnerung_per_mail_und_zu_erledigen(setup, mailoutbox):
    s = setup
    org = s["org"]
    today = timezone.localdate()
    due = today + datetime.timedelta(days=20)
    item = ok(
        s["chef"].post(
            s["base"],
            {
                "title": "Kassenprüfung",
                "due_date": due.isoformat(),
                "interval_months": 12,
                "remind_days": 30,
                "role": s["kasse_role"].pk,
            },
            content_type=JSON,
        ),
        201,
    )
    later = ok(
        s["chef"].post(
            s["base"],
            {
                "title": "Versicherungen",
                "due_date": (today + datetime.timedelta(days=200)).isoformat(),
                "remind_days": 30,
            },
            content_type=JSON,
        ),
        201,
    )
    mailoutbox.clear()
    assert send_reminders() == 1
    assert mailoutbox[0].to == ["kasse@example.org"]
    assert "Kassenprüfung" in mailoutbox[0].subject and "Hallo Karl" in mailoutbox[0].body
    # Je Frist nur einmal
    assert send_reminders() == 0
    # Ohne zuständige Rolle: an alle, die den Fristenkalender pflegen
    with tenant_context(org.pk):
        Obligation.objects.filter(pk=later["id"]).update(
            due_date=today - datetime.timedelta(days=2)
        )
    mailoutbox.clear()
    assert send_reminders() == 1
    assert mailoutbox[0].to == ["vorsitz@example.org"] and "Überfällig" in mailoutbox[0].subject
    # Zu erledigen: Pflegende sehen beide, die Kassiererin nur ihre
    tasks = f"/api/orgs/{org.pk}/open-tasks/"
    rows = [r for r in ok(s["chef"].get(tasks))["items"] if r["area"] == "obligations"]
    assert [r["title"] for r in rows] == ["Versicherungen", "Kassenprüfung"]
    assert rows[0]["highlight"] is True and rows[1]["highlight"] is False
    mine = [r for r in ok(s["kasse"].get(tasks))["items"] if r["area"] == "obligations"]
    assert [r["title"] for r in mine] == ["Kassenprüfung"]
    assert mine[0]["link"] == f"/fristenkalender?pflicht={item['id']}"
    # Nach Erledigung beginnt die Erinnerung für die neue Frist von vorn
    ok(s["kasse"].post(f"{s['base']}{item['id']}/done/", {}, content_type=JSON))
    with tenant_context(org.pk):
        assert Obligation.objects.get(pk=item["id"]).reminded_for is None


def test_aufgabe_nach_vorstandswahl(setup):
    from meetings.models import Resolution
    from organizations.imprint import ensure
    from todos.models import Todo, TodoShare

    s = setup
    org = s["org"]
    elections = [
        {"kind": "election", "office": "1. Vorsitzender", "elected_name": "Erika Vorsitz"},
        {"kind": "election", "office": "Kassierer", "elected_name": "Gerd Geld"},
    ]
    # Nicht im Register eingetragen und keine Pflicht übernommen: keine Aufgabe
    release(s, new_meeting(s), elections)
    with tenant_context(org.pk):
        assert not Todo.objects.filter(organization=org).exists()
    # Eingetragener Verein: Aufgabe auch ohne eigenen Eintrag im Fristenkalender
    imprint = ensure(org)
    imprint.registered = True
    imprint.save()
    assert "register_board" in [v["key"] for v in ok(s["chef"].get(s["base"]))["suggestions"]]
    meeting = release(s, new_meeting(s), elections)
    with tenant_context(org.pk):
        todo = Todo.objects.get(organization=org)
        assert todo.title == "Vorstandsänderung beim Registergericht anmelden"
        start = datetime.date.fromisoformat(meeting["starts_at"][:10])
        assert todo.due_date == start + datetime.timedelta(days=14)
        # Nur das vertretungsberechtigte Amt steht in der Aufgabe und ist verknüpft
        assert "1. Vorsitzender: Erika Vorsitz" in todo.description
        assert "Gerd Geld" not in todo.description and "§ 67 BGB" in todo.description
        linked = Resolution.objects.filter(todo=todo)
        assert [r.office for r in linked] == ["1. Vorsitzender"]
        todo.delete()
    # Übernommen mit zuständiger Rolle und eigener Frist: Aufgabe ist mit der Rolle geteilt
    rule = ok(
        s["chef"].post(
            s["base"],
            {"key": "register_board", "role": s["kasse_role"].pk, "days_after": 28},
            content_type=JSON,
        ),
        201,
    )
    assert rule["status"] == "election" and rule["due_date"] is None
    meeting = release(s, new_meeting(s), elections)
    with tenant_context(org.pk):
        todo = Todo.objects.get(organization=org)
        start = datetime.date.fromisoformat(meeting["starts_at"][:10])
        assert todo.due_date == start + datetime.timedelta(days=28) and todo.shared
        share = TodoShare.objects.get(todo=todo)
        assert share.role_id == s["kasse_role"].pk and share.level == "edit"
        todo.delete()
    # Abgeschaltet: keine Aufgabe mehr
    ok(
        s["chef"].patch(
            f"{s['base']}{rule['id']}/",
            {"version": rule["version"], "active": False},
            content_type=JSON,
        )
    )
    release(s, new_meeting(s), elections)
    with tenant_context(org.pk):
        assert not Todo.objects.filter(organization=org, deleted_at__isnull=True).exists()


def test_wahl_ohne_aufgabenmodul_legt_pflicht_an(setup):
    from organizations.imprint import ensure

    s = setup
    org = s["org"]
    org.enabled_modules = sorted({*org.enabled_modules} - {"todos"})
    org.save()
    imprint = ensure(org)
    imprint.registered = True
    imprint.save()
    release(
        s,
        new_meeting(s),
        [{"kind": "election", "office": "1. Vorsitzender", "elected_name": "Erika Vorsitz"}],
    )
    items = ok(s["chef"].get(s["base"]))["items"]
    assert [i["title"] for i in items] == ["Vorstandsänderung beim Registergericht anmelden"]
    assert items[0]["interval_months"] is None and "Erika Vorsitz" in items[0]["note"]
