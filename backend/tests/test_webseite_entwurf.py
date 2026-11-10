"""Entwurf der Gestaltung mit Vorschau, Veröffentlichen und früheren Fassungen
(Konzept webseite-baukasten G2, Ralf 10.11.2026). Alle Daten erfunden."""

import pytest
from django.test import Client

from website import services
from website.models import DesignVersion, Website, WebsiteImage

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "entwurf-a"


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
    )


@pytest.fixture
def client_web(club, api):
    user = make_user("web-entwurf@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    return api(user)


def url(club, path=""):
    return f"/api/orgs/{club.pk}/website/{path}"


def put(c, club, data):
    return c.put(url(club), data, "application/json")


def preview_session(site):
    token = services.open_token(site)
    session, _ = services.exchange(site, token)
    return session


def public(site, preview=False):
    headers = {"HTTP_X_PREVIEW_SESSION": preview_session(site)} if preview else {}
    return Client().get(f"/api/public/site/v1/{KEY}/", **headers).json()


def test_entwurf_nur_in_der_vorschau(club, site, client_web):
    resp = put(client_web, club, {"draft": {"style": {"font": "modern"}, "design": "stage"}})
    assert resp.status_code == 200, resp.content
    data = resp.json()["website"]
    assert data["draft"] == {"design": "stage", "style": {"font": "modern"}}
    site.refresh_from_db()
    assert site.style == {} and site.design == "classic"
    # Besucher sehen den veröffentlichten Stand, die Vorschau den Entwurf
    assert public(site)["style"] == {} and public(site)["design"] == "classic"
    seen = public(site, preview=True)
    assert seen["style"] == {"font": "modern"} and seen["design"] == "stage"
    # Der Entwurf wurde nicht gespeichert, nur angezeigt
    site.refresh_from_db()
    assert site.design == "classic"


def test_entwurf_wie_veroeffentlicht_faellt_weg(club, site, client_web):
    put(client_web, club, {"draft": {"style": {"font": "modern"}}})
    data = put(client_web, club, {"draft": {"style": {}}}).json()["website"]
    assert data["draft"] == {}


@pytest.mark.parametrize(
    "draft",
    [{"style": {"font": "comic"}}, {"design": "gibtsnicht"}, {"state": "off"}, ["style"]],
)
def test_entwurf_wird_geprueft(club, site, client_web, draft):
    assert put(client_web, club, {"draft": draft}).status_code == 400
    site.refresh_from_db()
    assert site.draft == {}


def test_veroeffentlichen_mit_fassungen(club, site, client_web):
    put(client_web, club, {"draft": {"style": {"corners": "round"}}})
    resp = client_web.post(url(club, "design/publish/"))
    assert resp.status_code == 200, resp.content
    data = resp.json()["website"]
    assert data["draft"] == {} and data["style"] == {"corners": "round"}
    site.refresh_from_db()
    assert site.style == {"corners": "round"} and site.draft == {}
    assert public(site)["style"] == {"corners": "round"}
    # Erste Veröffentlichung: der bisherige Stand bleibt als ältere Fassung
    versions = data["design_versions"]
    assert len(versions) == 2
    assert versions[0]["published_by"]
    # Ohne Änderungen gibt es nichts zu veröffentlichen
    assert client_web.post(url(club, "design/publish/")).status_code == 400


def test_hoechstens_fuenf_fassungen(club, site, client_web):
    for corners in ["round", "square", "slight", "round", "square", "slight", "round"]:
        put(client_web, club, {"draft": {"style": {"corners": corners}}})
        assert client_web.post(url(club, "design/publish/")).status_code == 200
    assert DesignVersion.objects.filter(website=site).count() == 5


def test_fassung_zurueckholen_ist_erst_ein_entwurf(club, site, client_web):
    put(client_web, club, {"draft": {"style": {"nav": "text"}}})
    client_web.post(url(club, "design/publish/"))
    first = DesignVersion.objects.filter(website=site).order_by("published_at", "pk").first()
    assert first.data["style"] == {}
    data = client_web.post(url(club, f"design/versions/{first.pk}/restore/")).json()["website"]
    assert data["draft"] == {"style": {}}
    site.refresh_from_db()
    assert site.style == {"nav": "text"}
    client_web.post(url(club, "design/publish/"))
    site.refresh_from_db()
    assert site.style == {}


def test_verwerfen(club, site, client_web):
    put(client_web, club, {"draft": {"style": {"font": "festive"}}})
    data = client_web.post(url(club, "design/discard/")).json()["website"]
    assert data["draft"] == {}
    site.refresh_from_db()
    assert site.draft == {} and site.style == {}


def test_kopfbild_im_entwurf(club, site, client_web):
    image = WebsiteImage.objects.create(
        organization=club, website=site, key="kopfbild1", alt_text="Banner"
    )
    put(client_web, club, {"draft": {"header_image": image.pk}})
    assert WebsiteImage.objects.get(pk=image.pk).header is False
    assert public(site)["header_image"] is None
    # Gelöschtes Bild fällt aus dem Entwurf
    image.delete()
    assert client_web.get(url(club)).json()["website"]["draft"] == {}


def test_nur_mit_recht(club, site, api):
    user = make_user("web-leser@example.org")
    give_role(user, club, permissions=["website.content"], name="Redaktion")
    c = api(user)
    assert c.post(url(club, "design/publish/")).status_code == 403
    assert c.put(url(club), {"draft": {"style": {}}}, "application/json").status_code == 403
