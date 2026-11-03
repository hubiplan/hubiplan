"""Gesamtaudit 03.11.2026, GA-F10: ausgeschaltet angelegter Fremdkalender ruft nichts ab.

Erfundene Daten."""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest

from events.models import Event

from .test_fremde_kalender import add, cal, remote, vp_event  # noqa: F401

pytestmark = pytest.mark.django_db


def test_inaktiv_angelegt_holt_nichts(cal, board_a, api, remote):
    remote.vp_events = [vp_event("00000001-aaaa", "Termin 1")]
    data = add(api(board_a), cal["a"], is_active=False)
    assert remote.calls == []
    assert data["event_count"] == 0
    assert not Event.objects.filter(title="Termin 1").exists()


def test_aktiv_angelegt_holt_weiter(cal, board_a, api, remote):
    remote.vp_events = [vp_event("00000001-aaaa", "Termin 1")]
    data = add(api(board_a), cal["a"])
    assert remote.calls and data["event_count"] == 1
