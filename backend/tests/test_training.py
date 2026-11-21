"""Training und Anwesenheit samt Schießnachweis nach § 14 WaffG (Lückenliste 20.11.2026, B1)."""

import datetime

import pytest

from training import services
from training.models import Attendance, ShootingEntry, TrainingSession

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"
ON = datetime.date(2026, 11, 21)


def ok(resp, code=(200, 201)):
    assert resp.status_code in ((code,) if isinstance(code, int) else code), resp.content
    return resp.json() if resp.content else None


@pytest.fixture
def setup(orgs, api):
    from organizations.models import Department
    from portal.models import PortalAccess

    org = orgs["a"]
    org.enabled_modules = sorted(
        {*org.enabled_modules, "training", "portal", "competitions", "shooting"}
    )
    org.member_portal_enabled = True
    org.department_access_enabled = True
    org.save()
    jugend = Department.objects.create(
        self_managed=True, organization=org, name="Schützenjugend", short_name="Jugend"
    )
    chef = make_user("trainer@example.org")
    give_role(chef, org, permissions=["training.edit", "training.view"], name="Sportleitung")
    leser = make_user("trainingleser@example.org")
    give_role(leser, org, permissions=["training.view"], name="Training lesen")
    people, portals = {}, {}
    for first, depts in (("Anna", [jugend]), ("Bernd", []), ("Carla", [])):
        m = make_member(org, first, "Muster", departments=depts)
        user = make_user(f"{first.lower()}-training@example.org")
        access = PortalAccess.objects.create(organization=org, membership=m, user=user)
        people[first] = m
        portals[first] = (api(user), f"/api/portal/{access.pk}/training/", access, user)
    return {
        "org": org,
        "jugend": jugend,
        "chef": api(chef),
        "leser": api(leser),
        "url": f"/api/orgs/{org.pk}/training/",
        "log": f"/api/orgs/{org.pk}/shooting-log/",
        "member_log": lambda m: f"/api/orgs/{org.pk}/members/{m.pk}/shooting-log/",
        "people": people,
        "portals": portals,
    }


def entry(org, membership, day, *, wclass="short", discipline="Sportpistole", **extra):
    extra.setdefault("status", ShootingEntry.Status.CONFIRMED)
    return ShootingEntry.objects.create(
        organization=org,
        membership=membership,
        date=day,
        discipline=discipline,
        weapon_class=wclass,
        **extra,
    )


# --- Rechenregeln ------------------------------------------------------------------------


def test_monate_verschieben():
    assert services.add_months(datetime.date(2026, 3, 31), -1) == datetime.date(2026, 2, 28)
    assert services.add_months(datetime.date(2026, 2, 28), 1) == datetime.date(2026, 3, 31)
    assert services.add_months(datetime.date(2026, 11, 21), -12) == datetime.date(2025, 11, 21)
    assert services.add_months(datetime.date(2026, 1, 15), -2) == datetime.date(2025, 11, 15)


def test_erwerb_jeden_monat_oder_achtzehnmal(setup):
    s = setup
    org, anna = s["org"], s["people"]["Anna"]
    # In jedem der zwölf Monate bis zum Prüftag einmal
    for i in range(12):
        entry(org, anna, services.add_months(ON, -i) - datetime.timedelta(days=3))
    state = services.evaluate(anna, ON)
    acq = state["acquisition"]
    assert acq["member_12_months"] and acq["by_months"] and not acq["by_count"]
    assert acq["ok"] and acq["count"] == 12 and acq["gap_ok"]
    # Ein Monat fehlt: nicht mehr erfüllt, bis 18 Termine zusammenkommen
    ShootingEntry.objects.filter(membership=anna, date__month=5).delete()
    acq = services.evaluate(anna, ON)["acquisition"]
    assert not acq["by_months"] and not acq["ok"]
    for day in range(1, 8):
        entry(org, anna, datetime.date(2026, 10, day))
    acq = services.evaluate(anna, ON)["acquisition"]
    assert acq["count"] == 18 and acq["by_count"] and acq["ok"]


