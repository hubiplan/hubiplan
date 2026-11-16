"""Termine nur aus dem Zeitraum laden (Gesamtaudit 15.11., PF-12). Erfundene Daten.

Kalender, iCal-Abos und Webseite luden bei jedem Abruf die ganze Terminhistorie samt Joins und
filterten erst in Python. Jetzt filtert ``occurrences`` QuerySets vorab in der Datenbank. Das
Ergebnis muss genau dasselbe bleiben wie ohne Vorfilter.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.tenancy import rls_bypass
from events.models import CalendarPublication, Event, EventException
from events.recurrence import in_window, occurrences

from .test_m12_events import at, cal  # noqa: F401

pytestmark = pytest.mark.django_db


def _event(org, title, start, hours=2, **kw):
    return Event.objects.create(
        organization=org,
        title=title,
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=hours),
        visibility=kw.pop("visibility", "public"),
        **kw,
    )


def _keys(items):
    return [(o.event.pk, o.original_start, o.starts_at, o.ends_at, o.is_cancelled) for o in items]


@pytest.fixture
def historie(cal):
    org = cal["a"]
    with rls_bypass():
        # 15 Jahre alte Einzeltermine
        for year in range(2010, 2025):
            for month in (3, 6, 9):
                _event(org, f"Alt {year}-{month}", at(year, month, 10, 19))
        # Serie ohne Ende seit 2015, wöchentlich
        weekly = _event(org, "Übungsabend", at(2015, 1, 6, 19), repeat="weekly")
        # Serie mit Ende, längst vorbei
        _event(
            org,
            "Alte Serie",
            at(2012, 1, 1, 10),
            repeat="monthly",
            repeat_until=datetime.date(2013, 1, 1),
        )
        # Serie mit Ende im Zeitraum
        _event(
            org,
            "Endet bald",
            at(2026, 1, 5, 18),
            repeat="weekly",
            repeat_until=datetime.date(2026, 6, 1),
        )
        # Serie, deren Termin aus der Vergangenheit in den Zeitraum verschoben ist
        moved = _event(
            org,
            "Verschoben",
            at(2024, 2, 1, 18),
            repeat="monthly",
            repeat_until=datetime.date(2024, 3, 1),
        )
        EventException.objects.create(
            organization=org,
            event=moved,
            original_start=at(2024, 3, 1, 18),
            starts_at=at(2026, 5, 20, 18),
            ends_at=at(2026, 5, 20, 20),
        )
        # Serie, die erst nach dem Zeitraum beginnt, mit einem vorgezogenen Termin darin
        later = _event(org, "Vorgezogen", at(2026, 9, 1, 18), repeat="weekly")
        EventException.objects.create(
            organization=org,
            event=later,
            original_start=at(2026, 9, 1, 18),
            starts_at=at(2026, 5, 15, 18),
            ends_at=at(2026, 5, 15, 20),
        )
        # Serie, die vor mehr als 400 Tagen endete; ihr letzter Termin in den Zeitraum verlegt
        old = _event(
            org,
            "Lange vorbei",
            at(2023, 1, 10, 18),
            repeat="monthly",
            repeat_until=datetime.date(2023, 6, 10),
        )
        EventException.objects.create(
            organization=org,
            event=old,
            original_start=at(2023, 6, 10, 18),
            starts_at=at(2026, 5, 25, 18),
            ends_at=at(2026, 5, 25, 20),
        )
        # Gestrichener Termin der Wochenserie im Zeitraum
        EventException.objects.create(
            organization=org, event=weekly, original_start=at(2026, 5, 12, 19), is_cancelled=True
        )
        # Ganztägig, mehrtägig über den Beginn des Zeitraums
        _event(org, "Schützenfest", at(2026, 4, 28, 0), hours=96, all_day=True)
        # Über die Zeitumstellung (29.03.2026)
        _event(org, "Nachtwanderung", at(2026, 3, 28, 22), hours=6)
        # Künftig
        _event(org, "Königsschießen", at(2026, 7, 4, 14))
    return org


@pytest.mark.parametrize(
    "start,end",
    [
        (at(2026, 5, 1), at(2026, 6, 1)),
        (at(2026, 3, 1), at(2026, 4, 1)),
        (at(2026, 4, 30), at(2026, 5, 2)),
        (at(2014, 1, 1), at(2027, 1, 1)),
    ],
)
def test_ergebnis_wie_ohne_vorfilter(historie, start, end):
    with rls_bypass():
        qs = Event.objects.filter(organization=historie)
        before = occurrences(list(qs), start, end)  # Liste: kein Vorfilter, alter Weg
        after = occurrences(qs, start, end)
    assert _keys(after) == _keys(before)
    assert after  # der Vergleich hat etwas zu vergleichen


def test_verschobene_und_gestrichene_ausnahmen(historie):
    with rls_bypass():
        items = occurrences(
            Event.objects.filter(organization=historie), at(2026, 5, 1), at(2026, 6, 1)
        )
    titles = {(o.event.title, o.starts_at, o.is_cancelled) for o in items}
    assert ("Verschoben", at(2026, 5, 20, 18), False) in titles
    assert ("Übungsabend", at(2026, 5, 12, 19), True) in titles
    assert ("Vorgezogen", at(2026, 5, 15, 18), False) in titles
    assert ("Lange vorbei", at(2026, 5, 25, 18), False) in titles
    assert any(t == "Schützenfest" for t, _s, _c in titles)


def test_alte_historie_wird_nicht_geladen(historie):
    with rls_bypass():
        qs = Event.objects.filter(organization=historie)
        loaded = list(in_window(qs, at(2026, 5, 1), at(2026, 6, 1)))
        total = qs.count()
    names = {e.title for e in loaded}
    # Vorher: alle Termine (über 50); jetzt nur die, die im Zeitraum vorkommen können
    assert total > 50 and len(loaded) <= 8, names
    assert not any(n.startswith("Alt ") for n in names)
    assert "Alte Serie" not in names


def test_eine_abfrage_fuer_termine_unabhaengig_von_der_historie(historie):
    with rls_bypass(), CaptureQueriesContext(connection) as ctx:
        occurrences(Event.objects.filter(organization=historie), at(2026, 5, 1), at(2026, 6, 1))
    assert len(ctx.captured_queries) <= 2  # Termine, Ausnahmen der Serien


def test_oeffentliches_abo_mit_etag(historie):
    with rls_bypass():
        _event(
            historie,
            "Interne Sitzung",
            timezone.now() + datetime.timedelta(days=3),
            visibility="members",
        )
        pub = CalendarPublication.objects.create(
            organization=historie, is_public=True, public_key="abo-test-1"
        )
    url = f"/api/public/calendar/{pub.public_key}/termine.ics"
    first = Client().get(url)
    assert first.status_code == 200 and first["ETag"]
    assert b"Interne Sitzung" not in first.content
    again = Client().get(url, HTTP_IF_NONE_MATCH=first["ETag"])
    assert again.status_code == 304 and again.content == b""
    # Ein nicht öffentlicher Termin ändert den ETag nicht (er verrät nichts darüber)
    with rls_bypass():
        _event(
            historie,
            "Noch eine interne",
            timezone.now() + datetime.timedelta(days=4),
            visibility="members",
        )
    assert Client().get(url)["ETag"] == first["ETag"]
    # Ein neuer öffentlicher Termin schon
    with rls_bypass():
        _event(historie, "Sommerfest", timezone.now() + datetime.timedelta(days=5))
    assert Client().get(url, HTTP_IF_NONE_MATCH=first["ETag"]).status_code == 200
