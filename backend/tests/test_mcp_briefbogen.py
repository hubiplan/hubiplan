"""KI-Schnittstelle: Briefbogen der Einheit (Issue #470, docs/mcp.md). Alles erfunden."""

from __future__ import annotations

import json

import pytest

from audit.models import AuditEntry
from letterhead import data as service
from letterhead.models import Letterhead
from organizations.models import Department

from .factories import give_role, make_user
from .test_mcp_verein import call, club, connect, editor, rpc, site  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)

LETTERHEAD = "verein.briefbogen"
ALL = f"webseite.lesen webseite.entwurf {LETTERHEAD}"


@pytest.fixture
def secretary(club):  # noqa: F811
    user = make_user("ki-brief@example.org", first_name="Max", last_name="Muster")
    give_role(
        user,
        club,
        permissions=["org.edit", "settings.view", "website.content", "mcp.connect"],
        name="Schriftführung",
    )
    return user


def data_of(text: str):
    return json.loads(text.split("\n\n", 1)[1])


def tools(token) -> set[str]:
    return {t["name"] for t in rpc(token, "tools/list").json()["result"]["tools"]}


def test_nur_mit_eigenem_haken(club, site, secretary):  # noqa: F811
    got = connect(secretary, club, scope=ALL)
    assert got["scope"] == "webseite.lesen webseite.entwurf"
    names = tools(got["access_token"])
    assert "briefbogen_ansehen" in names and "briefbogen_aendern" not in names
    got = connect(secretary, club, scope=ALL, haken=[LETTERHEAD])
    assert LETTERHEAD in got["scope"].split()
    assert "briefbogen_aendern" in tools(got["access_token"])


def test_ansehen_und_aendern(club, site, secretary):  # noqa: F811
    club.accent_color = "#fbc707"
    club.save()
    token = connect(secretary, club, scope=ALL, haken=[LETTERHEAD])["access_token"]
    text, failed = call(token, "briefbogen_ansehen")
    assert not failed, text
    info = data_of(text)
    assert info["einstellungen"]["linienfarbe"] == 1
    assert info["einstellungen"]["fusszeile"]["bankverbindung"] is True
    assert any("Linienfarbe" in h for h in info["hinweise"])
    text, failed = call(
        token,
        "briefbogen_aendern",
        linienfarbe=0,
        linie_fusszeile=False,
        logo_groesse="large",
        name_neben_logo=False,
        schrift="Source Sans 3",
        schrift_ueberschriften="Crimson Pro",
        ersatzschrift="Verdana",
        titelfarbe="primary",
        tabellenlinien=0,
        tabellenstreifen="none",
        fusszeile={"vorstand": False, "social_media": True},
    )
    assert not failed, text
    lh = Letterhead.objects.get(organization=club)
    assert (lh.line_color, lh.footer_line, lh.logo_size, lh.show_name) == (
        "0",
        False,
        "large",
        False,
    )
    assert (lh.font, lh.heading_font, lh.font_fallback) == (
        "Source Sans 3",
        "Crimson Pro",
        "Verdana",
    )
    assert (lh.title_color, lh.table_line_color, lh.table_stripe) == ("primary", "0", "none")
    assert (lh.show_board, lh.show_social) == (False, True)
    assert data_of(text)["einstellungen"]["tabellenstreifen"] == "none"
    entry = AuditEntry.objects.filter(organization=club, user=secretary).latest("id")
    assert entry.via == "KI-Assistent (Testassistent)"
    # Streifen auch als Palettenplatz
    text, failed = call(token, "briefbogen_aendern", tabellenstreifen=1)
    assert not failed, text
    assert Letterhead.objects.get(organization=club).table_stripe == "1"
    # Unbekannte Werte: abgelehnt, nichts geändert
    _text, failed = call(token, "briefbogen_aendern", linienfarbe=9)
    assert failed
    assert Letterhead.objects.get(organization=club).line_color == "0"
    _text, failed = call(token, "briefbogen_aendern")
    assert failed


def test_untereinheit(club, site, secretary):  # noqa: F811
    zug = Department.objects.create(organization=club, name="Jägerzug", own_workspace=True)
    token = connect(secretary, club, scope=ALL, haken=[LETTERHEAD])["access_token"]
    text, failed = call(token, "briefbogen_ansehen", untereinheit=zug.pk)
    assert not failed, text
    assert data_of(text)["gilt_von"] == club.name
    text, failed = call(
        token, "briefbogen_aendern", untereinheit=zug.pk, briefbogen="own", linienfarbe=0
    )
    assert not failed, text
    assert service.ensure(zug).line_color == "0"
    assert service.ensure(club).line_color == "1"


def test_ohne_recht_nur_lesen(club, site, editor):  # noqa: F811
    give_role(editor, club, permissions=["settings.view"], name="Lesen")
    token = connect(editor, club, scope=ALL, haken=[LETTERHEAD])["access_token"]
    text, failed = call(token, "briefbogen_ansehen")
    assert not failed, text
    _text, failed = call(token, "briefbogen_aendern", linienfarbe=0)
    assert failed
    assert service.ensure(club).line_color == "1"


def test_name_im_kopf(club, site, secretary):  # noqa: F811
    token = connect(secretary, club, scope=ALL, haken=[LETTERHEAD])["access_token"]
    text, failed = call(
        token,
        "briefbogen_aendern",
        name_im_kopf="Musterschützen-Bruderschaft\nMusterstadt von 1920",
        zweite_zeile_kleiner=True,
    )
    assert not failed, text
    lh = Letterhead.objects.get(organization=club)
    assert (lh.head_name, lh.head_name_small) == (
        "Musterschützen-Bruderschaft\nMusterstadt von 1920",
        True,
    )
    assert data_of(text)["einstellungen"]["zweite_zeile_kleiner"] is True
    _text, failed = call(token, "briefbogen_aendern", name_im_kopf="Eins\nZwei\nDrei")
    assert failed
    assert Letterhead.objects.get(organization=club).head_name.count("\n") == 1


def test_logo_fuer_briefbogen(club, site, secretary, settings, tmp_path):  # noqa: F811
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    from website import content

    settings.PRIVATE_ROOT = tmp_path / "private"
    settings.MEDIA_ROOT = tmp_path / "media"
    buf = io.BytesIO()
    Image.new("RGBA", (500, 100), (18, 62, 122, 255)).save(buf, "PNG")
    upload = SimpleUploadedFile("marke.png", buf.getvalue(), content_type="image/png")
    image = content.store_image(site, upload, "", "", secretary)
    token = connect(secretary, club, scope=ALL, haken=[LETTERHEAD])["access_token"]
    text, failed = call(token, "briefbogen_ansehen")
    assert not failed, text
    assert data_of(text)["eigenes_logo"] is False
    text, failed = call(token, "briefbogen_logo_aus_bild", nummer=image.pk)
    assert not failed, text
    assert data_of(text)["eigenes_logo"] is True
    club.refresh_from_db()
    assert not club.logo.name  # Erscheinungsbild bleibt
    assert Letterhead.objects.get(organization=club).logo.name.startswith("logos/briefbogen/")
    text, failed = call(token, "briefbogen_logo_aus_bild", entfernen=True)
    assert not failed, text
    assert not Letterhead.objects.get(organization=club).logo.name
    _text, failed = call(token, "briefbogen_logo_aus_bild")
    assert failed