def test_nur_bestaetigte_erlaubnispflichtige_und_einmal_je_tag_und_disziplin(setup):
    s = setup
    org, bernd = s["org"], s["people"]["Bernd"]
    day = datetime.date(2026, 10, 3)
    entry(org, bernd, day)
    entry(org, bernd, day)  # doppelt am selben Tag, gleiche Disziplin: zählt einmal
    entry(org, bernd, day, discipline="Großkaliber-Pistole")  # andere Disziplin zählt
    entry(org, bernd, day, wclass="long", discipline="Luftgewehr", permit_required=False)
    entry(org, bernd, day, status=ShootingEntry.Status.REPORTED)
    entry(org, bernd, day, discipline="KK-Gewehr", status=ShootingEntry.Status.REJECTED)
    state = services.evaluate(bernd, ON)
    assert state["acquisition"]["count"] == 2
    assert state["pending"] == 1
    short = next(p for p in state["possession"] if p["weapon_class"] == "short")
    long_ = next(p for p in state["possession"] if p["weapon_class"] == "long")
    assert short["count"] == 2 and long_["count"] == 0


def test_mitglied_noch_keine_zwoelf_monate(setup):
    s = setup
    neu = make_member(s["org"], "Nina", "Neu", entry_date=datetime.date(2026, 3, 1))
    for i in range(12):
        entry(s["org"], neu, services.add_months(ON, -i) - datetime.timedelta(days=1))
    acq = services.evaluate(neu, ON)["acquisition"]
    assert acq["by_months"] and not acq["member_12_months"] and not acq["ok"]


def test_besitz_quartale_oder_sechsmal_je_jahr_getrennt_nach_waffenart(setup):
    s = setup
    org, carla = s["org"], s["people"]["Carla"]
    # Kurzwaffe: in jedem der acht Quartale einmal
    for i in range(8):
        entry(org, carla, services.add_months(ON, -3 * i) - datetime.timedelta(days=10))
    # Langwaffe: sechsmal je Zwölfmonatszeitraum, aber alles im Frühjahr
    for year in (2025, 2026):
        for day in range(1, 7):
            entry(org, carla, datetime.date(year, 4, day), wclass="long", discipline="KK-Gewehr")
    state = services.evaluate(carla, ON)
    short = next(p for p in state["possession"] if p["weapon_class"] == "short")
    long_ = next(p for p in state["possession"] if p["weapon_class"] == "long")
    assert short["by_quarters"] and short["ok"] and not short["by_six"]
    assert long_["by_six"] and long_["ok"] and not long_["by_quarters"]
    # Ein Termin der Langwaffe im älteren Jahr weniger: nicht mehr erfüllt
    ShootingEntry.objects.filter(
        membership=carla, weapon_class="long", date__year=2025
    ).first().delete()
    long_ = next(
        p for p in services.evaluate(carla, ON)["possession"] if p["weapon_class"] == "long"
    )
    assert not long_["ok"]


def test_luecke_ueber_vier_monate_wird_gemeldet(setup):
    s = setup
    org, carla = s["org"], s["people"]["Carla"]
    entry(org, carla, datetime.date(2026, 1, 10))
    entry(org, carla, datetime.date(2026, 7, 10))
    acq = services.evaluate(carla, ON)["acquisition"]
    assert acq["gap_ok"] is False and acq["longest_gap_days"] > 4 * 31


# --- Verwaltung --------------------------------------------------------------------------


