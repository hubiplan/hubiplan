"""Würden-Fotos mit nur namentlich eingetragenen Personen nur mit bestätigter Einwilligung.

Gesamtaudit 15.11., PF-21 (Fachfrage, von Ralf am 16.11. wie empfohlen entschieden): Das Foto
erschien, sobald alle verknüpften Mitglieder eingewilligt hatten; wer nur mit Namen eingetragen
ist, wurde übergangen. Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest
from django.test import Client

from honors.models import Companion, Reign, ReignPhoto

from .test_wuerden import koenig, people, png, private_root, site, url  # noqa: F401

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _photo_urls():
    data = Client().get("/api/public/site/v1/schluessel-w/honors/").json()
    return [r["photo_url"] for r in data["dignities"][0]["reigns"]]


def test_freie_namen_brauchen_bestaetigte_einwilligung(orgs, site, koenig, board_a, api):
    org = orgs["a"]
    reign = Reign.objects.create(organization=org, dignity=koenig, year=1975, name="Karl Frei")
    c = api(board_a)
    resp = c.post(url(org, f"reigns/{reign.pk}/photo/"), {"file": png()})
    assert resp.status_code == 201
    assert resp.json()["free_names"] is True and resp.json()["consent"] is False
    assert _photo_urls() == [None]  # ohne Bestätigung nicht auf der Webseite

    resp = c.patch(url(org, f"reigns/{reign.pk}/photo/"), {"consent": True}, content_type=JSON)
    assert resp.status_code == 200 and resp.json()["consent"] is True
    assert _photo_urls()[0]


def test_freie_begleitung_zaehlt_auch(orgs, site, people, koenig, board_a, api):
    from website import services

    org = orgs["a"]
    erika = people["erika"]
    services.set_entry(erika, "photo", True, "paper", None)  # Mitglied hat eingewilligt
    reign = Reign.objects.create(organization=org, dignity=koenig, year=2020, person=erika.person)
    Companion.objects.create(organization=org, reign=reign, label="Prinzgemahl", name="Max Frei")
    assert (
        api(board_a).post(url(org, f"reigns/{reign.pk}/photo/"), {"file": png()}).status_code == 201
    )
    assert _photo_urls() == [None]


def test_sammelaktion_fuer_alte_jahre(orgs, site, koenig, board_a, api):
    org = orgs["a"]
    c = api(board_a)
    for year in (1950, 1951, 1952):
        reign = Reign.objects.create(organization=org, dignity=koenig, year=year, name=f"N {year}")
        assert c.post(url(org, f"reigns/{reign.pk}/photo/"), {"file": png()}).status_code == 201
    assert c.get(url(org, "photo-consent/")).json() == {"open": 3}
    resp = c.post(url(org, "photo-consent/"), {"all": True}, content_type=JSON)
    assert resp.status_code == 200 and resp.json() == {"open": 0, "confirmed": 3}
    assert ReignPhoto.objects.filter(consent_confirmed=True).count() == 3
    assert all(_photo_urls())
