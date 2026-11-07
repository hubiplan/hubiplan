"""Belegung von Infrastruktur und Material auf der Webseite (alles erfunden)."""

import datetime
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from django.utils import timezone

from bookings.models import Booking
from bookings.services import rebuild
from materials.models import MaterialItem
from website import menu
from website.models import Website
from website.public import SiteView

pytestmark = pytest.mark.django_db
KEY = "belegung-a"
BERLIN = ZoneInfo("Europe/Berlin")
ADDRESS = {"street": "Musterweg 1", "postal_code": "12345", "city": "Musterstadt", "country": "DE"}


def public(path):
    return Client().get(f"/api/public/site/v1/{KEY}/{path}")


@pytest.fixture
def setup(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "website", "infrastructure", "bookings"]
    org.save()
    site = Website.objects.create(organization=org, public_key=KEY, state="public")
    house = MaterialItem.objects.create(
        organization=org,
        kind="facility",
        title="Schützenhaus",
        description="Vereinsheim",
        location_kind="address",
        address=ADDRESS,
        facility_type="building",
        booking_rules={"enabled": True, "website": "titles"},
    )
    hidden = MaterialItem.objects.create(
        organization=org,
        kind="facility",
        title="Werkstatt",
        description="x",
        location_kind="address",
        address=ADDRESS,
        facility_type="storage",
        booking_rules={"enabled": True},
    )
    day = timezone.localdate() + datetime.timedelta(days=1)

    def booking(item, title, hour, visibility):
        start = datetime.datetime.combine(day, datetime.time(hour), BERLIN)
        b = Booking.objects.create(
            organization=org,
            item=item,
            title=title,
            starts_at=start,
            ends_at=start + datetime.timedelta(hours=2),
            status="confirmed",
            visibility=visibility,
        )
        rebuild(b)
        return b

    booking(house, "Seniorennachmittag", 14, "public")
    booking(house, "Geburtstag Familie Muster", 18, "members")
    booking(hidden, "Inventur", 10, "public")
    return {"org": org, "site": site, "house": house}


def test_belegung_erst_nach_einschalten_und_ohne_private_zwecke(setup):
    assert public("bookings/").status_code == 404
    site = setup["site"]
    site.blocks = {**(site.blocks or {}), "bookings": True}
    site.save()
    data = public("bookings/").json()
    assert [i["title"] for i in data["items"]] == ["Schützenhaus"]
    titles = sorted(r["title"] for r in data["occurrences"])
    assert titles == ["Belegt", "Seniorennachmittag"]
    assert "Musterstraße" not in str(data)
    ics = public("bookings.ics")
    assert ics.status_code == 200
    body = ics.content.decode()
    assert "Seniorennachmittag" in body
    assert "Familie Muster" not in body
    assert "Inventur" not in body
    assert menu._available(SiteView(site), "bookings")


def test_nur_belegt(setup):
    site = setup["site"]
    site.blocks = {**(site.blocks or {}), "bookings": True}
    site.save()
    house = setup["house"]
    house.booking_rules = {"enabled": True, "website": "busy"}
    house.save()
    titles = {r["title"] for r in public("bookings/").json()["occurrences"]}
    assert titles == {"Belegt"}
