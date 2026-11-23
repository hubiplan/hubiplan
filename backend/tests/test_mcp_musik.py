"""KI-Schnittstelle: Musik, Uniformen und Auftrittsarten (Issues #712/#713). Alles erfunden."""

from __future__ import annotations

import json

import pytest

from core.tenancy import tenant_context
from events.models import Event
from music.models import Performance

from .factories import give_role, make_user
from .test_mcp_verein import call, club, connect, rpc  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)

MUSIC = "musik.auftritte"
ALL = f"webseite.lesen {MUSIC}"


@pytest.fixture
def musikwart(club):  # noqa: F811
    club.enabled_modules = [*club.enabled_modules, "music"]
    club.save()
    user = make_user("ki-musik@example.org", first_name="Max", last_name="Muster")
    give_role(
        user,
        club,
        permissions=["music.view", "music.edit", "events.view", "mcp.connect"],
        name="Musikwart",
    )
    return user


def tools(token) -> set[str]:
    return {t["name"] for t in rpc(token, "tools/list").json()["result"]["tools"]}


def test_nur_mit_eigenem_haken(club, musikwart):  # noqa: F811
    got = connect(musikwart, club, scope=ALL)
    assert "musik_ansehen" not in tools(got["access_token"])
    got = connect(musikwart, club, scope=ALL, haken=[MUSIC])
    assert {"musik_ansehen", "musik_auftritt_aendern"} <= tools(got["access_token"])


def test_uniform_und_art_setzen(club, musikwart):  # noqa: F811
    with tenant_context(club.pk):
        event = Event.objects.create(
            organization=club,
            title="Musterumzug",
            starts_at="2099-06-01T10:00:00Z",
            ends_at="2099-06-01T12:00:00Z",
        )
        performance = Performance.objects.create(organization=club, event=event)
    token = connect(musikwart, club, scope=ALL, haken=[MUSIC])["access_token"]
    # „name“ ist auch der Parameter von call(): Werkzeug direkt aufrufen
    resp = rpc(
        token,
        "tools/call",
        {
            "name": "musik_uniform_speichern",
            "arguments": {"name": "Winteruniform", "checkliste": ["Mantel", "Mütze"]},
        },
    )
    result = resp.json()["result"]
    assert not result["isError"], result
    text, failed = call(token, "musik_ansehen")
    assert not failed, text
    data = json.loads(text)
    uniform = next(u for u in data["uniformen"] if u["name"] == "Winteruniform")
    art = next(k for k in data["auftrittsarten"] if k["name"] == "Umzug")
    assert uniform["checkliste"] == ["Mantel", "Mütze"]
    text, failed = call(
        token,
        "musik_auftritt_aendern",
        nummer=performance.pk,
        art=art["nummer"],
        uniform=uniform["nummer"],
        uniform_ergaenzung="mit Handschuhen",
    )
    assert not failed, text
    performance.refresh_from_db()
    assert performance.kind_id == art["nummer"]
    assert performance.uniform_text() == "Winteruniform · mit Handschuhen"
