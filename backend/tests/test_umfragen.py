"""Umfragen und Meinungsbilder (konzepte/umfragen-meinungsbilder.md)."""

import datetime

import pytest
from django.utils import timezone

from surveys.models import Survey, SurveyAnswer, SurveyParticipation

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def ok(resp, code=(200, 201)):
    assert resp.status_code in ((code,) if isinstance(code, int) else code), resp.content
    return resp.json() if resp.content else None


def later(days=7):
    return (timezone.now() + datetime.timedelta(days=days)).isoformat()


@pytest.fixture
def setup(orgs, api):
    from portal.models import PortalAccess

    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "surveys", "events", "portal"})
    org.member_portal_enabled = True
    org.save()
    chef = make_user("schriftfuehrer@example.org")
    give_role(chef, org, permissions=["surveys.edit", "surveys.view"], name="Schriftführer")
    reader = make_user("beisitz@example.org")
    give_role(reader, org, permissions=["surveys.view"], name="Beisitz")
    people = {}
    portals = {}
    for first in ("Anna", "Bernd", "Carla", "Dieter"):
        m = make_member(org, first, "Muster", email=f"{first.lower()}@example.org")
        user = make_user(f"{first.lower()}-konto@example.org")
        access = PortalAccess.objects.create(organization=org, membership=m, user=user)
        people[first] = m
        portals[first] = (api(user), f"/api/portal/{access.pk}/surveys/")
    return {
        "org": org,
        "chef": api(chef),
        "reader": api(reader),
        "url": f"/api/orgs/{org.pk}/surveys/",
        "people": people,
        "portals": portals,
    }


def new_survey(s, questions, **extra):
    data = {"title": "Ausflug 2099", "closes_at": later(), "questions": questions, **extra}
    return ok(s["chef"].post(s["url"], data, content_type=JSON))


def start(s, survey):
    return ok(s["chef"].post(f"{s['url']}{survey['id']}/start/"))


def answer(s, who, survey, answers, code=(200, 201)):
    client, url = s["portals"][who]
    return ok(
        client.post(f"{url}{survey['id']}/answer/", {"answers": answers}, content_type=JSON),
        code,
    )


def mehr_leute(s, *names):
    """Weitere Mitglieder mit Mitgliederbereich (anonyme Ergebnisse brauchen fünf Antworten)."""
    from django.test import Client

    from portal.models import PortalAccess

    for first in names:
        m = make_member(s["org"], first, "Muster", email=f"{first.lower()}@example.org")
        user = make_user(f"{first.lower()}-konto@example.org")
        access = PortalAccess.objects.create(organization=s["org"], membership=m, user=user)
        client = Client()
        client.force_login(user)
        s["people"][first] = m
        s["portals"][first] = (client, f"/api/portal/{access.pk}/surveys/")


SINGLE = {
    "kind": "single",
    "text": "Wohin geht der Ausflug?",
    "options": [{"label": "Xanten"}, {"label": "Köln"}],
}


