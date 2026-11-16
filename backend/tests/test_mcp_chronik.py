"""KI-Schnittstelle: Chronik ansehen und als Entwurf bearbeiten (docs/mcp.md).

Alle Daten erfunden."""

from __future__ import annotations

import json

import pytest

from audit.models import AuditEntry
from website.content_models import TIMELINE_SLUG, WebsiteImage, WebsiteText
from website.models import Website

from .factories import give_role, make_user
from .test_mcp_verein import call, club, connect, editor, rpc, site  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def chronicle_on(club):  # noqa: F811
    club.enabled_modules = sorted({*club.enabled_modules, "chronicle"})
    club.save()
    return club


def data_of(text: str):
    return json.loads(text.split("\n\n", 1)[1])


def tools(token) -> set[str]:
    return {t["name"] for t in rpc(token, "tools/list").json()["result"]["tools"]}


def chronicle_of(org) -> WebsiteText:
    return WebsiteText.objects.get(website__organization=org, kind="page", slug=TIMELINE_SLUG)


def test_werkzeuge_je_bereich(chronicle_on, site, editor):  # noqa: F811
    names = tools(connect(editor, chronicle_on, scope="webseite.lesen")["access_token"])
    assert "chronik_ansehen" in names
    assert not {n for n in names if n.startswith("chronik_") and n != "chronik_ansehen"}
    names = tools(connect(editor, chronicle_on)["access_token"])
    assert {
        "chronik_aendern",
        "chronik_eintraege_anlegen",
        "chronik_eintrag_aendern",
        "chronik_eintrag_loeschen",
    } <= names
    assert not {n for n in names if "veroeffentlich" in n}


def test_eintraege_anlegen_aendern_entfernen(chronicle_on, site, editor):  # noqa: F811
    image = WebsiteImage.objects.create(
        organization=chronicle_on, website=site, key="Fahne00001", alt_text="Alte Vereinsfahne"
    )
    token = connect(editor, chronicle_on)["access_token"]
    text, failed = call(token, "chronik_ansehen")
    assert not failed, text
    info = data_of(text)
    assert info["anzahl"] == 0 and info["veroeffentlicht"] is False

    text, failed = call(
        token,
        "chronik_eintraege_anlegen",
        eintraege=[
            {"jahr": 1952, "ueberschrift": "Neue Fahne", "bilder": [image.pk], "text": "Geweiht."},
            {"jahr": 1920, "ueberschrift": "Gründung", "text": "Zwölf Bürger gründen den Verein."},
            {"art": "kapitel", "jahr": 1920, "bis": 1938, "ueberschrift": "Gründerjahre"},
        ],
    )
    assert not failed, text
    assert "Entwurf" in text
    result = data_of(text)
    assert result["anzahl"] == 3
    # Nummern in der neu sortierten Liste: Kapitel vor dem Ereignis seines Jahres
    assert {r["ueberschrift"]: r["nr"] for r in result["eintraege"]} == {
        "Neue Fahne": 3,
        "Gründung": 2,
        "Gründerjahre": 1,
    }
    page = chronicle_of(chronicle_on)
    assert [e["title"] for e in page.timeline] == ["Gründerjahre", "Gründung", "Neue Fahne"]
    assert page.timeline[0]["kind"] == "chapter" and page.timeline[0]["until"] == 1938
    assert page.timeline[2]["images"] == [image.pk]
    assert not page.is_published and page.published_timeline == []

    text, failed = call(
        token,
        "chronik_eintrag_aendern",
        nr=3,
        ueberschrift_bisher="Neue Fahne",
        jahr=1910,
        bildposition="unten",
        bis=1911,
    )
    assert not failed, text
    page.refresh_from_db()
    assert page.timeline[0]["title"] == "Neue Fahne"
    assert (page.timeline[0]["until"], page.timeline[0]["image_position"]) == (1911, "below")
    assert data_of(text)["eintraege"][0]["nr"] == 1

    # Veraltete Nummer: nichts ändert sich
    text, failed = call(token, "chronik_eintrag_loeschen", nr=1, ueberschrift_bisher="Gründung")
    assert failed and "chronik_ansehen" in text
    assert len(chronicle_of(chronicle_on).timeline) == 3

    text, failed = call(token, "chronik_eintrag_loeschen", nr=1, ueberschrift_bisher="Neue Fahne")
    assert not failed, text
    assert [e["title"] for e in chronicle_of(chronicle_on).timeline] == [
        "Gründerjahre",
        "Gründung",
    ]

    text, failed = call(
        token, "chronik_aendern", einleitung="Unser Verein seit 1920.", neueste_zuerst=True
    )
    assert not failed, text
    page.refresh_from_db()
    assert page.body == "Unser Verein seit 1920." and page.timeline_newest_first is True
    # Protokoll nennt den Assistenten
    entry = AuditEntry.objects.filter(organization=chronicle_on, action="update").latest("pk")
    assert "KI-Assistent" in entry.via


