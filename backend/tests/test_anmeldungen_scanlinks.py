# ruff: noqa: F811  (Fixtures aus test_m9_billing und test_anmeldungen)
"""Scanpersonal mit Link: nur der Kartenscanner, für den Einlass oder eine Zusatzleistung
(konzepte/veranstaltungen-anmeldung-gebuehr.md, Abschnitt 3.11). Alle Daten erfunden."""

import datetime

import pytest
from django.test import Client
from django.utils import timezone

from core.tenancy import tenant_context
from registrations import tickets
from registrations.models import Participant

from .test_anmeldungen import JSON, einrichten, fest, ok, soon  # noqa: F401
from .test_m9_billing import base, c, club, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db

ADDONS = [
    {
        "name": "Mittagessen",
        "kind": "meal",
        "per": "person",
        "choices": [{"name": "Schnitzel", "amount": "0"}, {"name": "Gemüse", "amount": "0"}],
    },
]
FREE = [{"name": "Alle", "steps": [{"amount": "0"}]}]


def _anmelden(fest, who, meal=True):
    client, url = fest["portals"][who]
    offer = ok(client.get(f"{url}registration/"))["offer"]
    person = {"membership_id": fest[who.lower()].pk, "price_id": offer["prices"][0]["id"]}
    if meal:
        addon = offer["addons"][0]
        person["addons"] = {str(addon["id"]): addon["choices"][0]["id"]}
    ok(client.post(f"{url}registration/", {"persons": [person]}, content_type=JSON))


def _code(club, member):
    with tenant_context(club.pk):
        return tickets.code(Participant.objects.get(membership=member))


def _token(url):
    return url.rsplit("/kartenscan/", 1)[1]


def test_scanlinks_einlass_und_essen(c, fest, club):
    einrichten(c, fest, prices=FREE, addons=ADDONS)
    _anmelden(fest, "Anna")
    _anmelden(fest, "Bernd", meal=False)
    links_url = f"{fest['url']}scan-links/"
    listing = ok(c.get(links_url))
    assert listing["links"] == [] and listing["addons"][0]["name"] == "Mittagessen"
    entry = ok(c.post(links_url, {"label": "Eingang Nord"}, content_type=JSON))
    meal = ok(
        c.post(
            links_url,
            {"label": "Essensausgabe", "addon": listing["addons"][0]["id"]},
            content_type=JSON,
        )
    )
    assert entry["station"] == "Einlass" and meal["station"] == "Mittagessen"
    assert "/kartenscan/" in entry["url"]

    staff = Client()  # ohne Konto
    entry_api = f"/api/public/scan/{_token(entry['url'])}/"
    meal_api = f"/api/public/scan/{_token(meal['url'])}/"
    page = ok(staff.get(entry_api))
    assert page["kind"] == "entry" and page["event"] == fest["event"]["title"]

    anna = _code(club, fest["anna"])
    first = ok(staff.post(entry_api, {"code": anna}, content_type=JSON))
    assert first["result"] == "ok" and first["valid"]
    card = first["card"]
    assert card["name"] == "Anna Muster" and card["price_name"]
    assert card["bookings"][0]["name"].startswith("Mittagessen")
    assert card["bookings"][0]["redeemed_at"] is None
    again = ok(staff.post(entry_api, {"code": anna}, content_type=JSON))
    assert again["result"] == "already" and not again["valid"] and again["at"]
    # Verwaltung sieht den Einlass
    with tenant_context(club.pk):
        p = Participant.objects.get(membership=fest["anna"])
        assert p.checked_in_at and p.checked_in_via == "Eingang Nord"

    # Essen: einmal einlösen, zweites Mal mit Zeitpunkt abgewiesen
    got = ok(staff.post(meal_api, {"code": anna}, content_type=JSON))
    assert got["result"] == "ok" and got["card"]["bookings"][0]["redeemed_at"]
    twice = ok(staff.post(meal_api, {"code": anna}, content_type=JSON))
    assert twice["result"] == "already" and twice["at"]
    # Ohne gebuchtes Essen
    bernd = _code(club, fest["bernd"])
    none = ok(staff.post(meal_api, {"code": bernd}, content_type=JSON))
    assert none["result"] == "not_booked" and none["card"]["name"] == "Bernd Beispiel"
    # Unsinn
    bad = ok(staff.post(entry_api, {"code": "T1:falsch"}, content_type=JSON))
    assert bad["result"] == "unknown" and bad["card"] is None

    # Gesperrt: Link tot; abgelaufen ebenso
    assert c.delete(f"{links_url}{entry['id']}/").status_code == 204
    assert staff.get(entry_api).status_code == 404
    assert staff.post(entry_api, {"code": anna}, content_type=JSON).status_code == 404
    with tenant_context(club.pk):
        from registrations.models import ScanLink

        ScanLink.objects.filter(pk=meal["id"]).update(
            expires_at=timezone.now() - datetime.timedelta(minutes=1)
        )
    assert staff.get(meal_api).status_code == 404
    listing = ok(c.get(links_url))
    assert [link["active"] for link in listing["links"]] == [False, False]
    assert listing["links"][0]["scans"] == 3


