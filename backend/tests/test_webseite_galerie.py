"""Galerie der Webseite: Alben, Unteralben, Bilder und öffentliche Schnittstelle (erfunden)."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image

from website.models import GalleryAlbum, GalleryItem, Website, WebsiteImage

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
    return Website.objects.create(
        organization=org, public_key="galerie-a", state="public", blocks={"gallery": True}
    )


@pytest.fixture
def editor(orgs):
    user = make_user("bilder@example.org")
    give_role(user, orgs["a"], permissions=["website.content"], name="Schriftführer")
    return user


def url(org, rest=""):
    return f"/api/orgs/{org.pk}/website/{rest}"


def public(path):
    return Client().get(f"/api/public/site/v1/galerie-a/{path}")


def jpg(color="red"):
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), color).save(buf, "JPEG")
    return SimpleUploadedFile("foto.jpg", buf.getvalue(), content_type="image/jpeg")


def upload(c, org, color="red", caption=""):
    resp = c.post(url(org, "images/"), {"file": jpg(color), "caption": caption})
    assert resp.status_code == 201, resp.content
    return resp.json()


def post(c, org, rest, data):
    return c.post(url(org, rest), data, "application/json")


def put(c, org, rest, data):
    return c.put(url(org, rest), data, "application/json")


class TestVerwaltung:
    def test_album_anlegen_adresse_aus_titel(self, orgs, editor, api, site):
        c = api(editor)
        resp = post(c, orgs["a"], "albums/", {"title": "Schützenfest 2024"})
        assert resp.status_code == 201, resp.content
        assert resp.json()["slug"] == "schuetzenfest-2024"
        assert resp.json()["published"] is False
        again = post(c, orgs["a"], "albums/", {"title": "Schützenfest 2024"}).json()
        assert again["slug"] == "schuetzenfest-2024-2"
        dup = post(c, orgs["a"], "albums/", {"title": "X", "slug": "schuetzenfest-2024"})
        assert dup.status_code == 400
        bad = post(c, orgs["a"], "albums/", {"title": "X", "slug": "Groß!"})
        assert bad.status_code == 400
        assert post(c, orgs["a"], "albums/", {"title": " "}).status_code == 400

    def test_hoechstens_zwei_ebenen(self, orgs, editor, api, site):
        c = api(editor)
        top = post(c, orgs["a"], "albums/", {"title": "2024"}).json()
        sub = post(c, orgs["a"], "albums/", {"title": "Fest", "parent": top["id"]})
        assert sub.status_code == 201
        third = post(c, orgs["a"], "albums/", {"title": "Zu tief", "parent": sub.json()["id"]})
        assert third.status_code == 400
        # Album mit Unteralben wird nicht selbst Unteralbum
        other = post(c, orgs["a"], "albums/", {"title": "2023"}).json()
        assert put(c, orgs["a"], f"albums/{top['id']}/", {"parent": other["id"]}).status_code == 400

    def test_fremde_alben_und_bilder(self, orgs, editor, board_b, api, site):
        c = api(editor)
        album = post(c, orgs["a"], "albums/", {"title": "2024"}).json()
        image = upload(c, orgs["a"])
        # andere Webseite
        orgs["b"].enabled_modules = ["members", "website"]
        orgs["b"].save()
        Website.objects.create(organization=orgs["b"], public_key="galerie-b")
        cb = api(board_b)
        assert cb.get(url(orgs["b"], f"albums/{album['id']}/")).status_code == 404
        resp = post(cb, orgs["b"], "albums/", {"title": "B", "parent": album["id"]})
        assert resp.status_code == 400
        theirs = post(cb, orgs["b"], "albums/", {"title": "B"}).json()
        resp = put(cb, orgs["b"], f"albums/{theirs['id']}/", {"images": [image["id"]]})
        assert resp.status_code == 400
        resp = put(cb, orgs["b"], f"albums/{theirs['id']}/", {"cover": image["id"]})
        assert resp.status_code == 400

    def test_bilder_anfuegen_ordnen_entfernen(self, orgs, editor, api, site):
        c = api(editor)
        album = post(c, orgs["a"], "albums/", {"title": "2024", "image_order": "manual"}).json()
        a, b, d = (upload(c, orgs["a"], col) for col in ("red", "blue", "green"))
        data = post(c, orgs["a"], f"albums/{album['id']}/images/", {"images": [a["id"], b["id"]]})
        assert [i["id"] for i in data.json()["images"]] == [a["id"], b["id"]]
        # schon enthaltene bleiben, neue hinten
        data = post(c, orgs["a"], f"albums/{album['id']}/images/", {"images": [b["id"], d["id"]]})
        assert [i["id"] for i in data.json()["images"]] == [a["id"], b["id"], d["id"]]
        data = put(c, orgs["a"], f"albums/{album['id']}/", {"images": [d["id"], a["id"]]}).json()
        assert [i["id"] for i in data["images"]] == [d["id"], a["id"]]
        # entferntes Bild bleibt in der Bilderverwaltung
        assert WebsiteImage.objects.filter(pk=b["id"]).exists()
        listing = c.get(url(orgs["a"], "albums/")).json()
        assert listing["albums"][0]["image_count"] == 2 and listing["block_on"] is True
        assert put(c, orgs["a"], f"albums/{album['id']}/", {"images": "x"}).status_code == 400

    def test_bild_im_album_beim_loeschen_genannt(self, orgs, editor, api, site):
        c = api(editor)
        album = post(c, orgs["a"], "albums/", {"title": "Fest"}).json()
        image = upload(c, orgs["a"])
        post(c, orgs["a"], f"albums/{album['id']}/images/", {"images": [image["id"]]})
        detail = c.get(url(orgs["a"], f"images/{image['id']}/")).json()
        assert detail["used"] is True
        assert detail["usage"][0]["album"] == album["id"]
        assert detail["usage"][0]["label"] == "Galerie: Fest"
        resp = c.delete(url(orgs["a"], f"images/{image['id']}/"))
        assert resp.status_code == 409 and "Galerie: Fest" in resp.json()["detail"]
        assert c.delete(url(orgs["a"], f"images/{image['id']}/?trotzdem=1")).status_code == 204
        assert not GalleryItem.objects.exists()

    def test_reihenfolge_und_loeschen(self, orgs, editor, api, site):
        c = api(editor)
        x = post(c, orgs["a"], "albums/", {"title": "2023"}).json()
        y = post(c, orgs["a"], "albums/", {"title": "2024"}).json()
        sub = post(c, orgs["a"], "albums/", {"title": "Fest", "parent": y["id"]}).json()
        c.put(url(orgs["a"], "albums/"), {"gallery_order": "manual"}, "application/json")
        resp = post(c, orgs["a"], "albums/reorder/", {"ids": [y["id"], x["id"]]})
        assert resp.status_code == 200, resp.content
        titles = [a["title"] for a in c.get(url(orgs["a"], "albums/")).json()["albums"]]
        assert titles == ["2024", "Fest", "2023"]
        assert c.delete(url(orgs["a"], f"albums/{y['id']}/")).status_code == 204
        assert not GalleryAlbum.objects.filter(pk__in=[y["id"], sub["id"]]).exists()

    def test_ohne_recht(self, orgs, api, site):
        user = make_user("leser@example.org")
        give_role(user, orgs["a"], permissions=["website.view"], name="Leser")
        resp = post(api(user), orgs["a"], "albums/", {"title": "2024"})
        assert resp.status_code in (403, 404)


class TestSortierung:
    def test_bilder_nach_aufnahmedatum_und_dateiname(self, orgs, editor, api, site):
        import datetime

        from django.utils import timezone

        c = api(editor)
        album = post(c, orgs["a"], "albums/", {"title": "Fest"}).json()
        imgs = [upload(c, orgs["a"], col, caption=cap) for col, cap in
                (("red", "Cäsar"), ("blue", "anton"), ("green", "Bert"))]  # fmt: skip
        ids = [i["id"] for i in imgs]
        post(c, orgs["a"], f"albums/{album['id']}/images/", {"images": ids})
        day = lambda d: timezone.make_aware(datetime.datetime(2024, 8, d, 12))  # noqa: E731
        for pk, d, name in zip(ids, (3, 1, 2), ("c.jpg", "a.jpg", "b.jpg"), strict=True):
            WebsiteImage.objects.filter(pk=pk).update(taken_at=day(d), file_name=name)
        order = lambda o: [  # noqa: E731
            i["id"]
            for i in put(c, orgs["a"], f"albums/{album['id']}/", {"image_order": o}).json()[
                "images"
            ]
        ]
        assert order("taken") == [ids[1], ids[2], ids[0]]
        assert order("taken_desc") == [ids[0], ids[2], ids[1]]
        assert order("name_desc") == [ids[0], ids[2], ids[1]]
        assert order("caption") == [ids[1], ids[2], ids[0]]
        assert order("manual") == ids
        assert put(c, orgs["a"], f"albums/{album['id']}/", {"image_order": "x"}).status_code == 400

    def test_aufnahmedatum_aus_der_kamera(self, orgs, editor, api, site):
        buf = io.BytesIO()
        exif = Image.Exif()
        exif.get_ifd(0x8769)[0x9003] = "2019:06:15 14:30:00"
        Image.new("RGB", (400, 300), "red").save(buf, "JPEG", exif=exif)
        f = SimpleUploadedFile("IMG_0001.jpg", buf.getvalue(), content_type="image/jpeg")
        data = api(editor).post(url(orgs["a"], "images/"), {"file": f}).json()
        image = WebsiteImage.objects.get(pk=data["id"])
        assert image.taken_at.year == 2019 and image.file_name == "IMG_0001.jpg"
        # die gespeicherte Datei bleibt ohne Metadaten
        with Image.open(image.file.open("rb")) as img:
            assert not img.getexif()

    def test_alben_sortieren(self, orgs, editor, api, site):
        c = api(editor)
        for title, date in (("Alt", "2019-05-01"), ("Neu", "2024-05-01"), ("Ohne", None)):
            a = post(c, orgs["a"], "albums/", {"title": title, "date": date}).json()
            put(c, orgs["a"], f"albums/{a['id']}/", {"published": True})
        assert [a["title"] for a in public("galleries/").json()["albums"]] == ["Neu", "Alt", "Ohne"]
        resp = c.put(url(orgs["a"], "albums/"), {"gallery_order": "title"}, "application/json")
        assert resp.status_code == 200 and resp.json()["gallery_order"] == "title"
        assert [a["title"] for a in resp.json()["albums"]] == ["Alt", "Neu", "Ohne"]
        assert [a["title"] for a in public("galleries/").json()["albums"]] == ["Alt", "Neu", "Ohne"]
        bad = c.put(url(orgs["a"], "albums/"), {"gallery_order": "x"}, "application/json")
        assert bad.status_code == 400


class TestOeffentlich:
    @pytest.fixture
    def alben(self, orgs, editor, api, site):
        c = api(editor)
        org = orgs["a"]
        top = post(c, org, "albums/", {"title": "2024", "date": "2024-08-30"}).json()
        fest = post(c, org, "albums/", {"title": "Schützenfest", "parent": top["id"]}).json()
        hidden = post(c, org, "albums/", {"title": "Entwurf"}).json()
        a = upload(c, org, "red", caption="Umzug")
        b = upload(c, org, "blue", caption="Parade")
        secret = upload(c, org, "green")
        post(c, org, f"albums/{fest['id']}/images/", {"images": [a["id"], b["id"]]})
        post(c, org, f"albums/{hidden['id']}/images/", {"images": [secret["id"]]})
        for album in (top, fest):
            put(c, org, f"albums/{album['id']}/", {"published": True})
        keys = {i["id"]: WebsiteImage.objects.get(pk=i["id"]).public_key for i in (a, b, secret)}
        return {"c": c, "top": top, "fest": fest, "hidden": hidden, "a": a, "b": b,
                "secret": secret, "keys": keys}  # fmt: skip

    def test_liste_und_album(self, alben):
        data = public("galleries/").json()
        assert [a["slug"] for a in data["albums"]] == ["2024"]
        top = data["albums"][0]
        assert top["year"] == 2024 and top["images"] == 2 and top["albums"] == 1
        # Titelbild aus dem Unteralbum
        assert top["cover"]["key"] == alben["keys"][alben["a"]["id"]]
        album = public("galleries/2024/").json()
        assert album["albums"][0]["slug"] == "schuetzenfest"
        fest = public("galleries/schuetzenfest/").json()
        assert fest["parent"] == {"slug": "2024", "title": "2024"}
        assert [i["caption"] for i in fest["images"]] == ["Umzug", "Parade"]
        assert '"id": ' not in public("galleries/schuetzenfest/").content.decode()

    def test_unveroeffentlicht_unsichtbar(self, alben, orgs):
        assert public("galleries/entwurf/").status_code == 404
        secret = alben["keys"][alben["secret"]["id"]]
        assert public(f"images/{secret}/").status_code == 404
        shown = alben["keys"][alben["a"]["id"]]
        assert public(f"images/{shown}/").status_code == 200
        # Oberalbum zurückgenommen: Unteralbum und seine Bilder verschwinden
        put(alben["c"], orgs["a"], f"albums/{alben['top']['id']}/", {"published": False})
        assert public("galleries/schuetzenfest/").status_code == 404
        assert public(f"images/{shown}/").status_code == 404

    def test_bildunterschriften_abschaltbar(self, alben, orgs):
        put(alben["c"], orgs["a"], f"albums/{alben['fest']['id']}/", {"show_captions": False})
        fest = public("galleries/schuetzenfest/").json()
        assert [i["caption"] for i in fest["images"]] == ["", ""]
        assert fest["images"][0]["alt"] == "Umzug"

    def test_bereich_aus(self, alben, site):
        site.blocks = {"gallery": False}
        site.save()
        assert public("galleries/").status_code == 404
        assert public("galleries/2024/").status_code == 404
        shown = alben["keys"][alben["a"]["id"]]
        assert public(f"images/{shown}/").status_code == 404

    def test_menue(self, alben, site):
        nav = Client().get("/api/public/site/v1/galerie-a/").json()["nav"]
        assert any(n["key"] == "gallery" for n in nav)
        GalleryAlbum.objects.update(published=False)
        nav = Client().get("/api/public/site/v1/galerie-a/").json()["nav"]
        assert not any(n["key"] == "gallery" for n in nav)

    def test_neue_webseite_ohne_galerie(self, orgs):
        site = Website.objects.create(organization=orgs["b"], public_key="neu-b")
        assert site.block_on("gallery") is False
        assert site.block_on("events") is True
