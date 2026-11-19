"""Hilfe: Ansprechpartner und Hinweise der Einheit, abgehakte erste Schritte."""

from __future__ import annotations

import pytest

from access.catalog import MEMBERS_VIEW, ORG_EDIT, ROLES_MANAGE, ROLES_PREVIEW
from access.models import Role
from core.tenancy import tenant_context
from organizations.help_views import clean_contacts, clean_notes

from .factories import audit_with, give_role, make_user

JSON = "application/json"
pytestmark = pytest.mark.django_db


def test_bereinigen():
    assert clean_contacts("x") == []
    assert clean_contacts([{"name": " Anna ", "email": "a@example.org", "x": 1}, {"name": ""}]) == [
        {"name": "Anna", "hint": "", "email": "a@example.org"}
    ]
    assert clean_contacts([{"name": str(i)} for i in range(20)])[-1]["name"] == "9"
    raw = {"guide.a": " x ", "page.b": "y", "guide.c": " ", 3: "z"}
    assert clean_notes(raw) == {"guide.a": "x"}


def test_lesen_jede_rolle_aendern_nur_mit_recht(orgs, api):
    org = orgs["a"]
    leser = make_user("leser@example.org")
    give_role(leser, org, [MEMBERS_VIEW], name="Leser")
    chef = make_user("chef@example.org")
    give_role(chef, org, [ORG_EDIT, ROLES_MANAGE], name="Geschäftsführung")
    fremd = make_user("fremd@example.org")
    give_role(fremd, orgs["b"], [ORG_EDIT])
    url = f"/api/orgs/{org.pk}/help/"

    state = api(leser).get(url).json()
    assert state["contacts"] == [] and state["contacts_from"] is None
    assert state["can_edit"] is False
    assert state["admin_roles"] == ["Geschäftsführung"]
    assert MEMBERS_VIEW in state["rights"] and state["rights"][MEMBERS_VIEW]

    assert api(fremd).get(url).status_code == 404
    contacts = [{"name": "Anna Beispiel", "hint": "Mitglieder", "email": "anna@example.org"}]
    assert api(leser).patch(url, {"contacts": contacts}, content_type=JSON).status_code == 403

    res = api(chef).patch(url, {"contacts": contacts}, content_type=JSON)
    assert res.status_code == 200
    assert res.json()["contacts"] == contacts
    assert res.json()["contacts_from"] == {"name": org.display_name, "own": True}
    assert api(leser).get(url).json()["contacts"] == contacts

    bad = api(chef).patch(url, {"contacts": [{"name": "X", "email": "kein"}]}, content_type=JSON)
    assert bad.status_code == 400
    with tenant_context(org.pk):
        assert len(audit_with("Ansprechpartner für Fragen zu HUBIplan", organization=org)) == 1


def test_ansprechpartner_und_hinweise_von_oben(orgs, api):
    fed, org = orgs["federation"], orgs["a"]
    fed.help_contacts = [{"name": "Bund-Hilfe", "hint": "", "email": ""}]
    fed.help_notes = {"guide.member_new": "Bitte Formular B nutzen."}
    fed.save()
    chef = make_user("chef@example.org")
    give_role(chef, org, [ORG_EDIT])
    client = api(chef)

    state = client.get(f"/api/orgs/{org.pk}/help/").json()
    assert state["contacts"][0]["name"] == "Bund-Hilfe"
    assert state["contacts_from"] == {"name": fed.display_name, "own": False}
    assert state["own_contacts"] == []

    url = f"/api/orgs/{org.pk}/help/notes/guide.member_new/"
    res = client.put(url, {"text": "Bei uns: Kassierer fragen."}, content_type=JSON)
    assert res.status_code == 200
    notes = res.json()["notes"]["guide.member_new"]
    assert [(n["text"], n["own"]) for n in notes] == [
        ("Bitte Formular B nutzen.", False),
        ("Bei uns: Kassierer fragen.", True),
    ]
    # Leerer Text entfernt nur den eigenen Hinweis
    res = client.put(url, {"text": " "}, content_type=JSON)
    assert [n["own"] for n in res.json()["notes"]["guide.member_new"]] == [False]
    bad = client.put(f"/api/orgs/{org.pk}/help/notes/page.x/", {"text": "x"}, content_type=JSON)
    assert bad.status_code == 403


def test_hinweise_nur_mit_recht(orgs, api):
    org = orgs["a"]
    leser = make_user("leser@example.org")
    give_role(leser, org, [MEMBERS_VIEW])
    url = f"/api/orgs/{org.pk}/help/notes/guide.member_new/"
    assert api(leser).put(url, {"text": "x"}, content_type=JSON).status_code == 403


def test_erste_schritte_abhaken(orgs, api):
    user = make_user("neu@example.org")
    client = api(user)
    assert client.get("/api/me/help/").json() == {"help_done": []}
    assert client.post("/api/me/help/start.profile/").json() == {"help_done": ["start.profile"]}
    client.post("/api/me/help/start.password/")
    assert client.get("/api/me/help/").json()["help_done"] == ["start.password", "start.profile"]
    assert client.delete("/api/me/help/start.profile/").json() == {"help_done": ["start.password"]}
    assert client.post("/api/me/help/Böse Sache/").status_code == 404
    assert client.delete("/api/me/help/").json() == {"help_done": []}
    user.refresh_from_db()
    assert user.help_done is None


def test_abhaken_in_ansicht_als_rolle_gesperrt(orgs, api):
    org = orgs["a"]
    chef = make_user("chef@example.org")
    give_role(chef, org, [MEMBERS_VIEW, ROLES_PREVIEW], name="Chef")
    rolle = Role.objects.create(organization=org, name="Leser", permissions=[MEMBERS_VIEW])
    client = api(chef)
    ok = client.post(f"/api/orgs/{org.pk}/ansicht/", {"role": rolle.pk}, content_type=JSON)
    assert ok.status_code == 200
    assert client.post("/api/me/help/start.profile/").status_code == 403
    assert client.get(f"/api/orgs/{org.pk}/help/").status_code == 200


