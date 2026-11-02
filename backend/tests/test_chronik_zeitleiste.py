"""Chronik als Zeitleiste: Einträge mit Jahr oder Zeitraum (Ralf 02.11., alles erfunden)."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from openpyxl import Workbook
from PIL import Image

from website.models import Website, WebsiteImage, WebsiteText

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def private_root(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def site(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "website"]
    org.save()
    return Website.objects.create(organization=org, public_key=Website.new_key(), state="public")


@pytest.fixture
def editor(orgs):
    user = make_user("chronik@example.org")
    give_role(user, orgs["a"], permissions=["website.content"], name="Schriftführer")
    return user


def url(org, rest=""):
    return f"/api/orgs/{org.pk}/website/{rest}"


def png():
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "blue").save(buf, "PNG")
    return SimpleUploadedFile("bild.png", buf.getvalue(), content_type="image/png")


def chronicle(c, org, slug="geschichte"):
    resp = c.post(
        url(org, "texts/"),
        {"kind": "page", "slug": slug, "title": "Chronik", "body": "Kurz vorweg."},
        "application/json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()["id"]


ENTRIES = [
    {"year": 1949, "title": "Neuanfang", "text": "Erstes Fest nach dem Krieg."},
    {"year": 1920, "title": "Gründung", "text": ""},
    {"year": 1939, "until": 1948, "title": "Ruhezeit", "text": "Kaum Vereinsleben."},
]


class TestZeitleiste:
    def test_entwurf_veroeffentlichen_und_webseite(self, orgs, editor, api, site):
        c = api(editor)
        pk = chronicle(c, orgs["a"])
        assert c.get(url(orgs["a"], f"texts/{pk}/")).json()["has_timeline"] is True
        resp = c.put(url(orgs["a"], f"texts/{pk}/"), {"timeline": ENTRIES}, "application/json")
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert data["has_changes"] is True
        # Gespeichert in fester Form, Reihenfolge wie eingegeben
        assert data["timeline"][1] == {
            "kind": "event",
            "year": 1920,
            "until": None,
            "title": "Gründung",
            "text": "",
            "image": None,
        }
        public = f"/api/public/site/v1/{site.public_key}/pages/geschichte/"
        assert Client().get(public).status_code == 404  # noch nicht veröffentlicht
        c.post(url(orgs["a"], f"texts/{pk}/publish/"))
        page = Client().get(public).json()
        # Webseite: nach Jahren sortiert, Zeitraum mit „bis“
        assert [(e["year"], e["until"]) for e in page["timeline"]] == [
            (1920, None),
            (1939, 1948),
            (1949, None),
        ]
        # Entwurf ändern: veröffentlichte Zeitleiste bleibt
        c.put(url(orgs["a"], f"texts/{pk}/"), {"timeline": ENTRIES[:1]}, "application/json")
        assert len(Client().get(public).json()["timeline"]) == 3
        # Frühere Fassung bringt die Zeitleiste zurück
        rev = c.get(url(orgs["a"], f"texts/{pk}/")).json()["revisions"][0]["id"]
        data = c.post(url(orgs["a"], f"texts/{pk}/revisions/{rev}/restore/")).json()
        assert len(data["timeline"]) == 3

    @pytest.mark.parametrize(
        "entry",
        [
            {"year": None, "title": "Ohne Jahr"},
            {"year": 999, "title": "Zu früh"},
            {"year": 1950, "title": ""},
            {"year": 1950, "until": 1940, "title": "Rückwärts"},
            {"year": 1950, "title": "x" * 121},
            {"year": 1950, "title": "Lang", "text": "x" * 401},
            {"year": 1950, "title": "Bild", "image": 999999},
            {"year": 1950, "title": "Bild", "image": "1"},
        ],
    )
    def test_eintraege_pruefen(self, orgs, editor, api, site, entry):
        c = api(editor)
        pk = chronicle(c, orgs["a"])
        resp = c.put(url(orgs["a"], f"texts/{pk}/"), {"timeline": [entry]}, "application/json")
        assert resp.status_code == 400, resp.content

    def test_kapitel(self, orgs, editor, api, site):
        c = api(editor)
        image = c.post(url(orgs["a"], "images/"), {"file": png()}).json()
        pk = chronicle(c, orgs["a"])
        entries = [
            *ENTRIES,
            {"kind": "chapter", "year": 1920, "until": 1938, "title": "Gründerjahre"},
            {"kind": "chapter", "year": 1949, "title": "Nachkriegszeit", "image": image["id"]},
        ]
        resp = c.put(url(orgs["a"], f"texts/{pk}/"), {"timeline": entries}, "application/json")
        assert resp.status_code == 200, resp.content
        assert resp.json()["timeline"][-1]["image"] is None  # Kapitel ohne Bild
        bad = [{"kind": "anderes", "year": 1950, "title": "x"}]
        resp = c.put(url(orgs["a"], f"texts/{pk}/"), {"timeline": bad}, "application/json")
        assert resp.status_code == 400
        c.post(url(orgs["a"], f"texts/{pk}/publish/"))
        public = f"/api/public/site/v1/{site.public_key}/pages/geschichte/"
        timeline = Client().get(public).json()["timeline"]
        # Kapitel steht vor den Ereignissen seines Jahres
        assert [(e["kind"], e["title"]) for e in timeline] == [
            ("chapter", "Gründerjahre"),
            ("event", "Gründung"),
            ("event", "Ruhezeit"),
            ("chapter", "Nachkriegszeit"),
            ("event", "Neuanfang"),
        ]

    def test_gleiches_jahr_bis_entfaellt(self, orgs, editor, api, site):
        c = api(editor)
        pk = chronicle(c, orgs["a"])
        data = c.put(
            url(orgs["a"], f"texts/{pk}/"),
            {"timeline": [{"year": 1950, "until": 1950, "title": "Fest"}]},
            "application/json",
        ).json()
        assert data["timeline"][0]["until"] is None

    def test_nur_in_der_chronik(self, orgs, editor, api, site):
        c = api(editor)
        pk = chronicle(c, orgs["a"], slug="anfahrt")
        assert c.get(url(orgs["a"], f"texts/{pk}/")).json()["has_timeline"] is False
        resp = c.put(url(orgs["a"], f"texts/{pk}/"), {"timeline": ENTRIES}, "application/json")
        assert resp.status_code == 400
        assert c.post(url(orgs["a"], f"texts/{pk}/timeline-import/")).status_code == 404

    def test_bild_in_der_zeitleiste(self, orgs, editor, api, site):
        c = api(editor)
        image = c.post(url(orgs["a"], "images/"), {"file": png(), "alt_text": "Fahne"}).json()
        pk = chronicle(c, orgs["a"])
        entries = [{"year": 1995, "title": "Neue Fahne", "image": image["id"]}]
        c.put(url(orgs["a"], f"texts/{pk}/"), {"timeline": entries}, "application/json")
        c.post(url(orgs["a"], f"texts/{pk}/publish/"))
        public = f"/api/public/site/v1/{site.public_key}/"
        entry = Client().get(f"{public}pages/geschichte/").json()["timeline"][0]
        assert entry["image"]["alt"] == "Fahne"
        # Öffentlich abrufbar und beim Löschen als verwendet gemeldet
        assert Client().get(f"{public}images/{image['key']}/").status_code == 200
        resp = c.delete(url(orgs["a"], f"images/{image['id']}/"))
        assert resp.status_code == 409
        assert resp.json()["places"] == ["Chronik: Zeitleiste"]
        # Trotzdem löschen: Eintrag bleibt, nur das Bild fällt weg
        assert c.delete(url(orgs["a"], f"images/{image['id']}/?trotzdem=1")).status_code == 204
        t = WebsiteText.objects.get(pk=pk)
        assert t.timeline[0]["image"] is None and t.published_timeline[0]["image"] is None
        assert t.revisions.get().timeline[0]["image"] is None
        assert t.timeline[0]["title"] == "Neue Fahne"
        assert not WebsiteImage.objects.filter(pk=image["id"]).exists()


class TestImport:
    def xlsx(self, rows):
        wb = Workbook()
        for row in rows:
            wb.active.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        return SimpleUploadedFile(
            "chronik.xlsx",
            buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_import_liest_eintraege_und_meldet_fehler(self, orgs, editor, api, site):
        c = api(editor)
        pk = chronicle(c, orgs["a"])
        upload = self.xlsx(
            [
                ["Jahr", "bis", "Überschrift", "Text", "Art"],
                [1920, None, "Gründung", "Zwölf Schützenbrüder.", None],
                ["1939", "1948", "Ruhezeit", None, "Kapitel"],
                ["irgendwann", None, "Ohne Jahr", None, None],
                [1960, None, None, "Ohne Überschrift", None],
            ]
        )
        resp = c.post(url(orgs["a"], f"texts/{pk}/timeline-import/"), {"file": upload})
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert [(e["kind"], e["year"], e["until"], e["title"]) for e in data["entries"]] == [
            ("event", 1920, None, "Gründung"),
            ("chapter", 1939, 1948, "Ruhezeit"),
        ]
        assert [e["line"] for e in data["errors"]] == [4, 5]
        # Gespeichert wird nichts
        assert WebsiteText.objects.get(pk=pk).timeline == []

    def test_import_ohne_pflichtspalten(self, orgs, editor, api, site):
        c = api(editor)
        pk = chronicle(c, orgs["a"])
        upload = self.xlsx([["Datum", "Text"], [1920, "Gründung"]])
        resp = c.post(url(orgs["a"], f"texts/{pk}/timeline-import/"), {"file": upload})
        assert resp.status_code == 400
        assert "Überschrift" in resp.json()["file"]

    def test_import_nur_mit_recht(self, orgs, api, site, editor):
        c = api(editor)
        pk = chronicle(c, orgs["a"])
        reader = make_user("leser@example.org")
        give_role(reader, orgs["a"], permissions=["members.view"], name="Leser")
        upload = self.xlsx([["Jahr", "Überschrift"], [1920, "Gründung"]])
        resp = api(reader).post(url(orgs["a"], f"texts/{pk}/timeline-import/"), {"file": upload})
        assert resp.status_code in (403, 404)