def test_anlegen_starten_und_beantworten_mit_namen(setup):
    s = setup
    survey = new_survey(s, [SINGLE, {"kind": "text", "text": "Wünsche?", "required": False}])
    assert survey["status"] == "draft" and len(survey["questions"]) == 2
    # Nur Lesen darf nicht anlegen
    assert s["reader"].post(s["url"], {"title": "X"}, content_type=JSON).status_code == 403
    # Entwurf ist im Mitgliederbereich unsichtbar
    client, url = s["portals"]["Anna"]
    assert ok(client.get(url))["surveys"] == []
    data = start(s, survey)
    assert data["status"] == "open" and data["invited"] == 4
    # Nach dem Start lassen sich Fragen nicht mehr ändern
    resp = s["chef"].patch(f"{s['url']}{survey['id']}/", {"questions": [SINGLE]}, content_type=JSON)
    assert resp.status_code == 400
    listed = ok(client.get(url))["surveys"]
    assert [x["title"] for x in listed] == ["Ausflug 2099"]
    row = listed[0]
    assert row["results"] is None and row["can_answer"]
    q1, q2 = row["questions"]
    xanten = q1["options"][0]["id"]
    # Pflichtfrage fehlt
    answer(s, "Anna", survey, [{"question": q2["id"], "text": "Bus"}], code=400)
    mine = answer(
        s,
        "Anna",
        survey,
        [{"question": q1["id"], "options": [xanten]}, {"question": q2["id"], "text": "Bus"}],
    )
    assert mine["answered"] and mine["can_change"]
    # Ergebnis nach der eigenen Antwort, Namen nur für die Verwaltung (Vorgabe)
    opt = mine["results"]["questions"][0]["options"][0]
    assert opt["count"] == 1 and opt["names"] == []
    # Ändern geht bei Umfragen mit Namen
    koeln = q1["options"][1]["id"]
    changed = answer(s, "Anna", survey, [{"question": q1["id"], "options": [koeln]}])
    assert changed["mine"][0]["options"] == [koeln]
    full = ok(s["chef"].get(f"{s['url']}{survey['id']}/"))
    assert full["participants"] == 1
    assert full["result"]["questions"][0]["options"][1]["names"] == ["Anna Muster"]
    assert "Bernd Muster" in full["pending"]
    # Zurückziehen
    client, url = s["portals"]["Anna"]
    ok(client.delete(f"{url}{survey['id']}/answer/"))
    assert SurveyParticipation.objects.filter(survey_id=survey["id"]).count() == 0


def test_anonym_nicht_aenderbar_und_erst_ab_fuenf(setup):
    s = setup
    mehr_leute(s, "Emil")
    yesno = {"kind": "yesno", "text": "Neue Uniformjacken bestellen?"}
    # Anonym: Ergebnis erst nach dem Ende (Gesamtaudit 15.11., FF-22 (a))
    survey = new_survey(s, [yesno], names="anonymous", results="after_close")
    start(s, survey)
    client, url = s["portals"]["Anna"]
    q = ok(client.get(url))["surveys"][0]["questions"][0]
    answer(s, "Anna", survey, [{"question": q["id"], "value": "yes"}])
    # Nicht änderbar
    answer(s, "Anna", survey, [{"question": q["id"], "value": "no"}], code=400)
    data = answer(s, "Bernd", survey, [{"question": q["id"], "value": "no"}])
    assert data["results"] is None and data["mine"] is None and not data["can_answer"]
    # Auch die Verwaltung sieht während der Umfrage nichts, auch nicht mit genug Antworten
    full = ok(s["chef"].get(f"{s['url']}{survey['id']}/"))
    assert full["result"]["hidden"] and "pending" not in full
    data = answer(s, "Carla", survey, [{"question": q["id"], "value": "yes"}])
    assert data["results"] is None
    full = ok(s["chef"].get(f"{s['url']}{survey['id']}/"))
    assert full["result"]["hidden"] and full["result"]["until_close"]
    # Keine Verbindung zwischen Teilnahme und Antwort, kein Zeitpunkt
    assert not SurveyAnswer.objects.filter(participation__isnull=False).exists()
    assert not SurveyParticipation.objects.filter(answered_at__isnull=False).exists()
    # Namen lassen sich nach der ersten Antwort nicht mehr lockern
    resp = s["chef"].patch(f"{s['url']}{survey['id']}/", {"names": "open"}, content_type=JSON)
    assert resp.status_code == 400
    # Die Verwaltung trägt bei anonymen Umfragen nichts ein
    resp = s["chef"].post(
        f"{s['url']}{survey['id']}/answers/",
        {"membership": s["people"]["Dieter"].pk, "answers": []},
        content_type=JSON,
    )
    assert resp.status_code == 400
    # Nach dem Ende: Ergebnis ab fünf Antworten, ohne Namen (Gesamtaudit 19.11., S-10)
    answer(s, "Dieter", survey, [{"question": q["id"], "value": "yes"}])
    answer(s, "Emil", survey, [{"question": q["id"], "value": "yes"}])
    ok(s["chef"].post(f"{s['url']}{survey['id']}/close/"))
    full = ok(s["chef"].get(f"{s['url']}{survey['id']}/"))
    values = full["result"]["questions"][0]["values"]
    assert values["yes"]["count"] == 4 and values["no"]["count"] == 1
    assert values["yes"]["names"] == []
    client, url = s["portals"]["Anna"]
    mine = next(x for x in ok(client.get(url))["surveys"] if x["id"] == survey["id"])
    assert mine["results"]["questions"][0]["values"]["no"]["count"] == 1


