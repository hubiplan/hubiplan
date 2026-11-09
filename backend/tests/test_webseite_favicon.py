"""Wappen als Favicon der Vereinswebseite (Ralf 09.11.2026, erfundene Daten)."""

import io

import pytest
from django.core.files.base import ContentFile
from django.test import Client
from django.utils import timezone
from PIL import Image

from organizations.models import PlatformSettings
from website.models import Website

pytestmark = pytest.mark.django_db(transaction=True)

BASE = "/api/public/site/v1/favicon-a/"


def _png(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (width, height), (31, 78, 121, 255)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def site(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "website"]
    org.save()
    return Website.objects.create(
        organization=org,
        public_key="favicon-a",
        state="public",
        privacy_published_text="Wir speichern wenig.",
        privacy_published_at=timezone.now(),
    )


def test_ohne_wappen_kein_symbol(site):
    assert Client().get(BASE).json()["icon"] is False
    assert Client().get(f"{BASE}icon-32.png").status_code == 404


def test_ohne_wappen_nicht_das_symbol_der_instanz(site, orgs):
    row = PlatformSettings.load()
    row.brand_icon.save("instanz.png", ContentFile(_png(512, 512)), save=True)
    assert Client().get(BASE).json()["icon"] is False
    assert Client().get(f"{BASE}icon-32.png").status_code == 404


def test_wappen_wird_quadratisch_zum_favicon(site, orgs):
    org = orgs["a"]
    org.logo.save("wappen.png", ContentFile(_png(300, 150)), save=True)
    assert Client().get(BASE).json()["icon"] is True
    for size in (32, 180, 192, 512):
        r = Client().get(f"{BASE}icon-{size}.png")
        assert r.status_code == 200
        assert r["Content-Type"] == "image/png"
        assert Image.open(io.BytesIO(r.content)).size == (size, size)
    assert Client().get(f"{BASE}icon-64.png").status_code == 404
    assert Client().get(f"{BASE}icon-abc.png").status_code == 404


def test_favicon_auch_in_der_wartung(site, orgs):
    org = orgs["a"]
    org.logo.save("wappen.png", ContentFile(_png(200, 240)), save=True)
    site.state = Website.State.MAINTENANCE
    site.save()
    info = Client().get(BASE)
    assert info.status_code == 503
    assert info.json()["icon"] is True
    assert Client().get(f"{BASE}icon-32.png").status_code == 200
    # Im Zustand „Aus“ gibt es nichts
    site.state = Website.State.OFF
    site.save()
    assert Client().get(f"{BASE}icon-32.png").status_code == 404
