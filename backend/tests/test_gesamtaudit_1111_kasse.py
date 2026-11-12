"""Gesamtaudit 11.11.2026, P-02: Die Buchungsliste zählt und lädt ohne Umwege."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from finance.models import Booking

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture(autouse=True)
def _private(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def kasse(orgs, api, board_a):
    club = orgs["a"]
    club.enabled_modules = ["finance", "members"]
    club.save()
    base = f"/api/orgs/{club.pk}/finance"
    c = api(board_a)
    ids = []
    for name, kind in (("Girokonto", "bank"), ("Barkasse", "cash")):
        resp = c.post(
            f"{base}/accounts/",
            {"name": name, "kind": kind, "opening_balance": "100", "opening_date": "2025-01-01"},
            content_type=JSON,
        )
        assert resp.status_code == 201, resp.json()
        ids.append(resp.json()["id"])
    cat = c.post(f"{base}/categories/", {"name": "Beiträge", "kind": "income"}, content_type=JSON)
    return {"c": c, "base": base, "bank": ids[0], "cash": ids[1], "cat": cat.json()["id"]}


def book(k, count, start=0):
    for i in range(start, start + count):
        resp = k["c"].post(
            f"{k['base']}/bookings/",
            {
                "date": "2025-03-01",
                "kind": "income",
                "amount": str(10 + i),
                "account": k["bank"],
                "category": k["cat"],
                "text": f"Beitrag {i}",
            },
            content_type=JSON,
        )
        assert resp.status_code == 201, resp.json()


def listing(k, query=""):
    with CaptureQueriesContext(connection) as queries:
        resp = k["c"].get(f"{k['base']}/bookings/{query}")
    assert resp.status_code == 200, resp.content
    return resp.json(), [q["sql"] for q in queries]


def test_abfragen_wachsen_nicht_mit_der_zahl_der_buchungen(kasse):
    book(kasse, 2)
    _, few = listing(kasse)
    book(kasse, 8, start=2)
    data, many = listing(kasse)
    assert data["count"] == 10
    assert len(many) == len(few)


def test_seitenzahl_wird_ohne_distinct_ueber_alle_spalten_gezaehlt(kasse):
    book(kasse, 3)
    data, sqls = listing(kasse)
    assert data["count"] == 3
    counts = [s for s in sqls if "COUNT(" in s.upper() and "finance_booking" in s]
    assert counts, sqls
    assert all("DISTINCT" not in s.upper() for s in counts)
    # Die Zählung braucht die verbundenen Tabellen nicht
    assert all("JOIN" not in s.upper() for s in counts)


def test_jede_buchung_genau_einmal_auch_mit_filtern(kasse):
    book(kasse, 3)
    resp = kasse["c"].post(
        f"{kasse['base']}/bookings/",
        {
            "date": "2025-03-02",
            "kind": "transfer",
            "amount": "20",
            "account": kasse["bank"],
            "to_account": kasse["cash"],
            "text": "Bargeld abgehoben",
        },
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.json()
    for query, expected in (
        ("", 4),
        (f"?konto={kasse['bank']}", 4),
        (f"?konto={kasse['cash']}", 1),
        ("?suche=Beitrag", 3),
        (f"?konto={kasse['bank']}&suche=Bargeld&jahr=2025", 1),
    ):
        data, _ = listing(kasse, query)
        ids = [row["id"] for row in data["results"]]
        assert data["count"] == expected == len(ids), query
        assert len(set(ids)) == len(ids), query
    assert Booking.objects.count() == 4
