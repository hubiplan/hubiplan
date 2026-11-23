"""Namensform je Bereich der Webseite (Issue #709): Vorstand mit vollem Namen, Aktive als
„D. Muster“, Passive wieder voll. Alle Personen und Vereine sind erfunden."""

from __future__ import annotations

import datetime
import json

import pytest
from django.test import Client

from access.models import Role, RoleAssignment
from members.models import MemberType
from website import services
from website.models import PublicationConsent, Website
from website.public import format_name

from .factories import give_role, make_member, make_user, make_website
from .test_mcp_verein import call, club, connect, rpc, site  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def private_root(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"


# --- Formen ---


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [("full", "Dora Asbeck"), ("short", "D. Asbeck"), ("initial", "Dora A.")],
)
def test_drei_formen(fmt, expected):
    assert format_name("Dora", "Asbeck", fmt) == expected


def test_kurzform_mit_mehreren_vornamen_titel_und_ordnungszahl():
    assert format_name("Hans-Peter Josef", "Muster", "short") == "H.-P. J. Muster"
    assert format_name("Erika", "Beispiel", "short", "Dr.") == "Dr. E. Beispiel"
    # Würdenträger: Ordnungszahl bleibt hinter dem (abgekürzten) Vornamen
    assert format_name("Max", "Muster", "short", ordinal="II.") == "M. II. Muster"
    assert format_name("Max", "Muster", "full", ordinal="II.") == "Max II. Muster"
    assert format_name("Max", "Muster", "initial", ordinal="II.") == "Max II. M."


def test_bereich_mitgliedsart_und_voreinstellung():
    web = Website(name_format="initial", name_formats={"members": "short", "membertype:7": "full"})
    assert web.name_format_for("board") == "initial"
    assert web.name_format_for("members") == "short"
    assert web.name_format_for("members", 7) == "full"
    assert web.name_format_for("members", 8) == "short"
    # Alte oder kaputte Werte fallen auf die Namensform der Webseite zurück
    web.name_formats = {"board": "gibt-es-nicht"}
    assert web.name_format_for("board") == "initial"
    web.name_formats = None
    assert web.name_format_for("results") == "initial"


# --- Öffentliche Schnittstelle ---

KEY = "namensform-a"


def public(path, preview_site=None):
    headers = {}
    if preview_site is not None:
        session, _ = services.exchange(preview_site, services.open_token(preview_site))
        headers = {"HTTP_X_PREVIEW_SESSION": session}
    return Client().get(f"/api/public/site/v1/{KEY}/{path}", **headers)


def consent(m, category):
    PublicationConsent.objects.create(
        organization=m.organization,
        membership=m,
        category=category,
        since=datetime.date(2024, 1, 1),
        source="paper",
    )


@pytest.fixture
def kapelle(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "website"]
    org.save()
    web = make_website(org, public_key=KEY, state="public")
    aktiv = MemberType.objects.create(organization=org, name="aktiv", active=True)
    passiv = MemberType.objects.create(organization=org, name="passiv")
    dora = make_member(org, "Dora", "Asbeck", member_type=aktiv)
    paul = make_member(org, "Paul", "Passiv", member_type=passiv)
    for m in (dora, paul):
        consent(m, PublicationConsent.Category.MEMBER_LIST)
    chair = Role.objects.create(
        organization=org, name="1. Vorsitzende", on_website=True, website_position=1
    )
    erika = make_member(org, "Erika", "Beispiel")
    RoleAssignment.objects.create(organization=org, role=chair, person=erika.person)
    web.blocks = {
        **(web.blocks or {}),
        "members": True,
        f"membertype:{aktiv.pk}": True,
        f"membertype:{passiv.pk}": True,
    }
    web.save()
    return {"org": org, "web": web, "aktiv": aktiv, "passiv": passiv}


def names(path, **kw):
    return [m["name"] for m in public(path, **kw).json()["members"]]


def board_name(**kw):
    return public("board/", **kw).json()["roles"][0]["holders"][0]["name"]


def test_ohne_wahl_wie_bisher(kapelle):
    assert board_name() == "Erika Beispiel"
    assert names("members/aktiv/") == ["Dora Asbeck"]
    web = kapelle["web"]
    web.name_format = "short"
    web.save()
    assert board_name() == "E. Beispiel"
    assert names("members/passiv/") == ["P. Passiv"]


