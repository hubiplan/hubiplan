"""White Label W1 und W2: Erscheinungsbild der Instanz ohne Anmeldung (konzepte/white-label.md)."""
# ruff: noqa: F811  (Fixture platform_admin aus test_impressum als Parameter)

import io

import pytest
from django.test import Client
from PIL import Image

from core.tenancy import tenant_context
from organizations.models import Organization, PlatformSettings

from .factories import give_role, make_org, make_user
from .test_impressum import platform_admin  # noqa: F401

pytestmark = pytest.mark.django_db
URL = "/api/public/platform/"


def platform() -> Organization:
    return Organization.platform()


def test_ohne_eigene_angaben_wie_bisher():
    platform()
    data = Client().get(URL).json()
    assert data == {
        "name": "HUBIplan",
        "short_name": "",
        "logo_url": None,
        "theme": None,
        "icon": False,
    }


def test_ohne_plattform_einheit_legt_nichts_an():
    Organization.objects.filter(type=Organization.Type.PLATFORM).delete()
    data = Client().get(URL).json()
    assert data["name"] == "HUBIplan"
    assert not Organization.objects.filter(type=Organization.Type.PLATFORM).exists()


def test_instanzname_und_farben():
    p = platform()
    p.name = "Vereinsportal Musterkreis"
    p.short_name = "Musterkreis"
    p.primary_color = "#1f4e79"
    p.save()
    resp = Client().get(URL)
    assert resp.status_code == 200
    assert "max-age" in resp["Cache-Control"]
    data = resp.json()
    assert data["name"] == "Vereinsportal Musterkreis"
    assert data["short_name"] == "Musterkreis"
    # Fehlende Zweitfarbe kommt vom Standard, Schriftfarbe ist lesbar berechnet
    assert data["theme"] == {
        "primary": "#1f4e79",
        "on_primary": "#ffffff",
        "accent": "#f2b33d",
        "on_accent": "#1d2421",
    }


def test_nur_angaben_der_plattform_keine_einheiten():
    p = platform()
    make_org("Schützenverein Musterstadt", primary_color="#7a1f1f")
    data = Client().get(URL).json()
    assert data["theme"] is None
    assert data["name"] == p.name


def test_kontrastpruefung_gilt_fuer_die_plattform():
    from organizations.serializers import ThemeSerializer

    s = ThemeSerializer(platform(), data={"primary_color": "#f2f2f2"}, partial=True)
    assert not s.is_valid()
    assert "primary_color" in s.errors


# --- W2: Symbol und Manifest ---


def _png(width: int, height: int, color=(31, 78, 121, 255)) -> io.BytesIO:
    buf = io.BytesIO()
    Image.new("RGBA", (width, height), color).save(buf, "PNG")
    buf.seek(0)
    buf.name = "symbol.png"
    return buf


def test_manifest_ohne_eigenes_symbol_wie_bisher():
    data = Client().get("/api/public/platform/manifest.webmanifest").json()
    assert data["name"] == "HUBIplan"
    assert data["theme_color"] == "#0e7c66"
    assert data["icons"][0]["src"] == "/favicon.svg"
    assert Client().get("/api/public/platform/icon-192.png").status_code == 404


def test_symbol_hochladen_und_abholen(api, platform_admin):
    p = platform()
    p.name = "Vereinsportal Musterkreis"
    p.primary_color = "#1f4e79"
    p.save()
    c = api(platform_admin)
    # Breites Bild wird quadratisch (durchsichtiger Rand oben und unten)
    resp = c.post("/api/platform/icon/", {"logo": _png(800, 400)})
    assert resp.status_code == 200, resp.content
    assert PlatformSettings.load().brand_icon
    assert Client().get(URL).json()["icon"] is True

    for name, size in (("32", 32), ("180", 180), ("192", 192), ("512", 512), ("maskable", 512)):
        r = Client().get(f"/api/public/platform/icon-{name}.png")
        assert r.status_code == 200
        assert r["Content-Type"] == "image/png"
        img = Image.open(io.BytesIO(r.content))
        assert img.size == (size, size)
    # Apple-Symbol ohne Durchsichtigkeit (iOS füllt sie schwarz)
    apple = Image.open(io.BytesIO(Client().get("/api/public/platform/icon-180.png").content))
    assert apple.mode == "RGB"
    assert Client().get("/api/public/platform/icon-64.png").status_code == 404

    manifest = Client().get("/api/public/platform/manifest.webmanifest")
    assert manifest["Content-Type"] == "application/manifest+json"
    data = manifest.json()
    assert data["name"] == "Vereinsportal Musterkreis"
    assert data["short_name"] == "Vereinsporta"
    assert data["theme_color"] == "#1f4e79"
    assert {i["src"] for i in data["icons"]} == {
        "/api/public/platform/icon-192.png",
        "/api/public/platform/icon-512.png",
        "/api/public/platform/icon-maskable.png",
    }

    assert c.delete("/api/platform/icon/").status_code == 204
    assert not PlatformSettings.load().brand_icon
    assert Client().get("/api/public/platform/icon-192.png").status_code == 404


