"""KI-Schnittstelle: Erscheinungsbild der Einheit (docs/mcp.md). Alles erfunden."""

from __future__ import annotations

import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from audit.models import AuditEntry
from website import content

from .factories import give_role, make_user
from .test_mcp_verein import call, club, connect, editor, rpc, site  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)

ALL = "webseite.lesen webseite.entwurf verein.erscheinungsbild"
THEME = "verein.erscheinungsbild"


@pytest.fixture(autouse=True)
def private_root(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def designer(club):  # noqa: F811
    user = make_user("ki-farben@example.org", first_name="Mia", last_name="Muster")
    give_role(
        user,
        club,
        permissions=["theme.edit", "website.content", "mcp.connect"],
        name="Öffentlichkeitsarbeit",
    )
    return user


def data_of(text: str):
    return json.loads(text.split("\n\n", 1)[1])


def test_bereich_und_werkzeuge(club, site, designer):  # noqa: F811
    token = connect(designer, club, scope="webseite.lesen webseite.entwurf")["access_token"]
    names = {t["name"] for t in rpc(token, "tools/list").json()["result"]["tools"]}
    assert "erscheinungsbild_ansehen" in names
    assert not {"erscheinungsbild_aendern", "logo_aus_bild"} & names
    token = connect(designer, club, scope=ALL, haken=[THEME])["access_token"]
    names = {t["name"] for t in rpc(token, "tools/list").json()["result"]["tools"]}
    assert {"erscheinungsbild_aendern", "logo_aus_bild"} <= names


def test_erscheinungsbild_nur_mit_eigenem_haken(club, site, designer):  # noqa: F811
    # Gesamtaudit 13.11., H-04: Fragt der Assistent nach allem, gibt es das Erscheinungsbild
    # trotzdem nur, wenn die Person es auf der Seite anhakt.
    for scope in (ALL, ""):
        got = connect(designer, club, scope=scope)
        assert got["scope"] == "webseite.lesen webseite.entwurf"
        names = {
            t["name"] for t in rpc(got["access_token"], "tools/list").json()["result"]["tools"]
        }
        assert not {"erscheinungsbild_aendern", "logo_aus_bild"} & names
    # Der Haken gilt auch, wenn der Assistent gar nicht danach gefragt hat
    got = connect(designer, club, scope="webseite.lesen", haken=[THEME])
    assert got["scope"] == "webseite.lesen verein.erscheinungsbild"
    # Nur nach dem Erscheinungsbild gefragt, nicht angehakt: es bleibt beim Lesen
    assert connect(designer, club, scope=THEME)["scope"] == "webseite.lesen"
    # Die Seite bietet den Haken an und zählt den Bereich nicht zu den üblichen
    from .test_mcp_verein import params, register, with_mfa

    query = params(register()["client_id"], scope=ALL)
    info = with_mfa(designer).get("/api/mcp/oauth/authorize/", query)
    assert info.status_code == 200, info.content
    assert [s["scope"] for s in info.json()["optional"]] == [THEME]
    assert THEME not in [s["scope"] for s in info.json()["scopes"]]


def test_farben_sofort_mit_protokoll(club, site, designer):  # noqa: F811
    token = connect(designer, club, scope=ALL, haken=[THEME])["access_token"]
    text, failed = call(token, "erscheinungsbild_ansehen")
    assert not failed, text
    assert data_of(text)["eigene_farben"] is False
    text, failed = call(
        token,
        "erscheinungsbild_aendern",
        hauptfarbe={"farbe": "#123E7A", "name": "Vereinsblau", "verwendung": "Kopf"},
        zweitfarbe={"farbe": "#e0a526", "name": "Gold"},
        weitere_farben=[{"farbe": "#f4f1ea", "name": "Sand"}],
        verlaeufe=[{"name": "Blau-Gold", "von": 0, "bis": 1}],
        farbrollen={"background": 2},
    )
    assert not failed, text
    club.refresh_from_db()
    assert club.primary_color == "#123e7a" and club.primary_color_name == "Vereinsblau"
    assert club.extra_colors == [{"color": "#f4f1ea", "name": "Sand"}]
    assert club.gradients[0]["from"] == 0 and club.palette_roles == {"background": 2}
    info = data_of(text)
    assert info["palette"][2]["farbe"] == "#f4f1ea"
    entry = AuditEntry.objects.filter(organization=club, user=designer).latest("id")
    assert entry.via == "KI-Assistent (Testassistent)"
    # Rollen werden ergänzt, null entfernt
    text, failed = call(
        token, "erscheinungsbild_aendern", farbrollen={"text": 0, "background": None}
    )
    assert not failed, text
    club.refresh_from_db()
    assert club.palette_roles == {"text": 0}
    # Schlecht lesbar: abgelehnt, nichts geändert
    text, failed = call(token, "erscheinungsbild_aendern", weitere_farben=[{"farbe": "#888888"}])
    assert failed
    club.refresh_from_db()
    assert club.extra_colors == [{"color": "#f4f1ea", "name": "Sand"}]
    _text, failed = call(token, "erscheinungsbild_aendern")
    assert failed


def test_ohne_recht_nur_lesen(club, site, editor):  # noqa: F811
    token = connect(editor, club, scope=ALL, haken=[THEME])["access_token"]
    _text, failed = call(token, "erscheinungsbild_aendern", hauptfarbe={"farbe": "#123e7a"})
    assert failed
    club.refresh_from_db()
    assert not club.primary_color


def test_logo_aus_bild(club, site, designer):  # noqa: F811
    buf = io.BytesIO()
    Image.new("RGBA", (300, 200), (18, 62, 122, 255)).save(buf, "PNG")
    upload = SimpleUploadedFile("wappen.png", buf.getvalue(), content_type="image/png")
    image = content.store_image(site, upload, "", "", designer)
    token = connect(designer, club, scope=ALL, haken=[THEME])["access_token"]
    text, failed = call(token, "logo_aus_bild", nummer=image.pk)
    assert not failed, text
    club.refresh_from_db()
    assert club.logo.name and not club.logo_dark.name
    text, failed = call(token, "logo_aus_bild", nummer=image.pk, dunkel=True)
    assert not failed, text
    club.refresh_from_db()
    assert club.logo_dark.name
    _text, failed = call(token, "logo_aus_bild", nummer=999999)
    assert failed