def test_rueckmeldung_ohne_person_und_einheit(orgs, api):
    from access.catalog import PLATFORM_MANAGE
    from organizations.models import HelpFeedback, Organization

    mitglied = make_user("mitglied@example.org")
    give_role(mitglied, orgs["a"], [MEMBERS_VIEW], name="Leser")
    betrieb = make_user("betrieb@example.org")
    give_role(betrieb, Organization.platform(), [PLATFORM_MANAGE], name="Betrieb")
    url = "/api/help/feedback/"

    ja = {"key": "guide.password", "language": "de", "helpful": True, "comment": "egal"}
    assert api(mitglied).post(url, ja, content_type=JSON).status_code == 204
    nein = {"key": "guide.password", "language": "en", "helpful": False, "comment": " Bild  fehlt "}
    assert api(mitglied).post(url, nein, content_type=JSON).status_code == 204
    assert api(mitglied).post(url, {**nein, "key": "x"}, content_type=JSON).status_code == 400
    assert api(mitglied).post(url, {**nein, "language": "fr"}, content_type=JSON).status_code == 400
    lang = {**nein, "comment": "x" * 301}
    assert api(mitglied).post(url, lang, content_type=JSON).status_code == 400

    # Nur Hilfetext, Sprache, Fassung, Antwort, Satz und Tag; der Satz nur bei „Nein“
    felder = {f.name for f in HelpFeedback._meta.concrete_fields}
    assert felder == {"id", "key", "language", "version", "helpful", "comment", "day"}
    assert sorted(HelpFeedback.objects.values_list("helpful", "comment")) == [
        (False, "Bild fehlt"),
        (True, ""),
    ]

    liste = "/api/platform/help-feedback/"
    assert api(mitglied).get(liste).status_code == 403
    state = api(betrieb).get(liste).json()
    assert [(e["key"], e["yes"], e["no"]) for e in state["entries"]] == [("guide.password", 1, 1)]
    comment = state["entries"][0]["comments"][0]
    assert comment["text"] == "Bild fehlt" and comment["language"] == "en"

    weg = f"{liste}comments/{comment['id']}/"
    assert api(mitglied).delete(weg).status_code == 403
    after = api(betrieb).delete(weg).json()
    assert after["entries"][0]["comments"] == [] and after["entries"][0]["no"] == 1


def test_rueckmeldung_meiste_nein_zuerst_und_begrenzt(orgs, api):
    from access.catalog import PLATFORM_MANAGE
    from organizations import help_feedback
    from organizations.models import HelpFeedback, Organization

    user = make_user("viel@example.org")
    give_role(user, orgs["a"], [MEMBERS_VIEW], name="Leser")
    betrieb = make_user("betrieb2@example.org")
    give_role(betrieb, Organization.platform(), [PLATFORM_MANAGE], name="Betrieb")
    url = "/api/help/feedback/"
    for key, helpful in [
        ("guide.a", True),
        ("guide.b", False),
        ("guide.b", False),
        ("page.c", False),
    ]:
        body = {"key": key, "language": "de", "helpful": helpful}
        assert api(user).post(url, body, content_type=JSON).status_code == 204
    state = api(betrieb).get("/api/platform/help-feedback/").json()
    assert [e["key"] for e in state["entries"]] == ["guide.b", "page.c", "guide.a"]

    rest = help_feedback.PER_HOUR - 4
    body = {"key": "guide.a", "language": "de", "helpful": True}
    for _ in range(rest):
        assert api(user).post(url, body, content_type=JSON).status_code == 204
    assert api(user).post(url, body, content_type=JSON).status_code == 429
    assert HelpFeedback.objects.count() == help_feedback.PER_HOUR


def test_suche_ohne_treffer_zaehlt_nur_woerter(orgs, api):
    from access.catalog import PLATFORM_MANAGE
    from organizations.help_feedback import clean_term
    from organizations.models import HelpSearchMiss, Organization

    assert clean_term("  Rück   Lastschrift ") == "rück lastschrift"
    assert clean_term("ab") == ""
    assert clean_term("anna@example.org") == ""
    assert clean_term("Mitglied 4711") == ""
    assert clean_term("eins zwei drei vier fünf") == ""
    assert clean_term("x" * 61) == ""

    user = make_user("sucht@example.org")
    give_role(user, orgs["a"], [MEMBERS_VIEW], name="Leser")
    betrieb = make_user("betrieb3@example.org")
    give_role(betrieb, Organization.platform(), [PLATFORM_MANAGE], name="Betrieb")
    url = "/api/help/search-miss/"
    for term in ["Newsletter", "newsletter ", "Serienbrief", "Mitglied 4711"]:
        body = {"term": term, "language": "de"}
        assert api(user).post(url, body, content_type=JSON).status_code == 204
    felder = {f.name for f in HelpSearchMiss._meta.concrete_fields}
    assert felder == {"id", "term", "language", "count", "last_day"}

    liste = "/api/platform/help-feedback/"
    misses = api(betrieb).get(liste).json()["misses"]
    assert [(m["term"], m["count"]) for m in misses] == [("newsletter", 2), ("serienbrief", 1)]
    assert api(user).delete(f"{liste}misses/{misses[0]['id']}/").status_code == 403
    after = api(betrieb).delete(f"{liste}misses/{misses[0]['id']}/").json()
    assert [m["term"] for m in after["misses"]] == ["serienbrief"]
