"""Zweites Logo/Wappen für den Dunkelmodus (Ralf 10.11.2026).

Plattform, Einheiten und Untereinheiten können neben dem Logo ein Logo für den Dunkelmodus
hochladen. Fehlt es, gilt im Dunkeln das helle Logo derselben Ebene.
"""

import io

import pytest
from django.core.files.base import ContentFile
from django.test import Client
from PIL import Image

from organizations.models import Department, Organization
from organizations.theme import effective_theme

pytestmark = pytest.mark.django_db


def png_file(color="red", name="logo.png"):
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color).save(buf, "PNG")
    buf.seek(0)
    buf.name = name
    return buf


def png_bytes(color="red") -> bytes:
    return png_file(color).getvalue()


def test_hochladen_anzeigen_und_entfernen(api, orgs, board_a):
    c = api(board_a)
    base = f"/api/orgs/{orgs['a'].pk}"
    light = c.post(f"{base}/logo/", {"logo": png_file("red")}).json()["logo_url"]
    resp = c.post(f"{base}/logo-dark/", {"logo": png_file("blue")})
    assert resp.status_code == 200
    dark = resp.json()["logo_dark_url"]
    assert dark.startswith("/media/logos/organisationen/") and "-dunkel-" in dark
    assert dark != light

    theme = c.get(f"{base}/theme/").json()
    assert theme["logo_url"] == light
    assert theme["logo_dark_url"] == dark
    assert theme["effective"]["logo_dark_url"] == dark
    me = c.get("/api/me/organizations/").json()[0]
    assert me["theme"]["logo_url"] == light
    assert me["theme"]["logo_dark_url"] == dark

    # Entfernen: im Dunkeln gilt wieder das helle Logo
    assert c.delete(f"{base}/logo-dark/").status_code == 204
    orgs["a"].refresh_from_db()
    assert not orgs["a"].logo_dark
    assert orgs["a"].logo
    theme = c.get(f"{base}/theme/").json()
    assert theme["logo_dark_url"] is None
    assert theme["effective"]["logo_dark_url"] == light


def test_nur_bilder(api, orgs, board_a):
    fake = io.BytesIO(b"<svg onload=alert(1)>")
    fake.name = "logo.svg"
    resp = api(board_a).post(f"/api/orgs/{orgs['a'].pk}/logo-dark/", {"logo": fake})
    assert resp.status_code == 400


def test_nur_mit_gestaltungsrecht(api, orgs, board_b):
    resp = api(board_b).post(f"/api/orgs/{orgs['a'].pk}/logo-dark/", {"logo": png_file()})
    assert resp.status_code in (403, 404)
    orgs["a"].refresh_from_db()
    assert not orgs["a"].logo_dark


class TestErben:
    def test_ohne_logos_nichts(self, orgs):
        data = effective_theme(orgs["a"].ancestors())
        assert data["logo_url"] is None
        assert data["logo_dark_url"] is None

    def test_ohne_dunkles_gilt_das_helle(self, orgs):
        orgs["a"].logo.save("a.png", ContentFile(png_bytes()), save=True)
        data = effective_theme(orgs["a"].ancestors())
        assert data["logo_dark_url"] == data["logo_url"] == orgs["a"].logo.url

    def test_helles_eigenes_geht_vor_dunklem_des_dachverbands(self, orgs):
        fed = orgs["federation"]
        fed.logo.save("f.png", ContentFile(png_bytes()), save=True)
        fed.logo_dark.save("fd.png", ContentFile(png_bytes("blue")), save=True)
        orgs["a"].logo.save("a.png", ContentFile(png_bytes()), save=True)
        data = effective_theme(orgs["a"].ancestors())
        # Das eigene Wappen gilt auch im Dunkeln, nicht das dunkle des Dachverbands
        assert data["logo_dark_url"] == orgs["a"].logo.url
        # Verein B ohne eigenes Wappen erbt beide vom Dachverband
        data_b = effective_theme(orgs["b"].ancestors())
        assert data_b["logo_url"] == fed.logo.url
        assert data_b["logo_dark_url"] == fed.logo_dark.url

    def test_nur_dunkles_eigenes(self, orgs):
        fed = orgs["federation"]
        fed.logo.save("f.png", ContentFile(png_bytes()), save=True)
        orgs["a"].logo_dark.save("ad.png", ContentFile(png_bytes("blue")), save=True)
        data = effective_theme(orgs["a"].ancestors())
        # Hell erbt wie bisher, dunkel zeigt das eigene
        assert data["logo_url"] == fed.logo.url
        assert data["logo_dark_url"] == orgs["a"].logo_dark.url


def test_untereinheit(api, orgs, board_a):
    zug = Department.objects.create(organization=orgs["a"], parent=orgs["a"], name="Jägerzug")
    c = api(board_a)
    base = f"/api/orgs/{orgs['a'].pk}/departments/{zug.pk}"
    resp = c.post(f"{base}/logo-dark/", {"logo": png_file("blue")})
    assert resp.status_code == 200
    zug.refresh_from_db()
    assert zug.logo_dark
    assert "/abteilungen/" in zug.logo_dark.url
    listed = c.get(f"/api/orgs/{orgs['a'].pk}/departments/").json()
    rows = listed["results"] if isinstance(listed, dict) else listed
    row = next(r for r in rows if r["id"] == zug.pk)
    assert row["logo_dark_url"] == zug.logo_dark.url
    assert c.delete(f"{base}/logo-dark/").status_code == 204
    zug.refresh_from_db()
    assert not zug.logo_dark


def test_anmeldeseite_der_instanz():
    platform = Organization.platform()
    platform.logo.save("p.png", ContentFile(png_bytes()), save=True)
    data = Client().get("/api/public/platform/").json()
    assert data["logo_dark_url"] == data["logo_url"] == platform.logo.url
    platform.logo_dark.save("pd.png", ContentFile(png_bytes("blue")), save=True)
    data = Client().get("/api/public/platform/").json()
    assert data["logo_url"] == platform.logo.url
    assert data["logo_dark_url"] == platform.logo_dark.url
