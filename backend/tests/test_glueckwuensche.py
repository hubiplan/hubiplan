"""Glückwünsche zu Geburtstag und Jubiläum: Einstellung, Entwürfe, Versand, Widerspruch.

Alles erfunden; Daten relativ zu heute, damit der Test an jedem Tag gleich läuft.
"""
# ruff: noqa: F811  (Fixtures aus test_m12_events als Parameter)

import datetime

import pytest
from django.core import mail as djmail
from django.utils import timezone

from circulars.models import Circular
from greetings import services
from greetings.models import GreetingBatch, GreetingSettings
from members.models import ContactDetails

from .factories import make_member
from .test_m12_events import JSON, cal, member_with_access  # noqa: F401  (Fixtures)

pytestmark = pytest.mark.django_db
TODAY = datetime.date.today()


def url(org) -> str:
    return f"/api/orgs/{org.pk}/greetings/"


def born(days_from_now: int, age: int) -> datetime.date:
    day = TODAY + datetime.timedelta(days=days_from_now)
    return day.replace(year=day.year - age)


def turn_on(c, org, **data):
    payload = {"birthdays": "round", "round_ages": "50, 60", "every_year_from": 80, **data}
    resp = c.put(f"{url(org)}settings/", payload, content_type=JSON)
    assert resp.status_code == 200, resp.json()
    return resp.json()


@pytest.fixture
def people(cal):
    club = cal["a"]
    return {
        # in drei Tagen 50: bekommt einen Glückwunsch
        "anna": make_member(club, "Anna", "Adler", "anna@example.org", birth_date=born(3, 50)),
        # in drei Tagen 51: kein besonderer Geburtstag
        "bernd": make_member(club, "Bernd", "Berg", "bernd@example.org", birth_date=born(3, 51)),
        # heute 85: ab 80 jedes Jahr, ohne E-Mail ein Brief
        "clara": make_member(club, "Clara", "Christ", birth_date=born(0, 85)),
        # in 20 Tagen 60: noch kein Entwurf, aber in der Vorschau
        "dora": make_member(club, "Dora", "Dachs", "dora@example.org", birth_date=born(20, 60)),
    }


def test_aus_ohne_einstellung(cal, board_a, people, api):
    data = api(board_a).get(url(cal["a"])).json()
    assert data["settings"]["active"] is False
    assert data["batches"] == [] and data["upcoming"] == []
    assert "{Alter}" in data["settings"]["birthday_body"]  # Vorgabetext


