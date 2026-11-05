"""Webseite für eine Kapelle (Ralf 05.11.2026): Mitgliederlisten, Gedenken, Instrument,
Anschrift, eigene Überschriften, Suche, Repertoire und Dokumente (alles erfunden)."""

import datetime
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image

from access.models import Role, RoleAssignment
from members.models import ExitReason, MembershipPeriod, MemberType
from music.models import Musician, Piece, Skill
from website import menu
from website.models import PublicationConsent, Website, WebsiteDocument, WebsiteText
from website.public import SiteView

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "kapelle-a"


@pytest.fixture(autouse=True)
def private_root(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "website", "music"]
    org.save()
    return org


@pytest.fixture
def site(club):
    return Website.objects.create(organization=club, public_key=KEY, state="public")


def public(path):
    return Client().get(f"/api/public/site/v1/{KEY}/{path}")


def consent(m, category):
    PublicationConsent.objects.create(
        organization=m.organization,
        membership=m,
        category=category,
        since=datetime.date(2024, 1, 1),
        source="paper",
    )


def instrument(m, name):
    musician = Musician.objects.create(organization=m.organization, membership=m)
    Skill.objects.create(
        organization=m.organization, musician=musician, instrument=name, primary=True
    )


def on(website, **blocks):
    website.blocks = {**(website.blocks or {}), **blocks}
    website.save()


class TestMitgliederlisten:
    def test_liste_je_mitgliedsart_erst_nach_einschalten(self, club, site):
        aktiv = MemberType.objects.create(organization=club, name="aktiv", active=True)
        passiv = MemberType.objects.create(organization=club, name="passiv")
        make_member(
            club, "Berta", "Zander", member_type=aktiv, entry_date=datetime.date(2012, 4, 1)
        )
        make_member(club, "Anton", "Alt", member_type=aktiv, entry_date=datetime.date(2019, 1, 1))
        make_member(club, "Carla", "Passiv", member_type=passiv)
        # Ohne Schalter keine Liste
        assert public("members/aktiv/").status_code == 404
        on(site, members=True)
        assert public("members/aktiv/").status_code == 404
        on(site, **{f"membertype:{aktiv.pk}": True})
        data = public("members/aktiv/").json()
        assert [m["name"] for m in data["members"]] == ["Anton Alt", "Berta Zander"]
        assert [m["since"] for m in data["members"]] == [2019, 2012]
        assert public("members/passiv/").status_code == 404
        # Menü: „Mitglieder“ mit der eingeschalteten Liste (einziger Unterpunkt steht oben)
        nav = menu.public_nav(SiteView(site))
        assert {"key": "membertype", "label": "aktiv", "id": "aktiv"} in nav

    def test_widerspruch_eigener_name_und_ohne_jahr(self, club, site):
        aktiv = MemberType.objects.create(organization=club, name="aktiv", active=True)
        m = make_member(club, "Dora", "Nein", member_type=aktiv)
        make_member(club, "Emil", "Ja", member_type=aktiv)
        consent(m, PublicationConsent.Category.NAME)  # Widerspruch
        site.block_names = {f"membertype:{aktiv.pk}": "Aktive"}
        site.show_member_since = False
        site.save()
        on(site, members=True, **{f"membertype:{aktiv.pk}": True})
        data = public("members/aktive/").json()
        assert data["title"] == "Aktive"
        assert data["members"] == [{"name": "Emil Ja", "photo_url": None}]

    def test_ausgetretene_fehlen_verstorbene_im_gedenken(self, club, site):
        aktiv = MemberType.objects.create(organization=club, name="aktiv", active=True)
        gone = make_member(club, "Fritz", "Fort", member_type=aktiv)
        died = make_member(
            club, "Gerd", "Gestorben", member_type=aktiv, entry_date=datetime.date(2009, 6, 1)
        )
        make_member(club, "Hans", "Da", member_type=aktiv)
        MembershipPeriod.objects.filter(membership=gone).update(
            exit_date=datetime.date(2020, 1, 1), exit_reason=ExitReason.EXIT
        )
        MembershipPeriod.objects.filter(membership=died).update(
            exit_date=datetime.date(2023, 3, 1), exit_reason=ExitReason.DEATH
        )
        on(site, members=True, memorial=True, **{f"membertype:{aktiv.pk}": True})
        names = [m["name"] for m in public("members/aktiv/").json()["members"]]
        assert names == ["Hans Da"]
        memorial = public("memorial/").json()
        assert memorial["members"] == [
            {"name": "Gerd Gestorben", "photo_url": None, "died": 2023, "since": 2009}
        ]
        assert memorial["intro"] is None
        WebsiteText.objects.create(
            organization=club,
            website=site,
            kind=WebsiteText.Kind.PAGE,
            slug=menu.MEMORIAL_SLUG,
            title="In Gedenken",
            published_title="In Gedenken",
            published_body="Wir denken an sie.",
            published_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        )
        assert public("memorial/").json()["intro"]["text"] == "Wir denken an sie."
        # Die Einleitung ist kein eigener Menüpunkt
        assert not any(k.startswith("page:") for k in menu.items(site))