def test_vorstand_voll_aktive_kurz_passive_voll(kapelle):
    web = kapelle["web"]
    web.name_formats = {f"membertype:{kapelle['aktiv'].pk}": "short"}
    web.save()
    assert board_name() == "Erika Beispiel"
    assert names("members/aktiv/") == ["D. Asbeck"]
    assert names("members/passiv/") == ["Paul Passiv"]
    # Alle Listen kurz, der Vorstand bleibt voll
    web.name_formats = {"members": "initial"}
    web.save()
    assert names("members/aktiv/") == ["Dora A."] and board_name() == "Erika Beispiel"
    web.name_formats = {"board": "initial"}
    web.save()
    assert board_name() == "Erika B." and names("members/aktiv/") == ["Dora Asbeck"]


# --- Verwaltung: Entwurf, Prüfung, Veröffentlichen ---


@pytest.fixture
def manager(kapelle, api):
    user = make_user("namensform@example.org")
    give_role(user, kapelle["org"], permissions=["website.manage"], name="Webseite")
    return api(user)


def url(org, path=""):
    return f"/api/orgs/{org.pk}/website/{path}"


def test_im_entwurf_erst_in_der_vorschau(kapelle, manager):
    org, web, aktiv = kapelle["org"], kapelle["web"], kapelle["aktiv"]
    draft = {"name_formats": {f"membertype:{aktiv.pk}": "short", "board": ""}}
    resp = manager.put(url(org), {"draft": draft}, "application/json")
    assert resp.status_code == 200, resp.content
    # Leere Wahl = wie die Webseite, wird nicht gespeichert
    expected = {f"membertype:{aktiv.pk}": "short"}
    assert resp.json()["website"]["draft"] == {"name_formats": expected}
    assert names("members/aktiv/") == ["Dora Asbeck"]
    assert names("members/aktiv/", preview_site=web) == ["D. Asbeck"]
    assert manager.post(url(org, "design/publish/")).status_code == 200
    web.refresh_from_db()
    assert web.name_formats == expected and web.draft == {}
    assert names("members/aktiv/") == ["D. Asbeck"]


@pytest.mark.parametrize(
    "value",
    [{"vorstand": "full"}, {"board": "kurz"}, {"membertype:x": "full"}, ["board"]],
)
def test_wird_geprueft(kapelle, manager, value):
    resp = manager.put(url(kapelle["org"]), {"draft": {"name_formats": value}}, "application/json")
    assert resp.status_code == 400


def test_neue_namensform_der_webseite(kapelle, manager):
    resp = manager.put(url(kapelle["org"]), {"name_format": "short"}, "application/json")
    assert resp.status_code == 200, resp.content
    kapelle["web"].refresh_from_db()
    assert kapelle["web"].name_format == "short"


# --- KI-Schnittstelle ---


@pytest.fixture
def ki_manager(club):  # noqa: F811
    user = make_user("ki-namensform@example.org", first_name="Max", last_name="Muster")
    give_role(user, club, permissions=["website.manage", "mcp.connect"], name="Webseite")
    return user


def test_ki_aendert_namensform_im_entwurf(club, site, ki_manager):  # noqa: F811
    token = connect(ki_manager, club)["access_token"]
    text, failed = call(token, "webseite_gestaltung_ansehen")
    assert not failed, text
    info = json.loads(text.split("\n\n", 1)[1])
    assert info["namensformen"]["werte"]["short"] == "V. Nachname"
    assert "board" in info["namensformen"]["bereiche"] and info["namensform"] == {}
    text, failed = call(
        token, "webseite_gestaltung_aendern", namensform={"board": "full", "members": "short"}
    )
    assert not failed, text
    site.refresh_from_db()
    assert site.draft["name_formats"] == {"board": "full", "members": "short"}
    assert site.name_formats == {}
    # null nimmt einen Bereich zurück
    text, failed = call(token, "webseite_gestaltung_aendern", namensform={"board": None})
    assert not failed, text
    site.refresh_from_db()
    assert site.draft["name_formats"] == {"members": "short"}
    _text, failed = call(token, "webseite_gestaltung_aendern", namensform={"board": "kurz"})
    assert failed
