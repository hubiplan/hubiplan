# ruff: noqa: F401, F811  (Fixtures aus test_app_devices)
"""Mindestversion der App je Plattform (Gesamtaudit 15.11., APP-11). Erfundene Daten."""

import pytest
from django.test import Client

from devices import views
from devices.models import PairingCode

from .test_app_devices import APP, cal, member, pairing_code

pytestmark = pytest.mark.django_db
JSON = "application/json"


def test_selbstauskunft_je_plattform():
    data = Client().get(f"{APP}instance/").json()
    assert data["min_app_versions"] == {"android": views.MIN_APP_VERSION, "ios": 1}
    assert data["min_app_version"] == views.MIN_APP_VERSION  # ältere Android-Fassungen


def test_zu_alte_app_verbraucht_den_code_nicht(api, monkeypatch, member):
    monkeypatch.setitem(views.MIN_APP_VERSIONS, "ios", 5)
    code = pairing_code(api(member[0]))
    resp = Client().post(
        f"{APP}pair/",
        {"code": code, "name": "iPhone", "platform": "ios", "app_version": "4"},
        content_type=JSON,
    )
    assert resp.status_code == 426, resp.content
    assert resp.json()["detail"].startswith("Bitte die App aktualisieren")
    assert PairingCode.objects.get().used_at is None
    # Android ist eine eigene Zählung: Version 4 reicht dort
    assert not views.app_too_old("android", "4")
    # Unlesbare Angaben (Entwicklungsfassungen) gelten nicht als zu alt
    assert not views.app_too_old("ios", "0.1.0")