class TestVorstand:
    def test_instrument_und_anschrift_nur_mit_schalter_und_einwilligung(self, club, site):
        m = make_member(club, "Ida", "Horn")
        role = Role.objects.create(organization=club, name="1. Vorsitzende", on_website=True)
        RoleAssignment.objects.create(
            organization=club, role=role, membership=m, valid_from=datetime.date(2020, 1, 1)
        )
        instrument(m, "Tenorhorn")
        holder = public("board/").json()["roles"][0]["holders"][0]
        assert "instrument" not in holder and "address" not in holder
        site.show_instrument = True
        site.show_address = True
        site.save()
        holder = public("board/").json()["roles"][0]["holders"][0]
        assert holder["instrument"] == "Tenorhorn"
        assert "address" not in holder  # ohne Einwilligung
        consent(m, PublicationConsent.Category.ADDRESS)
        holder = public("board/").json()["roles"][0]["holders"][0]
        assert holder["address"] == {
            "street": "Lindenweg 4",
            "postal_code": "12345",
            "city": "Musterstadt",
        }


class TestMenue:
    def test_eigene_ueberschrift_ueber_die_verwaltung(self, club, site, api):
        site.state = "maintenance"  # öffentlich verlangt erst Datenschutzhinweise
        site.save()
        user = make_user("web@example.org")
        give_role(user, club, permissions=["website.manage"], name="Webseite")
        c = api(user)
        menu_value = [
            {"key": "heading:1", "children": [{"key": "events"}, {"key": "contact"}]},
            {"key": "board", "children": []},
        ]
        resp = c.put(
            f"/api/orgs/{club.pk}/website/",
            {"block_names": {"heading:1": "Kapelle"}, "menu": menu_value},
            "application/json",
        )
        assert resp.status_code == 200, resp.content
        nav = menu.public_nav(SiteView(Website.objects.get(pk=site.pk)))
        top = nav[0]
        assert top["label"] == "Kapelle" and top["heading"] is True
        assert [c["key"] for c in top["children"]] == ["events", "contact"]
        # Name leer: Überschrift weg, die Unterpunkte bleiben im Menü
        resp = c.put(
            f"/api/orgs/{club.pk}/website/", {"block_names": {"heading:1": ""}}, "application/json"
        )
        assert resp.status_code == 200
        nav = menu.public_nav(SiteView(Website.objects.get(pk=site.pk)))
        assert "Kapelle" not in [n["label"] for n in nav]
        assert {"events", "contact"} <= {n["key"] for n in nav}
        bad = c.put(
            f"/api/orgs/{club.pk}/website/",
            {"block_names": {"heading:x": "Nein"}},
            "application/json",
        )
        assert bad.status_code == 400


class TestSucheUndRepertoire:
    def test_suche_nur_mit_schalter(self, club, site):
        WebsiteText.objects.create(
            organization=club,
            website=site,
            kind=WebsiteText.Kind.PAGE,
            slug="wappen",
            title="Wappen",
            published_title="Unser Wappen",
            published_body="Die **Lyra** auf blauem Grund.",
            published_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        )
        assert public("search/?q=lyra").status_code == 404
        on(site, search=True)
        hits = public("search/?q=LYRA blau").json()["results"]
        assert hits == [
            {
                "kind": "page",
                "slug": "wappen",
                "title": "Unser Wappen",
                "text": "Die Lyra auf blauem Grund.",
            }
        ]
        assert public("search/?q=x").json()["results"] == []

    def test_repertoire_nur_angehakte_stuecke(self, club, site):
        Piece.objects.create(
            organization=club, title="Zapfenstreich", composer="Unbekannt", on_website=True
        )
        Piece.objects.create(
            organization=club, title="Alte Kameraden", composer="C. Teike", on_website=True
        )
        Piece.objects.create(organization=club, title="Nur Probe")
        assert public("repertoire/").status_code == 404
        on(site, repertoire=True)
        pieces = public("repertoire/").json()["pieces"]
        assert [p["title"] for p in pieces] == ["Alte Kameraden", "Zapfenstreich"]


def jpg():
    buf = io.BytesIO()
    Image.new("RGB", (400, 600), "white").save(buf, "JPEG")
    return SimpleUploadedFile("artikel.jpg", buf.getvalue(), content_type="image/jpeg")


class TestDokumente:
    def test_presse_hochladen_und_oeffentlich(self, club, site, api):
        user = make_user("presse@example.org")
        give_role(user, club, permissions=["website.content"], name="Schriftführer")
        c = api(user)
        base = f"/api/orgs/{club.pk}/website/documents/"
        resp = c.post(
            base, {"file": jpg(), "title": "Konzert", "source": "Musterblatt", "date": "2019-05-02"}
        )
        assert resp.status_code == 201, resp.content
        doc = resp.json()
        assert doc["kind"] == "image" and doc["section"] == "press"
        bad = c.post(base, {"file": SimpleUploadedFile("x.txt", b"hallo"), "title": "Text"})
        assert bad.status_code == 400
        assert public("documents/?section=press").status_code == 404
        on(site, press=True)
        items = public("documents/?section=press").json()["documents"]
        assert [(d["title"], d["source"], d["date"]) for d in items] == [
            ("Konzert", "Musterblatt", "2019-05-02")
        ]
        token = items[0]["id"]
        assert public(f"files/{token}/").status_code == 200
        assert public(f"files/{token}/?size=small").status_code == 200
        # Ausgeblendet: weder in der Liste noch als Datei
        c.patch(f"{base}{doc['id']}/", {"published": False}, "application/json")
        assert public("documents/?section=press").json()["documents"] == []
        assert public(f"files/{token}/").status_code == 404
        assert c.delete(f"{base}{doc['id']}/").status_code == 204
        assert not WebsiteDocument.objects.exists()
