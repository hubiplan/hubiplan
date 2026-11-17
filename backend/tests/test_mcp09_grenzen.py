# ruff: noqa: F811  (Fixtures aus test_mcp_verein)
"""KI-Schnittstelle: Grenzen für teure Werkzeuge und Antworten, Speichergrenze für
Webseitenbilder, Warnung auch bei bekannten Assistenten (Gesamtaudit 15.11., MCP-08/09).
Erfundene Daten."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError

from core import safehttp
from mcpserver import club_design, protocol
from organizations.models import PlatformSettings
from website import content, upload_views
from website.models import WebsiteImage

from .test_mcp_verein import call, club, connect, editor, site  # noqa: F401
from .test_mcp_webseite_w2 import picture, private_root  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def leer():
    cache.clear()
    yield
    cache.clear()


def test_antwort_wird_gekuerzt():
    part = protocol._cap({"type": "text", "text": "ä" * 80_000})
    assert len(part["text"].encode()) < 100_000 + 500
    assert "gekürzt" in part["text"]
    kurz = {"type": "text", "text": "kurz"}
    assert protocol._cap(kurz) == kurz


def test_hochladelinks_je_person_begrenzt(club, site, editor, monkeypatch):
    monkeypatch.setattr(club_design, "OPEN_LINKS_PER_PERSON", 2)
    token = connect(editor, club)["access_token"]
    for _ in range(2):
        _text, failed = call(token, "bild_hochladen_vorbereiten")
        assert not failed
    text, failed = call(token, "bild_hochladen_vorbereiten")
    assert failed and "offene Hochladelinks" in text


def test_bild_von_adresse_je_stunde_begrenzt(club, site, editor, monkeypatch):
    monkeypatch.setattr(club_design, "FETCH_PER_HOUR", 1)
    monkeypatch.setattr(
        upload_views.safehttp,
        "request",
        lambda method, url, **kw: safehttp.Response(200, {"Content-Type": "image/png"}, picture()),
    )
    site.image_hosts = ["cloud.example.org"]
    site.save()
    token = connect(editor, club)["access_token"]
    url = "https://cloud.example.org/a.png"
    _text, failed = call(token, "bild_von_adresse", adresse=url, quelle="Verein")
    assert not failed, _text
    text, failed = call(token, "bild_von_adresse", adresse=url, quelle="Verein")
    assert failed and "später erneut" in text
    assert WebsiteImage.objects.filter(website=site).count() == 1


def test_speichergrenze_fuer_webseitenbilder(club, site, editor):
    settings = PlatformSettings.load()
    settings.website_image_quota_mb = 1
    settings.save()
    big = picture(size=(1800, 1800))
    content.store_image(
        site, SimpleUploadedFile("a.png", big, content_type="image/png"), "", "", editor
    )
    with pytest.raises(ValidationError) as exc:
        for i in range(20):
            content.store_image(
                site, SimpleUploadedFile(f"b{i}.png", big, content_type="image/png"), "", "", editor
            )
    assert "Speicher für Webseitenbilder ist voll" in str(exc.value)
    settings.website_image_quota_mb = 0  # ohne Grenze
    settings.save()
    content.store_image(
        site, SimpleUploadedFile("c.png", big, content_type="image/png"), "", "", editor
    )
