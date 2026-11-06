"""White Label W1 und W2: Erscheinungsbild der Instanz ohne Anmeldung (konzepte/white-label.md)."""
# ruff: noqa: F811  (Fixture platform_admin aus test_impressum als Parameter)

import io

import pytest
from django.test import Client
from PIL import Image

from organizations.models import Organization, PlatformSettings

from .factories import make_org, make_user
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