def test_anonym_mit_vier_antworten_bleibt_verborgen(setup):
    """Gesamtaudit 19.11., S-10: Bei drei oder vier Antworten ließe sich auf Einzelne schließen."""
    s = setup
    yesno = {"kind": "yesno", "text": "Neue Uniformjacken bestellen?"}
    survey = new_survey(s, [yesno], names="anonymous", results="after_close")
    start(s, survey)
    client, url = s["portals"]["Anna"]
    q = ok(client.get(url))["surveys"][0]["questions"][0]
    for who in ("Anna", "Bernd", "Carla", "Dieter"):
        answer(s, who, survey, [{"question": q["id"], "value": "yes"}])
    ok(s["chef"].post(f"{s['url']}{survey['id']}/close/"))
    full = ok(s["chef"].get(f"{s['url']}{survey['id']}/"))
    assert full["result"]["hidden"] and not full["result"]["until_close"]
    assert full["result"]["participants"] == 4 and full["result"]["questions"] == []
    mine = next(x for x in ok(client.get(url))["surveys"] if x["id"] == survey["id"])
    assert mine["results"] is None or mine["results"].get("hidden")


def test_platzgrenze_wer_faehrt_mit(setup):
    s = setup
    q = {
        "kind": "single",
        "text": "Wie fährst du?",
        "options": [{"label": "Bus", "capacity": 1}, {"label": "Auto"}],
    }
    survey = new_survey(s, [q], names="open")
    start(s, survey)
    client, url = s["portals"]["Anna"]
    row = ok(client.get(url))["surveys"][0]["questions"][0]
    bus, auto = row["options"][0]["id"], row["options"][1]["id"]
    answer(s, "Anna", survey, [{"question": row["id"], "options": [bus]}])
    answer(s, "Bernd", survey, [{"question": row["id"], "options": [bus]}], code=400)
    data = answer(s, "Bernd", survey, [{"question": row["id"], "options": [auto]}])
    # Offen: Befragte sehen Namen
    assert data["results"]["questions"][0]["options"][0]["names"] == ["Anna Muster"]
    # Anna darf ihren eigenen Platz behalten (zählt beim Ändern nicht doppelt)
    answer(s, "Anna", survey, [{"question": row["id"], "options": [bus]}])


def test_terminfindung_und_termin_daraus(setup):
    from events.models import EventResponse

    s = setup
    a = timezone.now() + datetime.timedelta(days=10)
    dates = {
        "kind": "dates",
        "text": "Wann passt die Zugversammlung?",
        "options": [
            {"starts_at": a.isoformat()},
            {"starts_at": (a + datetime.timedelta(days=2)).isoformat()},
        ],
    }
    survey = new_survey(s, [dates], names="open", title="Zugversammlung")
    start(s, survey)
    client, url = s["portals"]["Anna"]
    q = ok(client.get(url))["surveys"][0]["questions"][0]
    first, second = (str(o["id"]) for o in q["options"])
    answer(s, "Anna", survey, [{"question": q["id"], "dates": {first: "yes", second: "maybe"}}])
    answer(s, "Bernd", survey, [{"question": q["id"], "dates": {first: "yes", second: "no"}}])
    data = answer(s, "Carla", survey, [{"question": q["id"], "dates": {first: "no", second: "no"}}])
    result = data["results"]["questions"][0]
    assert [o["count"] for o in result["options"]] == [2, 0]
    assert result["options"][1]["maybe"] == 1 and result["best"] == [int(first)]
    # Termin daraus anlegen braucht Recht auf Termine
    resp = s["chef"].post(f"{s['url']}{survey['id']}/event/", {"option": int(first)})
    assert resp.status_code == 403
    boss = make_user("vorstand-termine@example.org")
    give_role(boss, s["org"], permissions=["surveys.edit", "events.edit"], name="Vorsitz")
    from django.test import Client

    c = Client()
    c.force_login(boss)
    full = ok(c.post(f"{s['url']}{survey['id']}/event/", {"option": int(first)}, content_type=JSON))
    assert full["follow_event"]
    # Wer „Ja“ gesagt hat, übernimmt die Zusage mit einem Tipp
    row = ok(client.get(f"{url}{survey['id']}/"))
    assert row["follow_event"]["said_yes"] and row["follow_event"]["response"] is None
    row = ok(client.post(f"{url}{survey['id']}/follow/"))
    assert row["follow_event"]["response"] == "yes"
    assert EventResponse.objects.get(membership=s["people"]["Anna"]).status == "yes"


