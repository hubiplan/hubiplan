"""Startseite der Apps (``/api/portal/<Zugang>/start/``): nächster Termin, was wartet, Kacheln.
Nur erfundene Daten."""

import datetime

import pytest
from django.utils import timezone

from core.tenancy import rls_bypass, tenant_context

from .factories import make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "members", "events", "pinboard", "portal"})
    org.member_portal_enabled = True
    org.save()
    return org


@pytest.fixture
def zugang(club):
    from portal.models import PortalAccess

    member = make_member(club, "Anna", "Beispiel")
    user = make_user("anna-start@example.org")
    with rls_bypass():
        access = PortalAccess.objects.create(organization=club, membership=member, user=user)
    return user, access


def _termin(club, title, days, **more):
    from events.models import Event

    start = timezone.now() + datetime.timedelta(days=days)
    with rls_bypass(), tenant_context(club.pk):
        return Event.objects.create(
            organization=club,
            title=title,
            starts_at=start,
            ends_at=start + datetime.timedelta(hours=3),
            **more,
        )


def test_start_ohne_anlass_ist_leer(api, zugang):
    user, access = zugang
    resp = api(user).get(f"/api/portal/{access.pk}/start/")
    assert resp.status_code == 200, resp.content
    assert resp["Cache-Control"] == "private, no-store"
    data = resp.json()
    assert data["next_event"] is None and data["todo"] == []
    # Die Kacheln sind dieselben wie unter home-tiles
    tiles = api(user).get(f"/api/portal/{access.pk}/home-tiles/").json()["tiles"]
    assert [t["key"] for t in data["tiles"]] == [t["key"] for t in tiles]


def test_naechster_termin_und_offene_rueckmeldungen(api, club, zugang):
    user, access = zugang
    _termin(club, "Vergangen", -2)
    sommerfest = _termin(club, "Sommerfest", 5, rsvp_enabled=True)
    _termin(club, "Arbeitseinsatz", 9, rsvp_enabled=True)
    _termin(club, "Stammtisch", 12)
    # Anmeldeschluss vorbei: zählt nicht mehr als offen
    _termin(
        club,
        "Ausflug",
        20,
        rsvp_enabled=True,
        rsvp_deadline=timezone.now() - datetime.timedelta(days=1),
    )
    c = api(user)
    url = f"/api/portal/{access.pk}/start/"
    data = c.get(url).json()
    assert data["next_event"]["title"] == "Sommerfest"
    assert data["next_event"]["rsvp_enabled"] is True and data["next_event"]["my_response"] is None
    # Gleiches Format wie die Terminliste
    listed = c.get(f"/api/portal/{access.pk}/events/").json()["items"]
    assert set(data["next_event"]) == set(next(i for i in listed if i["title"] == "Sommerfest"))
    assert data["todo"] == [
        {
            "key": "rsvp",
            "title": "2 Termine warten auf deine Rückmeldung",
            "count": 2,
            "target": "events",
        }
    ]
    # Nach der Zusage wartet nur noch einer
    resp = c.put(
        f"/api/portal/{access.pk}/events/{sommerfest.pk}/response/",
        {"status": "yes"},
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.content
    data = c.get(url).json()
    assert data["next_event"]["my_response"] == "yes"
    assert data["todo"][0]["title"] == "1 Termin wartet auf deine Rückmeldung"
    assert data["todo"][0]["count"] == 1


def test_abgesagter_termin_ist_nicht_der_naechste(api, club, zugang):
    from events.models import Event

    user, access = zugang
    abgesagt = _termin(club, "Abgesagt", 3)
    _termin(club, "Findet statt", 6)
    with rls_bypass(), tenant_context(club.pk):
        Event.objects.filter(pk=abgesagt.pk).update(is_cancelled=True)
    data = api(user).get(f"/api/portal/{access.pk}/start/").json()
    assert data["next_event"]["title"] == "Findet statt"


def test_pinnwand_steht_unter_zu_tun(api, club, zugang):
    from pinboard.models import Notice

    user, access = zugang
    with rls_bypass(), tenant_context(club.pk):
        Notice.objects.create(organization=club, text="Arbeitseinsatz am Samstag\nBitte Handschuhe")
    data = api(user).get(f"/api/portal/{access.pk}/start/").json()
    assert data["todo"] == [
        {
            "key": "pinboard",
            "title": "1 neuer Beitrag an der Pinnwand",
            "count": 1,
            "target": "pinboard",
        }
    ]


def test_ohne_terminkalender_und_fremder_zugang(api, club, zugang):
    user, access = zugang
    club.enabled_modules = [m for m in club.enabled_modules if m != "events"]
    club.save()
    data = api(user).get(f"/api/portal/{access.pk}/start/").json()
    assert data["next_event"] is None
    fremd = make_user("fremd-start@example.org")
    assert api(fremd).get(f"/api/portal/{access.pk}/start/").status_code == 404


def test_start_auf_englisch(api, club, zugang, settings):
    settings.HUBIPLAN_LANGUAGES = ["de", "en"]
    user, access = zugang
    _termin(club, "Sommerfest", 5, rsvp_enabled=True)
    user.language = "en"
    user.save(update_fields=["language"])
    data = api(user).get(f"/api/portal/{access.pk}/start/").json()
    assert data["todo"][0]["title"] == "1 event is waiting for your reply"
