# ruff: noqa: F401, F811  (Fixtures aus test_webseite_suche)
"""Suche über einen zwischengespeicherten Index und mit eigener Grenze (Gesamtaudit 15.11.,
WEB-06). Erfundene Daten."""

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from website import content, public_views, search
from website.models import WebsiteText

from .factories import make_user
from .test_webseite_suche import KEY, WHEN, club, hits, site

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def leer():
    cache.clear()
    yield
    cache.clear()


def _seite(club, site, title, body, slug):
    return WebsiteText.objects.create(
        organization=club,
        website=site,
        kind="page",
        slug=slug,
        title=title,
        body=body,
        published_title=title,
        published_body=body,
        published_at=WHEN,
    )


def test_zweite_suche_aus_dem_index(club, site):
    _seite(club, site, "Anfahrt", "Parkplatz am Schützenhaus", "anfahrt")
    assert [h["slug"] for h in hits("Parkplatz") if h["kind"] == "page"] == ["anfahrt"]
    with CaptureQueriesContext(connection) as erste:
        hits("Schützenhaus")
    cache_key_da = cache.get(search.index_key(site.pk, "de")) is not None
    assert cache_key_da
    # Ein anderes Suchwort baut nichts neu: nur noch das Laden der Webseite
    with CaptureQueriesContext(connection) as zweite:
        hits("Anfahrt")
    assert len(zweite) <= len(erste)


def test_veroeffentlichen_verwirft_den_index(club, site):
    text = _seite(club, site, "Anfahrt", "Parkplatz am Schützenhaus", "anfahrt")
    assert not hits("Festwiese")
    text.body = "Festwiese hinter dem Schützenhaus"
    text.save()
    content.publish(text, make_user("redaktion-web06@example.org"))
    assert [h["slug"] for h in hits("Festwiese")] == ["anfahrt"]


def test_eigene_grenze(club, site, monkeypatch):
    monkeypatch.setattr(public_views, "SEARCH_LIMIT", 2)
    c = Client()
    url = f"/api/public/site/v1/{KEY}/search/"
    assert c.get(url, {"q": "a1"}).status_code == 200
    assert c.get(url, {"q": "a2"}).status_code == 200
    assert c.get(url, {"q": "a3"}).status_code == 429