def test_scanlinks_nur_mit_bearbeitungsrecht(c, fest, club, api):
    einrichten(c, fest, prices=FREE)
    client, _url = fest["portals"]["Anna"]
    # Ein Mitglied ohne Verwaltungsrechte kommt nicht an die Links
    assert client.get(f"{fest['url']}scan-links/").status_code in (403, 404)
    resp = c.post(
        f"{fest['url']}scan-links/",
        {"label": "Eingang", "expires_at": soon(-1)},
        content_type=JSON,
    )
    assert resp.status_code == 400


def test_ohne_karte_per_namenssuche(c, fest, club):
    einrichten(c, fest, prices=FREE)
    _anmelden(fest, "Anna", meal=False)
    links_url = f"{fest['url']}scan-links/"
    plain = ok(c.post(links_url, {"label": "Eingang Süd"}, content_type=JSON))
    search = ok(c.post(links_url, {"label": "Kasse", "allow_search": True}, content_type=JSON))
    assert search["allow_search"] is True and plain["allow_search"] is False
    staff = Client()
    plain_api = f"/api/public/scan/{_token(plain['url'])}/"
    api = f"/api/public/scan/{_token(search['url'])}/"
    # Ohne Erlaubnis: keine Suche, kein Einbuchen über die Nummer
    assert staff.get(f"{plain_api}search/?q=Ann").status_code == 404
    with tenant_context(club.pk):
        pid = Participant.objects.get(membership=fest["anna"]).pk
    denied = ok(staff.post(plain_api, {"participant": pid}, content_type=JSON))
    assert denied["result"] == "unknown"
    # Mit Erlaubnis: erst ab drei Zeichen, nur Treffer
    assert ok(staff.get(f"{api}search/?q=An"))["results"] == []
    hits = ok(staff.get(f"{api}search/?q=muster"))["results"]
    assert [h["name"] for h in hits] == ["Anna Muster"]
    # Die Suche liefert einen Verweis, keine fortlaufende Nummer (Gesamtaudit 19.11., S-04)
    ref = hits[0]["id"]
    assert isinstance(ref, str) and ref != str(pid)
    assert ok(staff.get(f"{api}search/?q=Bernd"))["results"] == []  # nicht angemeldet
    # Die Nummer allein bucht niemanden ein, auch nicht als Text
    for guess in (pid, str(pid)):
        assert ok(staff.post(api, {"participant": guess}, content_type=JSON))["result"] == (
            "unknown"
        )
    # Ein Verweis gilt nur an dem Link, der ihn ausgegeben hat
    other = ok(c.post(links_url, {"label": "Kasse 2", "allow_search": True}, content_type=JSON))
    other_api = f"/api/public/scan/{_token(other['url'])}/"
    assert ok(staff.post(other_api, {"participant": ref}, content_type=JSON))["result"] == (
        "unknown"
    )
    done = ok(staff.post(api, {"participant": ref}, content_type=JSON))
    assert done["result"] == "ok" and done["card"]["name"] == "Anna Muster"
    assert ok(staff.get(f"{api}search/?q=muster"))["results"][0]["checked_in_at"]
