"""Qualifikationen mit Ablaufdatum: Arten, Nachweise, Übersicht, Erinnerung, Helferdienste."""

import datetime

import pytest
from django.utils import timezone

from members.models import today
from qualifications import services
from qualifications.models import Qualification

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def ok(resp, code=(200, 201)):
    assert resp.status_code in ((code,) if isinstance(code, int) else code), resp.content
    return resp.json() if resp.content else None


def days(n: int) -> datetime.date:
    return today() + datetime.timedelta(days=n)


@pytest.fixture
def setup(orgs, board_a, api):
    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "qualifications", "helpers", "events"})
    org.save()
    return {
        "org": org,
        "c": api(board_a),
        "types": f"/api/orgs/{org.pk}/qualification-types/",
        "overview": f"/api/orgs/{org.pk}/qualifications/",
    }


def records(s, membership):
    return f"/api/orgs/{s['org'].pk}/members/{membership.pk}/qualifications/"


def new_type(s, name, **extra):
    return ok(s["c"].post(s["types"], {"name": name, **extra}, content_type=JSON))


def test_monate_addieren():
    assert services.add_months(datetime.date(2026, 1, 31), 1) == datetime.date(2026, 2, 28)
    assert services.add_months(datetime.date(2024, 2, 29), 12) == datetime.date(2025, 2, 28)
    assert services.add_months(datetime.date(2026, 11, 12), 26) == datetime.date(2029, 1, 12)


def test_modul_aus_ist_unsichtbar(orgs, board_a, api):
    org = orgs["a"]
    org.enabled_modules = [m for m in org.enabled_modules if m != "qualifications"]
    org.save()
    c = api(board_a)
    assert c.get(f"/api/orgs/{org.pk}/qualification-types/").status_code == 404
    assert c.get(f"/api/orgs/{org.pk}/qualifications/").status_code == 404


def test_arten_anlegen_eindeutig_archivieren(setup):
    s = setup
    kind = new_type(s, "Erste Hilfe", validity_months=24, remind_days=90)
    assert kind["validity_months"] == 24 and not kind["inspection_only"]
    assert s["c"].post(s["types"], {"name": "erste hilfe"}, content_type=JSON).status_code == 400
    assert (
        s["c"].post(s["types"], {"name": "X", "validity_months": 0}, content_type=JSON).status_code
        == 400
    )
    anna = make_member(s["org"], "Anna", "Muster")
    ok(s["c"].post(records(s, anna), {"kind": kind["id"], "acquired_on": "2025-03-01"}, JSON))
    # Eingetragene Arten nur archivieren
    resp = s["c"].delete(f"{s['types']}{kind['id']}/")
    assert resp.status_code == 409 and resp.json()["can_archive"]
    assert ok(s["c"].post(f"{s['types']}{kind['id']}/archive/"))["is_archived"]
    resp = s["c"].post(records(s, anna), {"kind": kind["id"], "acquired_on": "2025-03-01"}, JSON)
    assert resp.status_code == 400
    # Unbenutzte Art löschen
    other = new_type(s, "Sachkunde")
    assert s["c"].delete(f"{s['types']}{other['id']}/").status_code == 204


def test_nachweis_mit_vorgeschlagenem_ablauf_und_verlauf(setup):
    s = setup
    kind = new_type(s, "Erste Hilfe", validity_months=24)
    anna = make_member(s["org"], "Anna", "Muster")
    url = records(s, anna)
    first = ok(s["c"].post(url, {"kind": kind["id"], "acquired_on": "2020-05-31"}, JSON))
    assert first["valid_until"] == "2022-05-31" and first["status"] == "expired"
    # Ablaufdatum vor Beginn, Datum in der Zukunft
    bad = s["c"].post(
        url, {"kind": kind["id"], "acquired_on": "2024-01-01", "valid_until": "2023-01-01"}, JSON
    )
    assert bad.status_code == 400
    bad = s["c"].post(url, {"kind": kind["id"], "acquired_on": days(3).isoformat()}, JSON)
    assert bad.status_code == 400
    # Verlängerung: neuer Eintrag, alter bleibt im Verlauf
    renewed = ok(
        s["c"].post(
            url,
            {
                "kind": kind["id"],
                "acquired_on": today().isoformat(),
                "valid_until": days(700).isoformat(),
            },
            JSON,
        )
    )
    assert renewed["status"] == "valid"
    rows = ok(s["c"].get(url))
    assert {r["id"]: r["current"] for r in rows} == {renewed["id"]: True, first["id"]: False}
    # Unbefristet: ausdrücklich ohne Ablaufdatum
    unlimited = new_type(s, "Jugendleiter")
    row = ok(
        s["c"].post(
            url, {"kind": unlimited["id"], "acquired_on": "2019-01-01", "valid_until": None}, JSON
        )
    )
    assert row["valid_until"] is None and row["status"] == "valid"