def test_essenswahl_am_termin_nur_zugesagte(setup):
    from events.models import Event, EventResponse
    from events.rsvp import save_response

    s = setup
    org = s["org"]
    start_at = timezone.now() + datetime.timedelta(days=20)
    event = Event.objects.create(
        organization=org,
        title="Schützenball",
        starts_at=start_at,
        ends_at=start_at + datetime.timedelta(hours=5),
        rsvp_enabled=True,
        rsvp_guests=True,
    )
    anna, bernd = s["people"]["Anna"], s["people"]["Bernd"]
    save_response(event, anna, status="yes", guests=1, note="", source="member", user=None)
    save_response(event, bernd, status="yes", guests=0, note="", source="member", user=None)
    meal = {
        "kind": "quantity",
        "text": "Was möchtest du essen?",
        "options": [{"label": "Schnitzel"}, {"label": "Lachs"}, {"label": "Vegetarisch"}],
    }
    survey = new_survey(
        s, [meal], title="Essenswahl Schützenball", event=event.pk, audience="event_yes"
    )
    data = start(s, survey)
    assert data["invited"] == 2
    client, url = s["portals"]["Anna"]
    row = ok(client.get(url))["surveys"][0]
    q = row["questions"][0]
    assert q["max_total"] == 2 and row["event"]["title"] == "Schützenball"
    schnitzel, lachs = str(q["options"][0]["id"]), str(q["options"][1]["id"])
    answer(s, "Anna", survey, [{"question": q["id"], "quantities": {schnitzel: 2, lachs: 1}}], 400)
    answer(s, "Anna", survey, [{"question": q["id"], "quantities": {schnitzel: 1, lachs: 1}}])
    answer(s, "Bernd", survey, [{"question": q["id"], "quantities": {schnitzel: 1}}])
    # Carla hat nicht zugesagt
    c_client, c_url = s["portals"]["Carla"]
    assert ok(c_client.get(c_url))["surveys"] == []
    answer(s, "Carla", survey, [{"question": q["id"], "quantities": {schnitzel: 1}}], 404)
    # Absage: Antwort mit Namen entfällt
    save_response(event, bernd, status="no", guests=0, note="", source="member", user=None)
    assert not SurveyParticipation.objects.filter(membership=bernd).exists()
    full = ok(s["chef"].get(f"{s['url']}{survey['id']}/"))
    assert [o["count"] for o in full["result"]["questions"][0]["options"]] == [1, 1, 0]
    assert EventResponse.objects.filter(event=event).count() == 2
    # Export für den Wirt
    pdf = s["chef"].get(f"{s['url']}{survey['id']}/export/")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
    xlsx = s["chef"].get(f"{s['url']}{survey['id']}/export/?datei=xlsx")
    assert xlsx.status_code == 200


