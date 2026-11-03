"""Gesamtaudit 03.11.2026: Regressionstests zu GA-S12 und GA-P04 (erfundene Daten)."""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime

import pytest
from django.utils import timezone

from events import external
from finance.models import BankStatement, YearClosing

from .test_kontoauszug import camt_xml, entry, fin, upload  # noqa: F401
from .test_m9_billing import c, club, members, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db

# --- GA-S12: Kontoauszug eines abgeschlossenen Geschäftsjahrs bleibt ---


@pytest.mark.parametrize("sperre", ["", "Prüfung durch das Finanzamt"])
def test_auszug_im_abgeschlossenen_jahr_bleibt(c, fin, club, sperre):
    st = upload(c, fin, camt_xml([entry("4.00", ref="F1")])).json()["statements"][0]
    YearClosing.objects.create(organization=club, year=2025, retention_hold=sperre)
    resp = c.delete(f"{fin}/bank-statements/{st['id']}/")
    assert resp.status_code == 400, resp.content
    assert "abgeschlossenen Geschäftsjahr" in str(resp.json())
    assert BankStatement.objects.filter(pk=st["id"]).exclude(source="").exists()


def test_auszug_anderes_jahr_abgeschlossen_loeschbar(c, fin, club):
    st = upload(c, fin, camt_xml([entry("4.00", ref="F1")])).json()["statements"][0]
    YearClosing.objects.create(organization=club, year=2024)
    assert c.delete(f"{fin}/bank-statements/{st['id']}/").status_code == 204


# --- GA-P04: Serien fremder Kalender werden begrenzt aufgefaltet ---


def _fenster():
    now = timezone.now()
    return now - datetime.timedelta(days=30), now + datetime.timedelta(days=365)


def test_serie_im_sekundentakt_wird_nicht_aufgefaltet():
    since, until = _fenster()
    start = since - datetime.timedelta(days=3650)
    for rule in ("FREQ=SECONDLY", "FREQ=MINUTELY;INTERVAL=1", "freq = secondly"):
        assert external._expand(start, rule, [], datetime.timedelta(), since, until) == [start]


def test_serien_teilen_ein_schrittbudget():
    since, until = _fenster()
    start = since - datetime.timedelta(days=100)
    budget = [500]
    first = external._expand(start, "FREQ=HOURLY", [], datetime.timedelta(), since, until, budget)
    # 100 Tage vor dem Fenster sind 2.400 Schritte: das Budget reicht nicht bis ins Fenster
    assert first == [] and budget == [0]
    second = external._expand(start, "FREQ=DAILY", [], datetime.timedelta(), since, until, budget)
    assert second == []


def test_normale_serie_unveraendert():
    since, until = _fenster()
    start = since + datetime.timedelta(days=1)
    moments = external._expand(
        start, "FREQ=WEEKLY;COUNT=5", [start], datetime.timedelta(hours=2), since, until
    )
    assert moments == [start + datetime.timedelta(weeks=n) for n in range(1, 5)]
