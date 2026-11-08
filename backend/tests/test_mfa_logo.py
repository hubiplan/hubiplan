"""Vereinslogo im QR-Code der 2FA-Einrichtung (inoffizieller ``image``-Parameter)."""

import io
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from accounts.mfa import MFAAdapter, totp_image_url
from organizations.models import Organization

from .factories import give_role, make_user

SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


def png_bytes() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (16, 16), (10, 80, 60)).save(out, format="PNG")
    return out.getvalue()


def set_logo(org) -> None:
    org.logo.save("logo.png", SimpleUploadedFile("logo.png", png_bytes()))


def image_param(user) -> str | None:
    url = MFAAdapter().build_totp_url(user, SECRET)
    assert url.startswith("otpauth://totp/")
    values = parse_qs(urlsplit(url).query).get("image")
    return values[0] if values else None


@pytest.fixture(autouse=True)
def _https(settings):
    settings.FRONTEND_URL = "https://verein.example.org"


@pytest.mark.django_db
class TestTotpLogo:
    def test_logo_des_vereins(self, orgs, board_a):
        set_logo(orgs["a"])
        image = image_param(board_a)
        assert image.startswith("https://verein.example.org/media/logos/")
        assert image.endswith(".png")

    def test_logo_vom_dachverband_geerbt(self, orgs, board_a):
        set_logo(orgs["federation"])
        assert image_param(board_a) == totp_image_url(board_a)
        assert orgs["federation"].logo.url in image_param(board_a)

    def test_ohne_logo_kein_parameter(self, orgs, board_a):
        assert image_param(board_a) is None

    def test_mehrere_vereine_nimmt_plattformlogo(self, orgs):
        user = make_user("zwei-vereine@example.org")
        give_role(user, orgs["a"])
        give_role(user, orgs["c"])
        set_logo(orgs["a"])
        assert image_param(user) is None
        platform = Organization.platform()
        set_logo(platform)
        assert platform.logo.url in image_param(user)

    def test_ohne_https_kein_parameter(self, orgs, board_a, settings):
        settings.FRONTEND_URL = "http://localhost:5173"
        set_logo(orgs["a"])
        assert image_param(board_a) is None

    def test_parameter_ist_kodiert(self, orgs, board_a):
        set_logo(orgs["a"])
        url = MFAAdapter().build_totp_url(board_a, SECRET)
        assert "&image=https%3A%2F%2F" in url
        assert "issuer=" in url and f"secret={SECRET}" in url