def test_symbol_zu_klein(api, platform_admin):
    resp = api(platform_admin).post("/api/platform/icon/", {"logo": _png(200, 200)})
    assert resp.status_code == 400
    assert not PlatformSettings.load().brand_icon


def test_symbol_nur_fuer_plattformverwaltung(api):
    user = make_user("vorstand@example.org")
    resp = api(user).post("/api/platform/icon/", {"logo": _png(600, 600)})
    assert resp.status_code == 403


# --- W3: E-Mails mit dem Namen der Instanz ---


def _musterkreis() -> Organization:
    p = platform()
    p.name = "Vereinsportal Musterkreis"
    p.save()
    return p


def test_mails_ohne_eigenen_namen_wie_bisher(mailoutbox, settings):
    from accounts.invitations import send_password_link
    from outbox.mail import from_address

    assert from_address() == settings.DEFAULT_FROM_EMAIL
    platform()
    send_password_link(make_user("anna@example.org"))
    (m,) = mailoutbox
    assert m.subject == "HUBIplan: Passwort festlegen"
    assert "HUBIplan verschickt keine Startpasswörter mehr." in m.body
    assert m.from_email == settings.DEFAULT_FROM_EMAIL


def test_mails_mit_instanzname(mailoutbox, settings):
    from accounts.invitations import send_invitation, send_password_link
    from outbox import mail

    settings.DEFAULT_FROM_EMAIL = "HUBIplan <noreply@example.org>"
    _musterkreis()
    club = make_org("Schützenverein Musterstadt")
    send_password_link(make_user("anna@example.org"))
    send_invitation(make_user("bernd@example.org"), club, "Kassierer")
    mail.send("carla@example.org", "Hinweis", "Text", organization=club)
    reset, invite, note = mailoutbox
    assert reset.subject == "Vereinsportal Musterkreis: Passwort festlegen"
    assert "Vereinsportal Musterkreis verschickt keine Startpasswörter mehr." in reset.body
    assert reset.from_email == '"Vereinsportal Musterkreis" <noreply@example.org>'
    assert invite.subject == "Einladung zu Vereinsportal Musterkreis – Schützenverein Musterstadt"
    assert "bei Vereinsportal Musterkreis ein Konto angelegt" in invite.body
    assert invite.from_email == '"Vereinsportal Musterkreis" <noreply@example.org>'
    # Mails einer Einheit: Fußzeile mit Instanz, Adresse bleibt die feste (DMARC)
    assert (
        "im Auftrag von Schützenverein Musterstadt über Vereinsportal Musterkreis versandt"
        in note.body
    )
    assert note.from_email.endswith("<noreply@example.org>")


# --- W7a: Erscheinungsbild je Adresse ---

VEREIN_HOST = "mitglieder.sv-musterstadt.example"


@pytest.fixture
def adressen(settings):
    settings.ALLOWED_HOSTS = ["testserver", VEREIN_HOST, "unbekannt.example"]