def test_schiesstraining_anwesenheit_fuehrt_zum_schiessbuch(setup):
    s = setup
    anna, bernd = s["people"]["Anna"], s["people"]["Bernd"]
    today = services.today()
    created = ok(
        s["chef"].post(
            s["url"],
            {
                "date": today.isoformat(),
                "starts_at": "19:00",
                "ends_at": "21:30",
                "title": "Übungsabend Kurzwaffe",
                "kind": "practice",
                "leader": "Petra Probe",
                "shooting": True,
                "discipline": "Sportpistole",
                "weapon_class": "short",
                "caliber": ".22 lfB",
            },
            content_type=JSON,
        )
    )
    assert created["hours"] == 2.5 and created["shooting"] is True
    assert {r["membership"] for r in created["attendance"]} >= {anna.pk, bernd.pk}
    detail = ok(
        s["chef"].post(
            f"{s['url']}{created['id']}/attendance/",
            {"members": [anna.pk, bernd.pk], "present": True},
            content_type=JSON,
        )
    )
    assert {r["membership"] for r in detail["attendance"] if r["present"]} == {anna.pk, bernd.pk}
    entries = ShootingEntry.objects.filter(attendance__session_id=created["id"])
    assert entries.count() == 2
    assert set(entries.values_list("status", flat=True)) == {"confirmed"}
    # Disziplin geändert: Einträge ziehen mit
    ok(
        s["chef"].patch(
            f"{s['url']}{created['id']}/",
            {"discipline": "Großkaliber-Pistole", "caliber": "9 mm Luger"},
            content_type=JSON,
        )
    )
    assert set(entries.values_list("discipline", flat=True)) == {"Großkaliber-Pistole"}
    # Austragen nimmt den Schießbuch-Eintrag mit
    ok(
        s["chef"].post(
            f"{s['url']}{created['id']}/attendance/",
            {"membership": bernd.pk, "present": False},
            content_type=JSON,
        )
    )
    assert not ShootingEntry.objects.filter(membership=bernd).exists()
    # Eintrag aus dem Training lässt sich im Schießbuch nicht ändern oder löschen
    anna_entry = ShootingEntry.objects.get(membership=anna)
    resp = s["chef"].delete(f"{s['log']}{anna_entry.pk}/")
    assert resp.status_code == 400
    # Ohne Schießtermin: Einträge fallen weg
    ok(s["chef"].patch(f"{s['url']}{created['id']}/", {"shooting": False}, content_type=JSON))
    assert not ShootingEntry.objects.filter(membership=anna).exists()
    assert Attendance.objects.filter(session_id=created["id"]).count() == 1


def test_auswertung_und_dateien(setup):
    s = setup
    anna = s["people"]["Anna"]
    on = services.today()
    session = TrainingSession.objects.create(
        organization=s["org"], date=on, title="Training", starts_at=datetime.time(18)
    )
    services.set_present(session, anna, True, None)
    data = ok(s["chef"].get(f"{s['url']}report/"))
    assert data["total_sessions"] == 1 and data["total_attendances"] == 1
    assert data["members"][0]["membership"] == anna.pk and data["members"][0]["share"] == 100
    resp = s["chef"].get(f"{s['url']}report/?format=xlsx")
    assert resp.status_code == 200 and resp.content[:2] == b"PK"
    entry(s["org"], anna, on - datetime.timedelta(days=5))
    resp = s["chef"].get(f"{s['member_log'](anna)}pdf/?waffe=short")
    assert resp.status_code == 200 and resp.content[:4] == b"%PDF"
    assert s["chef"].get(f"{s['member_log'](anna)}pdf/?waffe=x").status_code == 400


def test_rechte_modul_und_fremder_verein(setup, orgs, api):
    s = setup
    resp = s["leser"].post(s["url"], {"date": "2026-11-20", "title": "x"}, content_type=JSON)
    assert resp.status_code == 403
    assert ok(s["leser"].get(s["url"]))["can_edit"] is False
    fremd = make_user("fremd-training@example.org")
    give_role(fremd, orgs["b"], permissions=["training.edit", "training.view"], name="Fremd")
    assert api(fremd).get(s["url"]).status_code == 404
    # Schießbuch nur mit Schießsport
    assert s["chef"].get(s["log"]).status_code == 200
    s["org"].enabled_modules = sorted(set(s["org"].enabled_modules) - {"shooting"})
    s["org"].save()
    assert s["chef"].get(s["log"]).status_code == 404
    created = ok(
        s["chef"].post(
            s["url"],
            {"date": "2026-11-20", "title": "Training", "shooting": True},
            content_type=JSON,
        )
    )
    assert created["shooting"] is False
    s["org"].enabled_modules = sorted(set(s["org"].enabled_modules) - {"training"})
    s["org"].save()
    assert s["chef"].get(s["url"]).status_code == 404


