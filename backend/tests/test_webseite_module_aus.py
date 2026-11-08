"""Webseite bei abgeschalteten Modulen (Ralf 08.11.2026): Einstellungen und Bausteine
eines abgeschalteten Moduls erscheinen weder in der Verwaltung noch auf der Webseite
(alles erfunden)."""

import datetime

import pytest
from django.test import Client

from access.models import Role, RoleAssignment
from music.models import Musician, Piece, Skill
from website.models import Website

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "module-aus"


def public(path):
    return Client().get(f"/api/public/site/v1/{KEY}/{path}")


def club_with(orgs, *modules):
    org = orgs["a"]
    org.enabled_modules = ["members", "website", *modules]
    org.save()
    return org


def payload(org, api):
    user = make_user("web-aus@example.org")
    give_role(user, org, permissions=["website.manage"], name="Webseite")
    resp = api(user).get(f"/api/orgs/{org.pk}/website/")
    assert resp.status_code == 200, resp.content
    return resp.json()


def test_bausteine_abgeschalteter_module_fehlen_in_der_verwaltung(orgs, api):
    org = club_with(orgs)
    Website.objects.create(organization=org, public_key=KEY, state="public")
    data = payload(org, api)
    gone = {"events", "honors", "results", "repertoire", "bookings", "history", "posts"}
    assert not gone & set(data["block_labels"])
    assert not {"events", "honors", "results", "instagram", "facebook"} & set(data["home_labels"])
    assert not gone & {item["key"] for item in data["website"]["menu_items"]}
    assert {"board", "contact"} <= set(data["block_labels"])


def test_bausteine_eingeschalteter_module_bleiben(orgs, api):
    org = club_with(orgs, "events", "honors", "competitions", "scores", "chronicle")
    Website.objects.create(organization=org, public_key=KEY, state="public")
    data = payload(org, api)
    assert {"events", "honors", "results", "repertoire", "history"} <= set(data["block_labels"])
    assert {"events", "honors", "results"} <= set(data["home_labels"])


def test_instrument_nur_mit_musikmodul(orgs):
    org = club_with(orgs, "events", "music", "scores")
    Website.objects.create(organization=org, public_key=KEY, state="public", show_instrument=True)
    m = make_member(org, "Dora", "Dirigent")
    role = Role.objects.create(organization=org, name="Dirigentin", on_website=True)
    RoleAssignment.objects.create(
        organization=org, role=role, membership=m, valid_from=datetime.date(2020, 1, 1)
    )
    musician = Musician.objects.create(organization=org, membership=m)
    Skill.objects.create(organization=org, musician=musician, instrument="Tuba", primary=True)
    holder = public("board/").json()["roles"][0]["holders"][0]
    assert holder["instrument"] == "Tuba"
    org.enabled_modules = ["members", "website"]
    org.save()
    holder = public("board/").json()["roles"][0]["holders"][0]
    assert "instrument" not in holder


def test_repertoire_mit_notenarchiv_ohne_musik(orgs):
    org = club_with(orgs, "scores")
    Website.objects.create(
        organization=org, public_key=KEY, state="public", blocks={"repertoire": True}
    )
    Piece.objects.create(organization=org, title="Marsch (erfunden)", on_website=True)
    assert [p["title"] for p in public("repertoire/").json()["pieces"]] == ["Marsch (erfunden)"]
    org.enabled_modules = ["members", "website"]
    org.save()
    assert public("repertoire/").status_code == 404
