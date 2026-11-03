"""Releases E9 (konzepte/releases.md): Hinweis auf ein neueres Release für Betreiber."""

import json

import pytest
from django.core.cache import cache
from django.test import override_settings

from core import safehttp, update_check, version
from organizations.imprint_generator import platform_privacy
from organizations.models import Organization

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
URL = "/api/platform/update/"


def antwort(**extra) -> bytes:
    data = {
        "tag_name": "v2026.12.0",
        "html_url": "https://github.com/hubiplan/hubiplan/releases/tag/v2026.12.0",
        "draft": False,
        "prerelease": False,
    }
    data.update(extra)
    return json.dumps(data).encode()


@pytest.fixture(autouse=True)
def sauber(tmp_path, monkeypatch):
    cache.delete(update_check.CACHE_KEY)
    monkeypatch.setattr(version, "VERSION_FILE", tmp_path / "hubiplan_version.txt")
    version.running_version.cache_clear()
    yield tmp_path / "hubiplan_version.txt"
    version.running_version.cache_clear()
    cache.delete(update_check.CACHE_KEY)


@pytest.fixture
def github(monkeypatch):
    calls = []

    def fake(method, url, **kwargs):
        calls.append(url)
        return safehttp.Response(status=200, headers={}, body=fake.body)

    fake.body = antwort()
    monkeypatch.setattr(safehttp, "request", fake)
    return fake, calls


@pytest.fixture
def platform_admin(db):
    user = make_user("plattform@example.org")
    give_role(user, Organization.platform())
    return user


def laufend(path, text):
    path.write_text(text, encoding="utf-8")
    version.running_version.cache_clear()


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("2026.11.0", (2026, 11, 0)),
        ("2026.11.0+3.0a5d21e", (2026, 11, 0)),
        ("0a5d21e", None),
        ("", None),
    ],
)
def test_laufendes_release(text, erwartet):
    assert update_check.running_release(text) == erwartet


@pytest.mark.parametrize(
    "body",
    [
        antwort(draft=True),
        antwort(prerelease=True),
        antwort(tag_name="nightly"),
        b"<html>",
        b"[]",
    ],
)
def test_unbrauchbare_antworten(body):
    assert update_check.parse_latest(body) is None


def test_fremde_adresse_wird_nicht_verlinkt():
    data = update_check.parse_latest(antwort(html_url="https://example.org/x"))
    assert data == {"version": "2026.12.0", "url": ""}


def test_neueres_release_gefunden(sauber, github):
    laufend(sauber, "2026.11.0+3.0a5d21e\n")
    assert update_check.check_latest() == "2026.12.0"
    assert github[1] == ["https://api.github.com/repos/hubiplan/hubiplan/releases/latest"]
    assert update_check.available() == {
        "version": "2026.12.0",
        "url": "https://github.com/hubiplan/hubiplan/releases/tag/v2026.12.0",
        "running": "2026.11.0+3.0a5d21e",
    }


@pytest.mark.parametrize("text", ["2026.12.0", "2026.12.0+1.abcdef0", "0a5d21e"])
def test_kein_hinweis_wenn_aktuell_oder_ohne_release(sauber, github, text):
    laufend(sauber, text)
    update_check.check_latest()
    assert update_check.available() is None


def test_abgeschaltet_fragt_nicht_und_vergisst(sauber, github):
    laufend(sauber, "2026.11.0")
    update_check.check_latest()
    with override_settings(UPDATE_CHECK=False):
        assert update_check.check_latest() is None
        assert update_check.available() is None
    assert len(github[1]) == 1
    assert cache.get(update_check.CACHE_KEY) is None


def test_github_nicht_erreichbar(sauber, monkeypatch):
    def kaputt(*args, **kwargs):
        raise safehttp.SafeHTTPError("weg")

    monkeypatch.setattr(safehttp, "request", kaputt)
    laufend(sauber, "2026.11.0")
    assert update_check.check_latest() is None
    assert update_check.available() is None


def test_schnittstelle_nur_fuer_plattformverwalter(api, sauber, github, platform_admin, board_a):
    laufend(sauber, "2026.11.0")
    update_check.check_latest()
    assert api(board_a).get(URL).status_code == 403
    data = api(platform_admin).get(URL).json()
    assert data["enabled"] is True
    assert data["update"]["version"] == "2026.12.0"


def test_datenschutzhinweis_nennt_github():
    assert "GitHub sieht nur die IP-Adresse des Servers" in platform_privacy()
    with override_settings(UPDATE_CHECK=False):
        assert "GitHub" not in platform_privacy()