def test_untereinheit_eigene_trainings(setup, api):
    from members.models import DepartmentRoleHolder
    from organizations.models import DepartmentRole

    s = setup
    anna = s["people"]["Anna"]
    role = DepartmentRole.objects.create(
        department=s["jugend"], name="Jugendleitung", permissions=["training.edit"]
    )
    DepartmentRoleHolder.objects.create(
        organization=s["org"], membership=anna, role=role, valid_from=datetime.date(2020, 1, 1)
    )
    _client, _url, _access, user = s["portals"]["Anna"]
    dept = api(user)
    url = f"/api/depts/{s['jugend'].pk}/training/"
    created = ok(
        dept.post(url, {"date": "2026-11-20", "title": "Jugendtraining"}, content_type=JSON)
    )
    assert TrainingSession.objects.get(pk=created["id"]).department_id == s["jugend"].pk
    # Liste: nur Mitglieder der Jugend
    assert [r["membership"] for r in created["attendance"]] == [anna.pk]
    bernd = s["people"]["Bernd"]
    resp = dept.post(
        f"{url}{created['id']}/attendance/", {"membership": bernd.pk}, content_type=JSON
    )
    assert resp.status_code == 400
    # Verein sieht das Training der Jugend in seiner Liste nicht
    assert ok(s["chef"].get(f"{s['url']}?von=2026-01-01&bis=2026-12-31"))["sessions"] == []


# --- Mitgliederbereich und App ----------------------------------------------------------


def test_einchecken_per_qr_code(setup):
    s = setup
    today = services.today()
    session = ok(
        s["chef"].post(
            s["url"], {"date": today.isoformat(), "title": "Training"}, content_type=JSON
        )
    )
    sid = session["id"]
    client, url, access, _user = s["portals"]["Carla"]
    resp = client.post(f"{url}{sid}/checkin/", {"code": "1-abc"}, content_type=JSON)
    assert resp.status_code == 400  # nicht geöffnet
    ok(s["chef"].post(f"{s['url']}{sid}/checkin/", {"open": True}, content_type=JSON))
    code = ok(s["chef"].get(f"{s['url']}{sid}/checkin/"))
    assert code["session"] == sid and code["club"] == s["org"].pk
    overview = ok(client.get(url))
    assert [c["id"] for c in overview["checkin"]] == [sid]
    from portal.views import portal_summary

    summary = portal_summary(access)
    assert summary["training_enabled"] and summary["training_checkin"] == 1
    assert summary["shooting_log_enabled"] is True
    resp = client.post(f"{url}{sid}/checkin/", {"code": "1-falsch"}, content_type=JSON)
    assert resp.status_code == 400
    data = ok(client.post(f"{url}{sid}/checkin/", {"code": code["code"]}, content_type=JSON))
    assert data["checkin"][0]["present"] is True
    assert data["attendance"][0]["source"] == "code"
    # Schließen: Code gilt nicht mehr
    ok(s["chef"].post(f"{s['url']}{sid}/checkin/", {"open": False}, content_type=JSON))
    assert s["chef"].get(f"{s['url']}{sid}/checkin/").status_code == 404
    # Alter Termin: Einchecken lässt sich nicht öffnen
    old = TrainingSession.objects.create(
        organization=s["org"], date=today - datetime.timedelta(days=10), title="alt"
    )
    resp = s["chef"].post(f"{s['url']}{old.pk}/checkin/", {"open": True}, content_type=JSON)
    assert resp.status_code == 400


