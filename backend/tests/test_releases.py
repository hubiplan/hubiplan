"""Releases (konzepte/releases.md, R1): Versionsnummer der laufenden Fassung."""

import pytest
from django.test import Client

from core import version

pytestmark = pytest.mark.django_db
APP = "/api/app/v1/"


@pytest.fixture
def version_file(tmp_path, monkeypatch):
    path = tmp_path / "hubiplan_version.txt"
    monkeypatch.setattr(version, "VERSION_FILE", path)
    version.running_version.cache_clear()
    yield path
    version.running_version.cache_clear()


def test_ohne_datei_leer(version_file):
    assert version.running_version() == ""


@pytest.mark.parametrize("text", ["2026.11.0", "2026.11.0+3.0a5d21e", "0a5d21e"])
def test_versionen_aus_deploy(version_file, text):
    version_file.write_text(f"{text}\n", encoding="utf-8")
    assert version.running_version() == text


@pytest.mark.parametrize("text", ["<script>", "2026.11.0 extra", "x" * 41])
def test_unerwartete_zeichen_verworfen(version_file, text):
    version_file.write_text(text, encoding="utf-8")
    assert version.running_version() == ""


def test_selbstauskunft_der_app(version_file):
    version_file.write_text("2026.11.1\n", encoding="utf-8")
    data = Client().get(f"{APP}instance/").json()
    assert data["version"] == "2026.11.1"
    assert data["api_version"] == 1
