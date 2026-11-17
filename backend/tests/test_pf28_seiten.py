# ruff: noqa: F401, F811  (Fixtures aus test_m12_events)
"""Lange Listen seitenweise (Gesamtaudit 15.11., PF-28): Versandprotokoll und Rückmeldungen
mit ``?seite=`` zu je 200; ohne den Parameter wie bisher alles (ältere Apps). Erfundene Daten."""

import pytest

from core import listing
from members.models import Membership

from .factories import make_member
from .test_m12_events import cal, org_base, private_root
from .test_m13_rsvp import rsvp_event

pytestmark = pytest.mark.django_db


def test_page_of_liste_und_ohne_parameter():
    items = list(range(5))
    assert listing.page_of({}, items) == (items, None)
    part, meta = listing.page_of({"seite": "1"}, items)
    assert part == items and meta == {"page": 1, "pages": 1, "total": 5, "more": False}


def test_page_of_queryset(monkeypatch, orgs):
    monkeypatch.setattr(listing, "PAGE_SIZE", 2)
    for i in range(5):
        make_member(orgs["a"], "Erika", f"Muster{i}")
    qs = Membership.objects.filter(organization=orgs["a"]).order_by("pk")
    part, meta = listing.page_of({"seite": "3"}, qs)
    assert len(list(part)) == 1 and meta["pages"] == 3 and meta["more"] is False
    _part, meta = listing.page_of({"seite": "x"}, qs)
    assert meta["page"] == 1 and meta["more"] is True


def test_rueckmeldungen_seitenweise(api, cal, board_a, monkeypatch):
    monkeypatch.setattr(listing, "PAGE_SIZE", 2)
    for i in range(5):
        make_member(cal["a"], "Ida", f"Beispiel{i}")
    data = rsvp_event(api(board_a), org_base(cal["a"]))
    base = f"{org_base(cal['a'])}events/{data['id']}/responses/"
    alles = api(board_a).get(base).json()
    assert "page" not in alles and len(alles["open"]) >= 5
    erste = api(board_a).get(base + "?seite=1").json()
    assert len(erste["open"]) == 2 and erste["page"]["more"] is True
    assert erste["summary"] == alles["summary"]
