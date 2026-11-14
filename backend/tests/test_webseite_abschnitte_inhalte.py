"""Weitere Abschnittsarten ohne Datenbezug (Ralf 14.11.2026): Mitglied werden, Spendenaufruf,
Zeiten, Zwei Spalten, Tabelle, Zeitstrahl, Festprogramm, Hinweis-Kasten, Aufklappbar,
Bilder, Download-Liste. Alle Daten erfunden."""

import pytest
from django.test import Client

from admission.models import ApplicationForm
from core.tenancy import rls_bypass
from website import home
from website.content_models import WebsiteDocument
from website.models import Website, WebsiteImage

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "inhalte-a"


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "website"]
    org.save()
    return org


@pytest.fixture
def site(club):
    return Website.objects.create(
        organization=club,
        public_key=KEY,
        state="public",
        privacy_mode="link",
        privacy_url="https://example.org/datenschutz",
        blocks={"events": True, "contact": True, "statutes": True},
    )


@pytest.fixture
def manager(club, api):
    user = make_user("inhalte@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    return api(user)


def url(club):
    return f"/api/orgs/{club.pk}/website/"


def custom(key, kind, data):
    return {"key": f"c:{key}", "kind": kind, "on": True, "data": data}


def layout():
    return Client().get(f"/api/public/site/v1/{KEY}/").json()["home_layout"]


def put(manager, club, sections):
    return manager.put(url(club), {"home_sections": sections}, "application/json")


def test_neue_arten_in_der_auswahl(club, site, manager):
    kinds = manager.get(url(club)).json()["home_kinds"]
    for kind in (
        "join",
        "donation",
        "hours",
        "columns",
        "table",
        "timeline",
        "program",
        "callout",
        "accordion",
        "images",
        "downloads",
    ):
        assert kind in kinds and kind in home.KIND_HINTS


def test_inhalte_speichern_und_zeigen(club, site, manager):
    bild = WebsiteImage.objects.create(
        organization=club, website=site, key="fest1", alt_text="Fest"
    )
    doc = WebsiteDocument.objects.create(
        organization=club,
        website=site,
        section="documents",
        key=WebsiteDocument.new_key(),
        title="Schießordnung",
        file="webseite/ordnung.pdf",
        content_type="application/pdf",
        size=50_000,
        published=True,
    )
    sections = [
        custom(
            "s",
            "donation",
            {
                "title": "Neue Fahne",
                "text": "Hilf mit!",
                "holder": "Schützenverein Musterstadt",
                "iban": "de02 1203 0000 0000 2020 51",
                "purpose": "Spende Fahne",
                "goal": 5000,
                "raised": 2300,
            },
        ),
        custom(
            "h",
            "hours",
            {"items": [{"day": "Dienstag", "time": "19–22 Uhr"}, {"day": "", "time": "x"}]},
        ),
        custom("c", "columns", {"items": [{"title": "Links", "text": "A"}, {"text": "B"}]}),
        custom(
            "t",
            "table",
            {"head": ["Art", "Beitrag"], "rows": [["Erwachsene", "60 €"], ["", ""], ["Jugend"]]},
        ),
        custom("z", "timeline", {"items": [{"when": "1920", "title": "Gründung"}]}),
        custom(
            "p",
            "program",
            {
                "items": [
                    {"day": "Samstag", "time": "14:00", "text": "Antreten"},
                    {"day": "Samstag", "time": "15:00", "text": "Festzug"},
                    {"day": "Sonntag", "time": "11:00", "text": "Frühschoppen"},
                ]
            },
        ),
        custom("k", "callout", {"title": "Wichtig", "text": "Halle zu", "style": "warning"}),
        custom("a", "accordion", {"items": [{"title": "Ordnung", "text": "§ 1"}, {"text": "x"}]}),
        custom("b", "images", {"items": [{"image": bild.pk, "caption": "Festzug"}], "columns": 4}),
        custom("d", "downloads", {"documents": [doc.pk, doc.pk, 99999]}),
    ]
    resp = put(manager, club, sections)
    assert resp.status_code == 200, resp.content
    saved = {
        s["key"]: s["data"] for s in resp.json()["website"]["home_sections"] if s["key"][:2] == "c:"
    }
    assert saved["c:s"]["iban"] == "DE02120300000000202051"
    assert saved["c:t"]["rows"][2] == ["Jugend", ""]
    assert saved["c:d"]["documents"] == [doc.pk]

    out = {s["kind"]: s for s in layout() if s["key"].startswith("c:")}
    assert out["donation"]["percent"] == 46 and out["donation"]["raised"] == 2300
    assert [i["day"] for i in out["hours"]["items"]] == ["Dienstag"]
    assert [i["title"] for i in out["columns"]["items"]] == ["Links", ""]
    assert out["table"]["rows"] == [["Erwachsene", "60 €"], ["Jugend", ""]]
    assert out["timeline"]["items"][0]["when"] == "1920"
    assert [(d["day"], len(d["items"])) for d in out["program"]["days"]] == [
        ("Samstag", 2),
        ("Sonntag", 1),
    ]
    assert out["callout"]["style"] == "warning"
    assert [i["title"] for i in out["accordion"]["items"]] == ["Ordnung"]
    assert out["images"]["items"][0]["image"]["url"] and out["images"]["columns"] == 4
    assert [i["label"] for i in out["downloads"]["items"]] == ["Schießordnung"]
    # Ohne Online-Antrag gibt es keinen Abschnitt „Mitglied werden“
    assert "join" not in out


def test_mitglied_werden_nur_mit_online_antrag(club, site, manager):
    with rls_bypass():
        ApplicationForm.objects.create(organization=club, public_key="antrag-x", enabled=True)
    site.blocks = {**site.blocks, "join": True}
    site.save()
    resp = put(manager, club, [custom("j", "join", {"title": "Mach mit", "label": ""})])
    assert resp.status_code == 200, resp.content
    out = [s for s in layout() if s.get("kind") == "join"]
    assert out and out[0]["title"] == "Mach mit" and out[0]["target"]


@pytest.mark.parametrize(
    "kind,data",
    [
        ("donation", {"iban": "keine"}),
        ("donation", {"goal": -5}),
        ("donation", {"goal": "viel"}),
        ("table", {"head": []}),
        ("table", {"head": ["a"] * 7}),
        ("columns", {"items": [{}, {}, {}]}),
        ("images", {"items": [{}] * 9}),
        ("downloads", {"documents": list(range(11))}),
    ],
)
def test_pruefung(club, site, manager, kind, data):
    assert put(manager, club, [custom("x", kind, data)]).status_code == 400
