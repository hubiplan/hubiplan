"""Anfahrt am Termin mit Kartenlinks (konzepte/termin-rundschreiben-rueckmeldung.md, T5)."""
# ruff: noqa: F811  (Fixtures aus test_m12_events als Parameter)

import pytest
from django.core import mail as djmail

from events import maps, notify

from .factories import make_member
from .test_m12_events import (  # noqa: F401  (Fixtures)
    JSON,
    cal,
    create,
    org_base,
    zug,
)

pytestmark = pytest.mark.django_db


def test_links_mit_punkt_und_mit_anschrift():
    found = maps.links("Festzelt", "Wiesenweg 1, 41468 Neuss", 51.17, 6.75)
    assert found["osm"] == "https://www.openstreetmap.org/directions?route=%3B51.17000%2C6.75000"
    assert "destination=51.17000%2C6.75000" in found["google"]
    found = maps.links("Festzelt", "Wiesenweg 1", None, None)
    assert found["osm"].endswith("query=Wiesenweg+1")
    assert "destination=Festzelt%2C+Wiesenweg+1" in found["google"]
    assert maps.links("Festzelt", "", None, None) == {}


def test_anfahrt_im_termin_und_in_der_mail(cal, board_a, zug, api):
    club = cal["a"]
    make_member(club, "Anna", "Adler", departments=[zug])
    c = api(board_a)
    base = org_base(club)
    ev = create(
        c,
        base,
        title="Königsschießen",
        location="Schießstand",
        address="Waldweg 3",
        directions="Parken am Sportplatz, 5 Minuten zu Fuß.",
        latitude="51.17123",
        longitude="6.75456",
        starts_at="2099-06-13T14:00:00",
        ends_at="2099-06-13T18:00:00",
    )
    assert ev["directions"].startswith("Parken")
    assert ev["latitude"] == 51.17123 and ev["map_links"]["osm"].endswith("6.75456")
    djmail.outbox.clear()
    assert notify.send(ev["id"], notify.INVITE) == 1
    body = djmail.outbox[0].body
    assert "Anfahrt: Parken am Sportplatz" in body
    assert "Route (OpenStreetMap): https://www.openstreetmap.org/directions" in body
    # Nur Breite ohne Länge geht nicht
    resp = c.patch(f"{base}events/{ev['id']}/", {"longitude": None}, content_type=JSON)
    assert resp.status_code == 400 and "latitude" in resp.json()
