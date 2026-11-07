"""Modul „Chronik“: eigener Menüpunkt, auch ohne Webseite (Modulverzeichnis, M2b).

Erfundene Daten."""

import pytest
from django.test import Client

from website.models import Website, WebsiteText

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def chronist(orgs):
    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "chronicle"} - {"website"})
    org.save()
    user = make_user("chronist@example.org")
    give_role(user, org, permissions=["chronicle.edit"], name="Chronist")
    return user


def test_chronik_ohne_webseite_pflegen(orgs, chronist, api):
    org = orgs["a"]
    c = api(chronist)
    data = c.get(f"/api/orgs/{org.pk}/chronicle/").json()
    assert data["can_edit"] is True and data["website"] is False
    text = data["text"]
    assert text["has_timeline"] is True and text["slug"] == "geschichte"
    site = Website.objects.get(organization=org)
    assert site.state == Website.State.OFF
    base = f"/api/orgs/{org.pk}/website/texts/{text['id']}/"
    resp = c.put(base, {"timeline": [{"year": 1920, "title": "Gründung"}], "slug": "x"}, JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["slug"] == "geschichte"
    assert c.post(f"{base}publish/").status_code == 200
    assert c.delete(base).status_code == 404
    assert c.get(f"/api/orgs/{org.pk}/website/images/").status_code == 200
    # Andere Texte und die Einrichtung der Webseite bleiben verborgen
    other = WebsiteText.objects.create(
        organization=org, website=site, kind="page", slug="satzung", title="Satzung"
    )
    assert c.get(f"/api/orgs/{org.pk}/website/texts/{other.pk}/").status_code == 404
    assert c.get(f"/api/orgs/{org.pk}/website/texts/").status_code == 404
    # Öffentlich gibt es ohne Modul „Webseite“ nichts
    assert Client().get(f"/api/public/site/v1/{site.public_key}/").status_code == 404


def test_chronik_aus(orgs, chronist, api):
    org = orgs["a"]
    org.enabled_modules = [m for m in org.enabled_modules if m != "chronicle"]
    org.save()
    c = api(chronist)
    assert c.get(f"/api/orgs/{org.pk}/chronicle/").status_code == 404
    assert not Website.objects.filter(organization=org).exists()


def test_leser_legt_nichts_an(orgs, api):
    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "chronicle"})
    org.save()
    user = make_user("leser-chronik@example.org")
    give_role(user, org, permissions=["chronicle.view"], name="Leser")
    data = api(user).get(f"/api/orgs/{org.pk}/chronicle/").json()
    assert data == {"text": None, "can_edit": False, "website": False}


def test_oeffentliche_zeitleiste_folgt_dem_modul(orgs):
    from website import content

    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "website", "chronicle"})
    org.save()
    site = Website.objects.create(organization=org, public_key=Website.new_key(), state="public")
    text = content.chronicle(site)
    text.timeline = [{"year": 1920, "title": "Gründung", "kind": "event"}]
    text.save()
    content.publish(text, None)
    page = Client().get(f"/api/public/site/v1/{site.public_key}/pages/geschichte/")
    assert page.json()["timeline"], page.content
    org.enabled_modules = [m for m in org.enabled_modules if m != "chronicle"]
    org.save()
    page = Client().get(f"/api/public/site/v1/{site.public_key}/pages/geschichte/")
    assert page.json()["timeline"] == []
