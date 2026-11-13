"""Kopfbild der Webseite statt Wappen und Name (Ralf 05.11.2026, erfundene Daten)."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone
from PIL import Image

from website.models import Website, WebsiteImage

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
        organization=org,
        public_key="kopf-a",
        state="public",
        privacy_published_text="Wir speichern wenig.",
        privacy_published_at=timezone.now(),
    )


@pytest.fixture
def admin(orgs, api):
    user = make_user("webseite@example.org")
    give_role(user, orgs["a"], permissions=["website.manage", "website.content"], name="Vorstand")
    return api(user)


def url(org, rest=""):
    return f"/api/orgs/{org.pk}/website/{rest}"


def upload(c, org, alt=""):
    buf = io.BytesIO()
    Image.new("RGB", (1200, 300), "navy").save(buf, "JPEG")
    f = SimpleUploadedFile("banner.jpg", buf.getvalue(), content_type="image/jpeg")
    resp = c.post(url(org, "images/"), {"file": f, "alt_text": alt})
    assert resp.status_code == 201, resp.content
    return resp.json()


def info():
    return Client().get("/api/public/site/v1/kopf-a/").json()


def test_kopfbild_setzen_und_entfernen(orgs, admin, site):
    org = orgs["a"]
    first = upload(admin, org)
    second = upload(admin, org, alt="Banner der Kapelle")
    key = WebsiteImage.objects.get(pk=first["id"]).public_key
    # Ohne Kopfbild: nichts in den Grunddaten, Bild nicht öffentlich
    assert info()["header_image"] is None
    assert Client().get(f"/api/public/site/v1/kopf-a/images/{key}/").status_code == 404

    resp = admin.put(url(org), {"header_image": first["id"]}, "application/json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["website"]["header_image"] == first["id"]
    header = info()["header_image"]
    assert header["url"].endswith(f"images/{key}/")
    # Ohne eigenen Alternativtext steht der Vereinsname dort
    assert header["alt"] == org.name
    assert Client().get(f"/api/public/site/v1/kopf-a/images/{key}/").status_code == 200
    usage = admin.get(url(org, f"images/{first['id']}/")).json()["usage"]
    assert any(u.get("header") for u in usage)

    # Höchstens ein Kopfbild: das neue ersetzt das alte
    admin.put(url(org), {"header_image": second["id"]}, "application/json")
    assert list(WebsiteImage.objects.filter(header=True).values_list("pk", flat=True)) == [
        second["id"]
    ]
    assert info()["header_image"]["alt"] == "Banner der Kapelle"
    assert Client().get(f"/api/public/site/v1/kopf-a/images/{key}/").status_code == 404

    admin.put(url(org), {"header_image": None}, "application/json")
    assert info()["header_image"] is None
    assert not WebsiteImage.objects.filter(header=True).exists()


def test_fremdes_bild_abgelehnt(orgs, admin, site):
    resp = admin.put(url(orgs["a"]), {"header_image": 999999}, "application/json")
    assert resp.status_code == 400


def test_kopfbild_fuer_schmale_bildschirme(orgs, admin, site):
    """Webseite #73: optionale Fassung fürs Handy, nur zusammen mit einem Kopfbild."""
    org = orgs["a"]
    wide = upload(admin, org)
    narrow = upload(admin, org, alt="Banner kompakt")
    key = WebsiteImage.objects.get(pk=narrow["id"]).public_key
    assert info()["header_image_narrow"] is None

    resp = admin.put(url(org), {"header_image_narrow": narrow["id"]}, "application/json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["website"]["header_image_narrow"] == narrow["id"]
    # Ohne Kopfbild bleibt es bei Wappen und Name, auch auf dem Handy
    assert info()["header_image"] is None
    assert info()["header_image_narrow"] is None
    assert Client().get(f"/api/public/site/v1/kopf-a/images/{key}/").status_code == 404

    admin.put(url(org), {"header_image": wide["id"]}, "application/json")
    data = info()
    assert data["header_image"]["url"] != data["header_image_narrow"]["url"]
    assert data["header_image_narrow"]["url"].endswith(f"images/{key}/")
    assert data["header_image_narrow"]["alt"] == "Banner kompakt"
    assert Client().get(f"/api/public/site/v1/kopf-a/images/{key}/").status_code == 200
    usage = admin.get(url(org, f"images/{narrow['id']}/")).json()["usage"]
    assert any(u.get("header") for u in usage)
    # Beide Kopfbilder unabhängig: das Kopfbild zu ändern lässt die Handyfassung stehen
    assert WebsiteImage.objects.get(pk=narrow["id"]).header_narrow
    assert not WebsiteImage.objects.get(pk=narrow["id"]).header

    admin.put(url(org), {"header_image_narrow": None}, "application/json")
    assert info()["header_image_narrow"] is None
    assert info()["header_image"] is not None
    assert not WebsiteImage.objects.filter(header_narrow=True).exists()


def test_kopfbild_schmal_fremdes_bild_abgelehnt(orgs, admin, site):
    resp = admin.put(url(orgs["a"]), {"header_image_narrow": 999999}, "application/json")
    assert resp.status_code == 400


def test_kopfbild_schmal_im_entwurf(orgs, admin, site):
    org = orgs["a"]
    wide = upload(admin, org)
    narrow = upload(admin, org)
    admin.put(url(org), {"header_image": wide["id"]}, "application/json")
    resp = admin.put(url(org), {"draft": {"header_image_narrow": narrow["id"]}}, "application/json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["website"]["draft"] == {"header_image_narrow": narrow["id"]}
    # Öffentlich noch nicht
    assert info()["header_image_narrow"] is None
    resp = admin.post(url(org, "design/publish/"))
    assert resp.status_code == 200, resp.content
    assert info()["header_image_narrow"]["url"]