def test_schiesstermin_melden_und_bestaetigen(setup):
    s = setup
    client, url, _access, _user = s["portals"]["Bernd"]
    bernd = s["people"]["Bernd"]
    day = (services.today() - datetime.timedelta(days=3)).isoformat()
    data = ok(
        client.post(
            f"{url}shooting/",
            {
                "date": day,
                "discipline": "Großkaliber-Revolver",
                "weapon_class": "short",
                "caliber": ".357 Mag.",
                "place": "Schießstand Beispielstadt",
                "external": True,
                "own_weapon": True,
            },
            content_type=JSON,
        )
    )
    assert data["shooting"]["entries"][0]["status"] == "reported"
    assert data["shooting"]["evaluation"]["pending"] == 1
    future = (services.today() + datetime.timedelta(days=1)).isoformat()
    resp = client.post(
        f"{url}shooting/",
        {"date": future, "discipline": "x", "weapon_class": "short"},
        content_type=JSON,
    )
    assert resp.status_code == 400
    pending = ok(s["chef"].get(s["log"]))["reported"]
    assert [p["membership"] for p in pending] == [bernd.pk]
    eid = pending[0]["id"]
    ok(s["chef"].post(f"{s['log']}{eid}/confirm/", content_type=JSON))
    confirmed = ShootingEntry.objects.get(pk=eid)
    assert confirmed.status == "confirmed" and confirmed.confirmed_by_name
    # Bestätigte Einträge zieht das Mitglied nicht mehr zurück
    assert client.delete(f"{url}shooting/{eid}/").status_code == 403
    log = ok(s["chef"].get(s["member_log"](bernd)))
    assert log["evaluation"]["acquisition"]["count"] == 1
    assert log["evaluation"]["acquisition"]["external"] == 1
    # Vorstand trägt selbst ein (gleich bestätigt) und löscht wieder
    created = ok(
        s["chef"].post(
            s["member_log"](bernd),
            {"date": day, "discipline": "KK-Gewehr", "weapon_class": "long"},
            content_type=JSON,
        )
    )
    own = next(e for e in created["entries"] if e["discipline"] == "KK-Gewehr")
    assert own["status"] == "confirmed" and own["source"] == "board"
    assert s["chef"].delete(f"{s['log']}{own['id']}/").status_code == 204


def test_anwesenheit_aus_der_app_erfassen(setup):
    s = setup
    client, url, _access, _user = s["portals"]["Carla"]
    assert client.get(f"{url}manage/").status_code == 403
    give_role(
        s["portals"]["Carla"][3],
        s["org"],
        permissions=["training.edit", "training.view"],
        name="Übungsleitung",
    )
    data = ok(client.get(f"{url}manage/"))
    assert data["targets"] == [{"department": None, "name": s["org"].name}]
    today = services.today().isoformat()
    created = ok(
        client.post(f"{url}manage/", {"date": today, "title": "Training"}, content_type=JSON)
    )
    anna = s["people"]["Anna"]
    detail = ok(
        client.post(
            f"{url}manage/{created['id']}/attendance/",
            {"membership": anna.pk, "present": True},
            content_type=JSON,
        )
    )
    assert [r["membership"] for r in detail["attendance"] if r["present"]] == [anna.pk]
    ok(client.post(f"{url}manage/{created['id']}/checkin/", {"open": True}, content_type=JSON))
    assert ok(client.get(f"{url}manage/{created['id']}/checkin/"))["code"]


def test_loeschen_und_auskunft(setup):
    s = setup
    anna = s["people"]["Anna"]
    old = TrainingSession.objects.create(
        organization=s["org"], date=datetime.date(2014, 5, 1), title="alt"
    )
    services.set_present(old, anna, True, None)
    entry(s["org"], anna, datetime.date(2014, 5, 1))
    entry(s["org"], anna, datetime.date(2026, 5, 1))
    assert services.purge_due(datetime.date(2026, 11, 21)) >= 2
    assert not TrainingSession.objects.filter(pk=old.pk).exists()
    assert ShootingEntry.objects.filter(membership=anna).count() == 1
    services.forget_membership(anna)
    assert not ShootingEntry.objects.filter(membership=anna).exists()