def test_entwuerfe_vorschau_und_auswahl(cal, board_a, people, api):
    c = api(board_a)
    turn_on(c, cal["a"])
    data = c.get(url(cal["a"])).json()
    names = {(u["name"], u["age"]) for u in data["upcoming"]}
    assert names == {("Anna Adler", 50), ("Clara Christ", 85), ("Dora Dachs", 60)}
    # Entwürfe nur für die nächsten 7 Tage: heute (Clara) und in drei Tagen (Anna)
    assert sorted((b["date"], b["count"], b["status"]) for b in data["batches"]) == [
        (TODAY.isoformat(), 1, "draft"),
        ((TODAY + datetime.timedelta(days=3)).isoformat(), 1, "draft"),
    ]
    circular = Circular.objects.get(pk=data["batches"][0]["circular"])
    assert circular.kind == Circular.Kind.GREETING
    # Nicht in der Liste der Rundschreiben und dort nicht änderbar
    listed = c.get(f"/api/orgs/{cal['a'].pk}/circulars/").json()
    assert all(i["kind"] != "greeting" for i in listed)
    resp = c.patch(
        f"/api/orgs/{cal['a'].pk}/circulars/{circular.pk}/", {"subject": "x"}, content_type=JSON
    )
    assert resp.status_code == 400
    resp = c.post(
        f"/api/orgs/{cal['a'].pk}/circulars/",
        {"kind": "greeting", "subject": "x"},
        content_type=JSON,
    )
    assert resp.status_code == 400
    # Brief an Clara ohne E-Mail lässt sich vorher drucken
    clara = next(b for b in data["batches"] if b["date"] == TODAY.isoformat())
    pdf = c.get(clara["letters_url"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_versand_am_tag_mit_alter(
    cal, board_a, people, api, settings, django_capture_on_commit_callbacks
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    c = api(board_a)
    # E-Mail ist verschlüsselt: nur über save() schreiben
    rows = list(ContactDetails.objects.filter(person=people["clara"].person))
    assert rows
    for details in rows:
        details.email = "clara@example.org"
        details.save()
    turn_on(c, cal["a"], send_hour=6)
    services.prepare(cal["a"], TODAY)
    noon = timezone.make_aware(datetime.datetime.combine(TODAY, datetime.time(12)))
    with django_capture_on_commit_callbacks(execute=True):
        assert services.send_due(cal["a"], noon) == 1
    mails = [m for m in djmail.outbox if m.to == ["clara@example.org"]]
    assert len(mails) == 1
    assert "85. Geburtstag" in mails[0].body
    assert "Abmelden" not in mails[0].body  # keine Abmeldezeile wie bei Informationen
    batch = GreetingBatch.objects.get(organization=cal["a"], date=TODAY)
    assert batch.circular.status != Circular.Status.DRAFT
    # Ein zweiter Lauf schickt nichts doppelt
    with django_capture_on_commit_callbacks(execute=True):
        assert services.send_due(cal["a"], noon) == 0


def test_freigabe_und_vor_der_uhrzeit_nichts_von_selbst(cal, board_a, people, api):
    c = api(board_a)
    turn_on(c, cal["a"], approval=True)
    early = timezone.make_aware(datetime.datetime.combine(TODAY, datetime.time(23)))
    assert services.send_due(cal["a"], early) == 0
    turn_on(c, cal["a"], approval=False, send_hour=20)
    morning = timezone.make_aware(datetime.datetime.combine(TODAY, datetime.time(7)))
    assert services.send_due(cal["a"], morning) == 0


def test_auslassen_und_wieder_vorsehen(cal, board_a, people, api):
    c = api(board_a)
    turn_on(c, cal["a"])
    batch = next(b for b in c.get(url(cal["a"])).json()["batches"] if b["count"])
    assert c.post(f"{url(cal['a'])}{batch['id']}/skip/").status_code == 200
    assert not Circular.objects.filter(pk=batch["circular"]).exists()
    again = {b["id"]: b for b in c.get(url(cal["a"])).json()["batches"]}
    assert again[batch["id"]]["status"] == "skipped"  # kommt nicht wieder
    assert c.post(f"{url(cal['a'])}{batch['id']}/restore/").status_code == 200
    statuses = {b["date"]: b["status"] for b in c.get(url(cal["a"])).json()["batches"]}
    assert statuses[batch["date"]] == "draft"


def test_widerspruch_im_mitgliederbereich(cal, board_a, api):
    m, user, access = member_with_access(cal["a"], "Erika")
    m.person.birth_date = born(2, 60)
    m.person.save()
    resp = api(user).put(
        f"/api/portal/{access.pk}/circulars/settings/",
        {"greetings_opt_out": True},
        content_type=JSON,
    )
    assert resp.json()["greetings_opt_out"] is True
    assert resp.json()["info_opt_out"] is False  # das andere bleibt unberührt
    c = api(board_a)
    turn_on(c, cal["a"])
    data = c.get(url(cal["a"])).json()
    assert [u["opted_out"] for u in data["upcoming"]] == [True]
    batch = data["batches"][0]
    rows = c.get(f"/api/orgs/{cal['a'].pk}/circulars/{batch['circular']}/recipients/").json()
    assert rows["items"][0]["channel"] is None
    assert rows["items"][0]["note"] == "möchte keine Glückwünsche"
    # Ohne Empfänger wird der Tag ausgelassen statt jede Stunde neu versucht
    b = GreetingBatch.objects.get(pk=batch["id"])
    assert services.send(b, None) == {}
    b.refresh_from_db()
    assert b.skipped_at and b.note == services.NOBODY


def test_einstellung_aus_entfernt_entwuerfe(cal, board_a, people, api):
    c = api(board_a)
    turn_on(c, cal["a"])
    assert Circular.objects.filter(kind=Circular.Kind.GREETING).count() == 2
    turn_on(c, cal["a"], birthdays="off")
    assert Circular.objects.filter(kind=Circular.Kind.GREETING).count() == 0
    assert GreetingSettings.objects.get(organization=cal["a"]).active is False


def test_pruefungen_und_rechte(cal, board_a, people, api):
    c = api(board_a)
    bad = c.put(
        f"{url(cal['a'])}settings/", {"birthday_body": "Hallo {Spitzname}"}, content_type=JSON
    )
    assert bad.status_code == 400
    assert (
        c.put(f"{url(cal['a'])}settings/", {"lead_days": 99}, content_type=JSON).status_code == 400
    )
    assert (
        c.put(f"{url(cal['a'])}settings/", {"send_hour": 3}, content_type=JSON).status_code == 400
    )
    m, user, access = member_with_access(cal["a"], "Fritz")
    assert api(user).get(url(cal["a"])).status_code == 404
    # Dachverband hat keine Glückwünsche
    assert c.get(url(cal["federation"])).status_code == 404


def test_besondere_geburtstage():
    s = GreetingSettings(birthdays="round", round_ages="18; 50, x, 60", every_year_from=80)
    assert services.parse_ages(s.round_ages) == [18, 50, 60]
    assert [a for a in (17, 18, 50, 51, 79, 80, 93) if services.wants_age(s, a)] == [18, 50, 80, 93]
    s.every_year_from = 0
    assert not services.wants_age(s, 93)
    s.birthdays = "all"
    assert services.wants_age(s, 1)