def test_mail_link_bescheid_erinnerung_ende_aufraeumen(setup, api, mailoutbox):
    from surveys import link, notify, services

    s = setup
    org = s["org"]
    ohne_zugang = make_member(org, "Erika", "Beispiel", email="erika@example.org")
    survey = new_survey(s, [SINGLE], remind_days=2)
    start(s, survey)
    sent = notify.send(survey["id"], notify.START)
    # Ohne App mit Push: Mail an alle fünf
    assert sent == 5 and len(mailoutbox) == 5
    mail = next(m for m in mailoutbox if "erika@example.org" in m.to)
    assert "/umfrage/" in mail.body
    token = link.token(survey["id"], ohne_zugang.pk)
    anon = api(make_user("niemand@example.org"))
    anon.logout()
    data = ok(anon.get(f"/api/public/survey/{token}/"))
    q = data["survey"]["questions"][0]
    ok(
        anon.post(
            f"/api/public/survey/{token}/",
            {"answers": [{"question": q["id"], "options": [q["options"][0]["id"]]}]},
            content_type=JSON,
        )
    )
    assert SurveyParticipation.objects.get(membership=ohne_zugang).source == "link"
    assert anon.get("/api/public/survey/kaputt/").status_code == 404
    # Erinnerung zwei Tage vor dem Ende an alle ohne Antwort
    obj = Survey.objects.get(pk=survey["id"])
    mailoutbox.clear()
    assert notify.send_reminders(obj.closes_at - datetime.timedelta(days=3)) == 0
    assert notify.send_reminders(obj.closes_at - datetime.timedelta(days=1)) == 4
    assert notify.send_reminders(obj.closes_at - datetime.timedelta(hours=1)) == 0
    # Ende
    assert services.close_due(obj.closes_at + datetime.timedelta(minutes=1)) == 1
    obj.refresh_from_db()
    assert obj.status == "closed" and obj.invited == 5
    client, url = s["portals"]["Anna"]
    row = ok(client.get(url))["surveys"][0]
    assert row["status"] == "closed" and not row["can_answer"] and row["results"]
    # Nach der Frist: Antworten weg, Zahlen bleiben
    assert services.purge_due(obj.closed_at + datetime.timedelta(days=30 * 13)) == 1
    obj.refresh_from_db()
    assert obj.purged_at and not obj.participations.exists() and not obj.answers.exists()
    full = ok(s["chef"].get(f"{s['url']}{survey['id']}/"))
    assert full["result"]["archived"] and full["result"]["participants"] == 1


def test_zielgruppe_vorstand_untereinheit_und_modul(orgs, api):
    from members.models import DepartmentRoleHolder
    from organizations.models import Department, DepartmentRole
    from portal.models import PortalAccess

    org = orgs["a"]
    user = make_user("vorstand-umfrage@example.org")
    give_role(user, org, permissions=["surveys.edit"], name="Geschäftsführer")
    client = api(user)
    org.enabled_modules = sorted({*org.enabled_modules} - {"surveys"})
    org.save()
    assert client.get(f"/api/orgs/{org.pk}/surveys/").status_code == 404
    org.enabled_modules = sorted({*org.enabled_modules, "members", "surveys", "portal"})
    org.department_access_enabled = True
    org.member_portal_enabled = True
    org.save()
    zug = Department.objects.create(
        self_managed=True, organization=org, name="Jägerzug", short_name="Jäger"
    )
    andere = Department.objects.create(
        self_managed=True, organization=org, name="Grenadiere", short_name="Gren"
    )
    max_ = make_member(org, "Max", "Muster", departments=[zug])
    moritz = make_member(org, "Moritz", "Muster", departments=[zug])
    make_member(org, "Otto", "Muster", departments=[andere])
    role = DepartmentRole.objects.create(
        department=zug, name="Zugführer", permissions=["surveys.edit"]
    )
    DepartmentRoleHolder.objects.create(
        organization=org, membership=max_, role=role, valid_from=datetime.date(2020, 1, 1)
    )
    zf = make_user("zugfuehrer-umfrage@example.org")
    PortalAccess.objects.create(organization=org, membership=max_, user=zf)
    c = api(zf)
    url = f"/api/depts/{zug.pk}/surveys/"
    survey = ok(
        c.post(
            url,
            {"title": "Zugfahrt", "closes_at": later(), "questions": [SINGLE]},
            content_type=JSON,
        )
    )
    assert Survey.objects.get(pk=survey["id"]).department_id == zug.pk
    data = ok(c.post(f"{url}{survey['id']}/start/"))
    assert data["invited"] == 2
    assert ok(client.get(f"/api/orgs/{org.pk}/surveys/")) == []
    assert c.get(f"/api/depts/{andere.pk}/surveys/").status_code == 404
    # Ausgewählte Personen
    count = ok(
        client.post(
            f"/api/orgs/{org.pk}/surveys/count/",
            {"audience": "persons", "persons": [moritz.pk]},
            content_type=JSON,
        )
    )
    assert count["count"] == 1
    # Ganze Mitgliedschaft nach Untereinheit gefiltert
    count = ok(
        client.post(
            f"/api/orgs/{org.pk}/surveys/count/",
            {"audience": "members", "filters": {"departments": [andere.pk]}},
            content_type=JSON,
        )
    )
    assert count["count"] == 1