def test_pruefung_wie_in_der_oberflaeche(chronicle_on, site, editor, orgs):  # noqa: F811
    token = connect(editor, chronicle_on)["access_token"]
    text, failed = call(
        token, "chronik_eintraege_anlegen", eintraege=[{"jahr": 3500, "ueberschrift": "Zukunft"}]
    )
    assert failed and "1000" in text
    text, failed = call(
        token,
        "chronik_eintraege_anlegen",
        eintraege=[{"jahr": 1950, "ueberschrift": "Lang", "text": "x" * 401}],
    )
    assert failed
    text, failed = call(
        token,
        "chronik_eintraege_anlegen",
        eintraege=[{"art": "kapitel", "jahr": 1950, "ueberschrift": "K", "bilder": [1]}],
    )
    assert failed and "Kapitel" in text
    # Bilder einer anderen Einheit gibt es hier nicht (Mandantentrennung)
    other_site = Website.objects.create(organization=orgs["b"], public_key="mcp-b")
    foreign = WebsiteImage.objects.create(
        organization=orgs["b"], website=other_site, key="Fremd0001"
    )
    text, failed = call(
        token,
        "chronik_eintraege_anlegen",
        eintraege=[{"jahr": 1950, "ueberschrift": "Fremd", "bilder": [foreign.pk]}],
    )
    assert failed and "Bild" in text
    assert chronicle_of(chronicle_on).timeline == []
    text, failed = call(token, "chronik_eintrag_aendern", nr=1, jahr=1950)
    assert failed and "Nummer" in text


def test_ohne_modul_chronik(club, site, editor):  # noqa: F811
    token = connect(editor, club)["access_token"]
    text, failed = call(token, "chronik_ansehen")
    assert failed and "Chronik" in text


def test_chronist_ohne_webseitenrechte(club):  # noqa: F811
    """Wer nur die Chronik pflegt, kann einen Assistenten dafür verbinden; die Webseite bleibt
    verborgen, auch ohne Modul „Webseite“."""
    club.enabled_modules = ["members", "chronicle", "mcp"]
    club.save()
    chronist = make_user("ki-chronik@example.org", first_name="Clara", last_name="Muster")
    give_role(chronist, club, permissions=["chronicle.edit", "mcp.connect"], name="Chronik")
    token = connect(chronist, club)["access_token"]
    text, failed = call(
        token, "chronik_eintraege_anlegen", eintraege=[{"jahr": 1920, "ueberschrift": "Gründung"}]
    )
    assert not failed, text
    assert Website.objects.get(organization=club).state == Website.State.OFF
    assert chronicle_of(club).timeline[0]["title"] == "Gründung"
    text, failed = call(token, "webseite_texte")
    assert failed


def test_nur_lesen(chronicle_on, site):  # noqa: F811
    reader = make_user("ki-leser@example.org")
    give_role(reader, chronicle_on, permissions=["chronicle.view", "mcp.connect"], name="Lesen")
    token = connect(reader, chronicle_on)["access_token"]
    text, failed = call(token, "chronik_ansehen")
    # Ohne Pflegerecht legt HUBIplan die Chronik nicht an
    assert failed and "Noch keine Chronik" in text
    WebsiteText.objects.create(
        organization=chronicle_on, website=site, kind="page", slug=TIMELINE_SLUG, title="Chronik"
    )
    text, failed = call(token, "chronik_ansehen")
    assert not failed, text
    text, failed = call(
        token, "chronik_eintraege_anlegen", eintraege=[{"jahr": 1920, "ueberschrift": "Gründung"}]
    )
    assert failed and "nur lesen" in text
    assert chronicle_of(chronicle_on).timeline == []
