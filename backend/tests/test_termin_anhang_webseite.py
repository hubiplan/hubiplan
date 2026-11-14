"""Anhänge öffentlicher Termine je Anhang für die Webseite freigeben (alles erfunden)."""
# ruff: noqa: F811  (Fixtures aus test_m12_events)

import datetime

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from website.models import Website

from .test_m12_events import cal, create, org_base, private_root  # noqa: F401

JSON = "application/json"


def soon(days=3):
    start = timezone.localtime(timezone.now() + datetime.timedelta(days=days)).replace(
        microsecond=0, tzinfo=None
    )
    return {
        "starts_at": start.isoformat(),
        "ends_at": (start + datetime.timedelta(hours=2)).isoformat(),
    }


@pytest.fixture
def site(cal):
    org = cal["a"]
    org.enabled_modules = [*org.enabled_modules, "website"]
    org.save()
    return Website.objects.create(organization=org, public_key="schluessel-a", state="public")


def public(path):
    return Client().get(f"/api/public/site/v1/schluessel-a/{path}")


def upload(c, base, ev, name="Ablauf.pdf"):
    pdf = SimpleUploadedFile(name, b"%PDF-1.4 erfundener Ablauf", "application/pdf")
    resp = c.post(f"{base}events/{ev['id']}/attachments/", {"file": pdf})
    assert resp.status_code == 201, resp.json()
    return [a for a in resp.json()["attachments"] if a["name"] == name][0]


def test_nur_freigegebene_anhaenge_oeffentlicher_termine(cal, site, board_a, api):
    c = api(board_a)
    base = org_base(cal["a"])
    ev = create(c, base, title="Schützenfest", visibility="public", **soon())
    shown = upload(c, base, ev)
    hidden = upload(c, base, ev, "Helferliste.pdf")
    assert shown["on_website"] is False
    # Standard: nichts auf der Webseite
    item = public("events/").json()["events"][0]
    assert item["attachments"] == []
    resp = c.patch(shown["url"], {"on_website": True}, content_type=JSON)
    assert resp.status_code == 200, resp.json()
    flags = {a["name"]: a["on_website"] for a in resp.json()["attachments"]}
    assert flags == {"Ablauf.pdf": True, "Helferliste.pdf": False}
    item = public("events/").json()["events"][0]
    assert [a["name"] for a in item["attachments"]] == ["Ablauf.pdf"]
    assert item["attachments"][0]["kind"] == "pdf"
    url = item["attachments"][0]["url"]
    assert url.endswith(f"/events/attachments/{shown['id']}/")
    resp = public(f"events/attachments/{shown['id']}/")
    assert resp.status_code == 200
    assert b"".join(resp.streaming_content).startswith(b"%PDF")
    assert public(f"events/attachments/{hidden['id']}/").status_code == 404
    # Termin wird intern: Anhang verschwindet von der Webseite
    resp = c.patch(f"{base}events/{ev['id']}/", {"visibility": "members"}, content_type=JSON)
    assert resp.status_code == 200, resp.json()
    assert public(f"events/attachments/{shown['id']}/").status_code == 404
    # Bei nicht öffentlichen Terminen lässt sich der Schalter nicht setzen
    resp = c.patch(hidden["url"], {"on_website": True}, content_type=JSON)
    assert resp.status_code == 400


def test_fremde_webseite_und_ohne_terminbereich(cal, site, board_a, board_b, api):
    c = api(board_a)
    base = org_base(cal["a"])
    ev = create(c, base, visibility="public", **soon())
    att = upload(c, base, ev)
    assert c.patch(att["url"], {"on_website": True}, content_type=JSON).status_code == 200
    # Ein anderer Verein mit eigener Webseite bekommt den Anhang nicht
    org_b = cal["b"]
    org_b.enabled_modules = [*org_b.enabled_modules, "website"]
    org_b.save()
    Website.objects.create(organization=org_b, public_key="schluessel-b", state="public")
    resp = Client().get(f"/api/public/site/v1/schluessel-b/events/attachments/{att['id']}/")
    assert resp.status_code == 404
    # Mitglied ohne Bearbeitungsrecht kann den Schalter nicht setzen
    assert api(board_b).patch(att["url"], {"on_website": False}, content_type=JSON).status_code in (
        403,
        404,
    )