def test_adresse_eintragen_und_erscheinungsbild(api, platform_admin, adressen):
    _musterkreis()
    club = make_org("Schützenverein Musterstadt", primary_color="#7a1f1f")
    c = api(platform_admin)
    resp = c.post(
        "/api/platform/addresses/",
        {"hostname": "Mitglieder.SV-Musterstadt.example.", "organization": club.pk},
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["hostname"] == VEREIN_HOST

    data = Client().get(URL, HTTP_HOST=VEREIN_HOST).json()
    assert data["name"] == "Schützenverein Musterstadt"
    assert data["unit"] == club.pk
    assert data["theme"]["primary"] == "#7a1f1f"
    # Unbekannte Adresse und Hauptadresse: Instanz wie bisher
    other = Client().get(URL, HTTP_HOST="unbekannt.example")
    assert other.json()["name"] == "Vereinsportal Musterkreis"
    assert other.json()["unit"] is None
    assert other["Vary"] == "Host"
    manifest = (
        Client().get("/api/public/platform/manifest.webmanifest", HTTP_HOST=VEREIN_HOST).json()
    )
    assert manifest["name"] == "Schützenverein Musterstadt"
    assert manifest["theme_color"] == "#7a1f1f"

    pk = resp.json()["id"]
    assert c.delete(f"/api/platform/addresses/{pk}/").status_code == 204
    assert Client().get(URL, HTTP_HOST=VEREIN_HOST).json()["unit"] is None


def test_adresse_pruefung(api, platform_admin, adressen, settings):
    from website.models import Website, WebsiteDomain

    settings.FRONTEND_URL = "https://portal.musterkreis.example"
    club = make_org("Schützenverein Musterstadt")
    c = api(platform_admin)

    def post(host):
        return c.post(
            "/api/platform/addresses/",
            {"hostname": host, "organization": club.pk},
            content_type="application/json",
        )

    assert post("kein host").status_code == 400
    assert post("portal.musterkreis.example").status_code == 400
    with tenant_context(club.pk):
        site = Website.objects.create(organization=club)
        WebsiteDomain.objects.create(
            organization=club, website=site, hostname="www.sv-musterstadt.example"
        )
    assert post("www.sv-musterstadt.example").status_code == 400
    assert post(VEREIN_HOST).status_code == 201
    assert post(VEREIN_HOST).status_code == 400
    # Die Plattform selbst bekommt keine Adresse
    resp = c.post(
        "/api/platform/addresses/",
        {"hostname": "x.example", "organization": platform().pk},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_adressen_nur_fuer_plattformverwaltung(api):
    user = make_user("vorstand@example.org")
    assert api(user).get("/api/platform/addresses/").status_code == 403


def test_symbol_je_adresse(api, adressen):
    from organizations.models import InstanceAddress

    club = make_org("Schützenverein Musterstadt")
    InstanceAddress.objects.create(hostname=VEREIN_HOST, organization=club)
    # Ohne Symbol und Wappen: kein Symbol
    assert Client().get(URL, HTTP_HOST=VEREIN_HOST).json()["icon"] is False
    # Wappen wird quadratisch zum Symbol
    from django.core.files.base import ContentFile

    club.logo.save("wappen.png", ContentFile(_png(300, 150).getvalue()), save=True)
    assert Client().get(URL, HTTP_HOST=VEREIN_HOST).json()["icon"] is True
    r = Client().get("/api/public/platform/icon-192.png", HTTP_HOST=VEREIN_HOST)
    assert r.status_code == 200
    assert Image.open(io.BytesIO(r.content)).size == (192, 192)
    # Eigenes Symbol der Einheit, hochgeladen vom Vorstand
    board = make_user("vorstand@example.org")
    with tenant_context(club.pk):
        give_role(board, club)
    resp = api(board).post(f"/api/orgs/{club.pk}/icon/", {"logo": _png(600, 600)})
    assert resp.status_code == 200, resp.content
    club.refresh_from_db()
    assert club.brand_icon
    theme = api(board).get(f"/api/orgs/{club.pk}/theme/").json()
    assert theme["has_icon"] is True
    preview = api(board).get(f"/api/orgs/{club.pk}/icon/")
    assert preview.status_code == 200
    assert Image.open(io.BytesIO(preview.content)).size == (512, 512)
    assert theme["addresses"] == [VEREIN_HOST]
    # Auf der Hauptadresse bleibt es beim (fehlenden) Symbol der Instanz
    assert Client().get("/api/public/platform/icon-192.png").status_code == 404


# --- W7b: Links in Mails auf der Adresse der Einheit ---


def _adresse(org: Organization, host: str = VEREIN_HOST):
    from organizations.models import InstanceAddress

    return InstanceAddress.objects.create(hostname=host, organization=org)


def test_basisadresse_je_einheit(settings):
    from organizations.addresses import base_url, rebase

    main = settings.FRONTEND_URL.rstrip("/")
    verband = make_org("Kreisverband Musterkreis", type_="federation")
    club = make_org("Schützenverein Musterstadt", parent=verband)
    other = make_org("Musikverein Musterdorf")
    # Ohne eingetragene Adresse: Hauptadresse
    assert base_url() == main
    assert base_url(club) == main
    _adresse(verband, "mitglieder.kreisverband.example")
    # Nächsthöhere Einheit mit eigener Adresse
    assert base_url(club) == "https://mitglieder.kreisverband.example"
    _adresse(club)
    assert base_url(club) == f"https://{VEREIN_HOST}"
    assert base_url(other) == main
    assert base_url(Organization.platform()) == main
    # Abgeschaltete Einheit: wieder die nächsthöhere
    club.is_active = False
    club.save()
    assert base_url(club) == "https://mitglieder.kreisverband.example"
    assert rebase(f"{main}/foto/abc", "https://x.example") == "https://x.example/foto/abc"
    assert rebase("https://fremd.example/a", "https://x.example") == "https://fremd.example/a"


def test_einladung_und_hinweise_mit_adresse_der_einheit(mailoutbox, settings):
    from accounts.invitations import send_invitation
    from portal.services import create_login_link

    club = make_org("Schützenverein Musterstadt")
    _adresse(club)
    send_invitation(make_user("bernd@example.org"), club, "Kassierer")
    (invite,) = mailoutbox
    assert f"https://{VEREIN_HOST}/passwort-zuruecksetzen/" in invite.body
    link = create_login_link(make_user("carla@example.org"), club)
    assert link.startswith(f"https://{VEREIN_HOST}/anmelden/link/")


def test_passwort_vergessen_auf_der_aufgerufenen_adresse(mailoutbox, adressen, settings):
    from .conftest import csrf_headers

    main = settings.FRONTEND_URL.rstrip("/")
    club = make_org("Schützenverein Musterstadt")
    _adresse(club)
    make_user("anna@example.org")
    for host, expected in ((VEREIN_HOST, f"https://{VEREIN_HOST}"), ("unbekannt.example", main)):
        client = Client(HTTP_HOST=host)
        resp = client.post(
            "/_allauth/browser/v1/auth/password/request",
            {"email": "anna@example.org"},
            content_type="application/json",
            headers=csrf_headers(client),
        )
        assert resp.status_code == 200, resp.content
        assert f"{expected}/passwort-zuruecksetzen/" in mailoutbox[-1].body