def test_einsichtsvermerk_ohne_bemerkung(setup):
    s = setup
    kind = new_type(s, "Einsicht erweitertes Führungszeugnis", inspection_only=True)
    anna = make_member(s["org"], "Anna", "Muster")
    url = records(s, anna)
    resp = s["c"].post(
        url, {"kind": kind["id"], "acquired_on": "2025-01-10", "note": "keine Einträge"}, JSON
    )
    assert resp.status_code == 400 and "note" in resp.json()
    row = ok(s["c"].post(url, {"kind": kind["id"], "acquired_on": "2025-01-10"}, JSON))
    assert row["inspection_only"] and row["note"] == ""
    # Art mit Bemerkungen lässt sich nicht nachträglich zum Einsichtsvermerk machen
    other = new_type(s, "Sachkunde")
    ok(s["c"].post(url, {"kind": other["id"], "acquired_on": "2025-01-10", "note": "WBK"}, JSON))
    resp = s["c"].patch(f"{s['types']}{other['id']}/", {"inspection_only": True}, JSON)
    assert resp.status_code == 400


def test_rechte_lesen_und_bearbeiten(setup, api):
    s = setup
    kind = new_type(s, "Standaufsicht")
    anna = make_member(s["org"], "Anna", "Muster")
    reader = make_user("leser@example.org")
    give_role(reader, s["org"], permissions=["members.view"], name="Beisitz")
    r = api(reader)
    assert r.get(records(s, anna)).status_code == 200
    assert r.get(s["overview"]).status_code == 200
    resp = r.post(records(s, anna), {"kind": kind["id"], "acquired_on": "2025-01-01"}, JSON)
    assert resp.status_code == 403
    assert r.post(s["types"], {"name": "X"}, content_type=JSON).status_code == 403


def test_fremde_art_und_fremdes_mitglied(setup, orgs, api):
    s = setup
    b = orgs["b"]
    b.enabled_modules = sorted({*b.enabled_modules, "qualifications"})
    b.save()
    board_b = make_user("vorstand-b@example.org")
    give_role(board_b, b)
    cb = api(board_b)
    foreign = ok(cb.post(f"/api/orgs/{b.pk}/qualification-types/", {"name": "Erste Hilfe"}, JSON))
    anna = make_member(s["org"], "Anna", "Muster")
    resp = s["c"].post(records(s, anna), {"kind": foreign["id"], "acquired_on": "2025-01-01"}, JSON)
    assert resp.status_code == 400
    # Mitglied eines anderen Vereins: nicht gefunden
    bert = make_member(b, "Bert", "Beispiel")
    assert s["c"].get(records(s, bert)).status_code == 404


def test_uebersicht_und_zu_erledigen(setup):
    s = setup
    kind = new_type(s, "Erste Hilfe", remind_days=60)
    anna = make_member(s["org"], "Anna", "Abgelaufen")
    bert = make_member(s["org"], "Bert", "Bald")
    carl = make_member(s["org"], "Carl", "Gültig")
    for m, end in ((anna, days(-5)), (bert, days(30)), (carl, days(400))):
        ok(
            s["c"].post(
                records(s, m),
                {"kind": kind["id"], "acquired_on": "2024-01-01", "valid_until": end.isoformat()},
                JSON,
            )
        )
    rows = ok(s["c"].get(s["overview"]))
    assert [(r["last_name"], r["status"]) for r in rows] == [
        ("Abgelaufen", "expired"),
        ("Bald", "expiring"),
        ("Gültig", "valid"),
    ]
    soon = ok(s["c"].get(f"{s['overview']}?stand=bald&art={kind['id']}"))
    assert [r["last_name"] for r in soon] == ["Abgelaufen", "Bald"]
    assert s["c"].get(f"{s['overview']}?art=x").status_code == 400
    tasks = ok(s["c"].get(f"/api/orgs/{s['org'].pk}/open-tasks/"))["items"]
    mine = [t for t in tasks if t["kind"] == "qualifications_due"]
    assert len(mine) == 1 and mine[0]["title"] == "Erste Hilfe"
    assert "1 abgelaufen" in mine[0]["detail"] and "1 läuft bald ab" in mine[0]["detail"]


def test_erinnerung_per_mail(setup, mailoutbox):
    from qualifications.notify import send_reminders

    s = setup
    kind = new_type(s, "Übungsleiter", remind_days=30)
    anna = make_member(s["org"], "Anna", "Muster", email="anna@example.org")
    bert = make_member(s["org"], "Bert", "Verlaengert", email="bert@example.org")
    carl = make_member(s["org"], "Carl", "Spaeter", email="carl@example.org")
    for m, end in ((anna, days(20)), (bert, days(10)), (carl, days(90))):
        ok(
            s["c"].post(
                records(s, m),
                {"kind": kind["id"], "acquired_on": "2024-01-01", "valid_until": end.isoformat()},
                JSON,
            )
        )
    # Bert hat schon verlängert
    ok(
        s["c"].post(
            records(s, bert),
            {"kind": kind["id"], "acquired_on": today().isoformat(), "valid_until": None},
            JSON,
        )
    )
    mailoutbox.clear()
    assert send_reminders() == 1
    assert send_reminders() == 0
    assert [m.to for m in mailoutbox] == [["anna@example.org"]]
    assert "Übungsleiter" in mailoutbox[0].subject
    # Neues Ablaufdatum: Erinnerung wird wieder fällig
    q = Qualification.objects.get(person=anna.person, kind_id=kind["id"])
    ok(s["c"].patch(f"{records(s, anna)}{q.pk}/", {"valid_until": days(25).isoformat()}, JSON))
    q.refresh_from_db()
    assert q.reminded_at is None
    assert send_reminders(timezone.now()) == 1