def test_eintragen_durch_verwaltung_auskunft_und_loeschen(setup):
    from members.auskunft import build
    from members.workflows import purge_membership

    s = setup
    survey = new_survey(s, [SINGLE], names="managers")
    start(s, survey)
    full = ok(s["chef"].get(f"{s['url']}{survey['id']}/"))
    q = full["questions"][0]
    dieter = s["people"]["Dieter"]
    ok(
        s["chef"].post(
            f"{s['url']}{survey['id']}/answers/",
            {
                "membership": dieter.pk,
                "answers": [{"question": q["id"], "options": [q["options"][0]["id"]]}],
            },
            content_type=JSON,
        )
    )
    part = SurveyParticipation.objects.get(membership=dieter)
    assert part.source == "board"
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(build(dieter, s["org"]))) as z:
        names = [n for n in z.namelist() if n.endswith("umfragen.json")]
        assert names and "Xanten" in z.read(names[0]).decode()
    purge_membership(dieter)
    part.refresh_from_db()
    assert part.membership_id is None
    # Gezählt bleibt die Antwort
    full = ok(s["chef"].get(f"{s['url']}{survey['id']}/"))
    assert full["participants"] == 1
    # Kopieren und Löschen
    copy = ok(s["chef"].post(f"{s['url']}{survey['id']}/copy/"))
    assert copy["status"] == "draft" and len(copy["questions"]) == 1
    assert s["chef"].delete(f"{s['url']}{survey['id']}/").status_code == 400
    ok(s["chef"].post(f"{s['url']}{survey['id']}/close/"))
    assert s["chef"].delete(f"{s['url']}{survey['id']}/").status_code == 204


def test_offene_umfragen_im_zugang(setup):
    s = setup
    survey = new_survey(s, [SINGLE])
    start(s, survey)
    client, url = s["portals"]["Anna"]
    me = ok(client.get("/api/me/contexts/"))
    row = next(r for r in me["portal"] if r.get("surveys_enabled"))
    assert row["surveys_open"] == 1


def test_umstellen_auf_anonym_loest_die_zuordnung(setup):
    """Sicherheitsprüfung 26.11. B-M10: Schon gegebene Antworten hängen danach an keiner Person."""
    from surveys.models import SurveyAnswer

    s = setup
    survey = new_survey(s, [SINGLE])
    start(s, survey)
    client, url = s["portals"]["Anna"]
    q1 = ok(client.get(url))["surveys"][0]["questions"][0]
    answer(s, "Anna", survey, [{"question": q1["id"], "options": [q1["options"][0]["id"]]}])
    assert SurveyAnswer.objects.filter(survey_id=survey["id"], participation__isnull=False).exists()
    ok(s["chef"].patch(f"{s['url']}{survey['id']}/", {"names": "anonymous"}, content_type=JSON))
    answers = SurveyAnswer.objects.filter(survey_id=survey["id"])
    assert answers.count() == 1 and not answers.filter(participation__isnull=False).exists()
    # Die Teilnahme bleibt (wer geantwortet hat), nur nicht mehr, was
    assert SurveyParticipation.objects.filter(survey_id=survey["id"]).count() == 1