def test_hinweis_bei_helferdiensten(setup, api):
    from portal.models import PortalAccess

    s = setup
    org = s["org"]
    kind = new_type(s, "Standaufsicht")
    anna = make_member(org, "Anna", "Ohne", email="anna@example.org")
    bert = make_member(org, "Bert", "Mit")
    carl = make_member(org, "Carl", "Abgelaufen")
    ok(s["c"].post(records(s, bert), {"kind": kind["id"], "acquired_on": "2024-01-01"}, JSON))
    ok(
        s["c"].post(
            records(s, carl),
            {"kind": kind["id"], "acquired_on": "2020-01-01", "valid_until": days(5).isoformat()},
            JSON,
        )
    )
    url = f"/api/orgs/{org.pk}/helpers/"
    plan = ok(s["c"].post(url, {"title": "Pokalschießen 2099"}, content_type=JSON))
    duty = ok(
        s["c"].post(
            f"{url}{plan['id']}/duties/",
            {"name": "Schießstand", "qualification": kind["id"]},
            content_type=JSON,
        )
    )
    assert duty["qualification"] == kind["id"] and duty["qualification_name"] == "Standaufsicht"
    shift = ok(
        s["c"].post(
            f"{url}duties/{duty['id']}/shifts/",
            {"day": days(20).isoformat(), "quick": "10-14", "needed": 5},
            content_type=JSON,
        )
    )[0]
    assign = f"{url}shifts/{shift['id']}/assignments/"
    ok(s["c"].post(assign, {"membership": bert.pk}, content_type=JSON))
    resp = s["c"].post(assign, {"membership": anna.pk}, content_type=JSON)
    assert resp.status_code == 400 and resp.json()["warnings"] == ["qualification"]
    resp = s["c"].post(assign, {"membership": carl.pk}, content_type=JSON)
    assert resp.status_code == 400 and resp.json()["warnings"] == ["qualification"]
    ok(s["c"].post(assign, {"membership": anna.pk, "force": True}, content_type=JSON))
    data = ok(s["c"].get(f"{url}{plan['id']}/"))
    issues = {
        a["name"]: a["qualification_issue"] for a in data["duties"][0]["shifts"][0]["assignments"]
    }
    assert issues["Bert Mit"] == "" and "Standaufsicht" in issues["Anna Ohne"]
    # Fremde Art geht nicht
    bad = s["c"].patch(f"{url}duties/{duty['id']}/", {"qualification": 999999}, JSON)
    assert bad.status_code == 400
    # Selbst eintragen im Mitgliederbereich: Hinweis, kein Eintrag
    org.member_portal_enabled = True
    org.save(update_fields=["member_portal_enabled"])
    ok(s["c"].patch(f"{url}{plan['id']}/", {"status": "published"}, content_type=JSON))
    carl_user = make_user("carl@example.org")
    access = PortalAccess.objects.create(organization=org, membership=carl, user=carl_user)
    portal = api(carl_user)
    plans = ok(portal.get(f"/api/portal/{access.pk}/helpers/"))
    assert plans["plans"][0]["duties"][0]["qualification"] == "Standaufsicht"
    resp = portal.post(f"/api/portal/{access.pk}/helpers/shifts/{shift['id']}/signup/")
    assert resp.status_code == 400 and "Vorstand" in str(resp.json())
    # Modul aus: kein Hinweis mehr
    org.enabled_modules = [m for m in org.enabled_modules if m != "qualifications"]
    org.save()
    ok(s["c"].post(assign, {"membership": carl.pk}, content_type=JSON))


def test_loeschen_nach_austritt(setup):
    from members.workflows import _purge_related

    s = setup
    kind = new_type(s, "Erste Hilfe")
    anna = make_member(s["org"], "Anna", "Muster")
    ok(s["c"].post(records(s, anna), {"kind": kind["id"], "acquired_on": "2024-01-01"}, JSON))
    _purge_related(anna, anna.person, s["org"])
    assert not Qualification.objects.filter(person=anna.person).exists()


def test_arten_fuer_dienstplan(setup):
    s = setup
    kind = new_type(s, "Standaufsicht")
    archived = new_type(s, "Alt")
    ok(s["c"].post(f"{s['types']}{archived['id']}/archive/"))
    url = f"/api/orgs/{s['org'].pk}/helpers/qualifications/"
    assert ok(s["c"].get(url)) == [{"id": kind["id"], "name": "Standaufsicht"}]
