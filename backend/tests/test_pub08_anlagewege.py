# ruff: noqa: F401, F811  (Fixtures aus anderen Testdateien)
"""Festgeschriebene Kasse: Jeder Weg, der eine Buchung anlegt, weist ein Datum im
festgeschriebenen Zeitraum verständlich ab statt mit einem Fehler der Datenbank
(Gesamtaudit 15.11., PUB-08). Erfundene Daten.

Geprüfte Wege: Zahlung zu einer Rechnung, Auszahlung einer Auslage, Kontoumsatz buchen (einzeln
und „Vorschläge übernehmen“), Kassenzählung, Quittung abschließen und stornieren, Storno und
Splitbuchung im Kassenbuch, Verbundrechnung als bezahlt melden.
"""

import datetime
import uuid

import pytest
from django.utils import timezone

from core.tenancy import rls_bypass
from expenses.models import ExpenseClaim
from finance.models import BankLine, Booking, CashCount, CashReceipt
from organizations.models import Organization
from peering.models import RemoteInvoice

from .test_app_verwaltung_b5 import offen
from .test_auslagen import einreichen, key, ok, s
from .test_kassenzaehlung import kasse, zaehlung
from .test_kontoauszug import camt_xml, entry, fin, lines, upload
from .test_m9_billing import JSON, _private, base, c, club, members, setup, zug
from .test_quittung import bestand, draft, finalize, q, sign
from .test_verbund_kopplung import VEREIN, _setup, api, net, world
from .test_verbund_rechnungen import account, category, coupled, fed_settings, issue

pytestmark = pytest.mark.django_db


def _lock(org, until):
    Organization.objects.filter(pk=org.pk).update(finance_locked_until=until)
    org.refresh_from_db()


def _bookings(org) -> int:
    with rls_bypass():
        return Booking.objects.filter(organization_id=org.pk).count()


def _abgewiesen(resp):
    """Saubere Ablehnung (400 mit Meldung), kein Fehler der Datenbank (500)."""
    assert resp.status_code == 400, resp.content
    assert "festgeschrieben" in str(resp.json())


def _buchung(c, fin, setup, date=None):
    resp = c.post(
        f"{fin}/bookings/",
        {
            "date": (date or timezone.localdate()).isoformat(),
            "kind": "income",
            "amount": "100.00",
            "account": setup["bank"],
            "category": setup["cat"],
            "text": "Spende Erika Muster",
        },
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


# --- 1. Zahlung zu einer Rechnung (billing.services.add_payment) ---


def test_zahlung_zur_rechnung_im_festgeschriebenen_zeitraum(club, c, base, setup, offen):
    day = datetime.date(2025, 2, 10)
    _lock(club, day)
    before = _bookings(club)
    resp = c.post(
        f"{base}/invoices/{offen.pk}/payments/",
        {"date": day.isoformat(), "method": "transfer", "account": setup["bank"]},
        content_type=JSON,
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    _abgewiesen(resp)
    assert _bookings(club) == before
    assert not offen.payments.exists()


# --- 2. Auszahlung einer Auslage (expenses.services.pay) ---


def test_auslage_auszahlen_heute_festgeschrieben(s):
    claim = einreichen(s)
    url = f"{s['url']}{claim['id']}/"
    ok(
        s["kasse"].patch(
            url, {"categories": {str(claim["lines"][0]["id"]): s["cat"].pk}}, content_type=JSON
        )
    )
    ok(s["kasse"].post(url + "approve/", {}, content_type=JSON))
    _lock(s["org"], timezone.localdate())
    before = _bookings(s["org"])
    resp = s["kasse"].post(url + "pay/", {"account": s["bank"].pk}, content_type=JSON, **key())
    _abgewiesen(resp)
    assert _bookings(s["org"]) == before
    with rls_bypass():
        assert ExpenseClaim.objects.get(pk=claim["id"]).status == ExpenseClaim.Status.APPROVED


# --- 3. Kontoumsatz buchen (finance.bank_import.book und apply_suggestions) ---


def test_kontoumsatz_mit_kategorie_buchen(club, c, fin):
    data = camt_xml([entry("12.30", False, name="Druckerei", purpose="Plakate", ref="P1")])
    assert upload(c, fin, data).status_code == 201
    row = lines(c, fin)[0]
    cat = c.post(
        f"{fin}/categories/", {"name": "Werbung", "kind": "expense"}, content_type=JSON
    ).json()
    _lock(club, datetime.date(2025, 3, 3))  # Datum des Umsatzes
    before = _bookings(club)
    resp = c.post(
        f"{fin}/bank-lines/{row['id']}/assign/",
        {"action": "booking", "category": cat["id"]},
        content_type=JSON,
    )
    _abgewiesen(resp)
    assert _bookings(club) == before
    with rls_bypass():
        assert BankLine.objects.get(pk=row["id"]).status == BankLine.Status.OPEN


def test_vorschlaege_uebernehmen_meldet_festgeschriebene_umsaetze(club, c, fin, offen):
    purpose = f"Mitgliedsbeitrag {offen.display_number}"
    assert upload(c, fin, camt_xml([entry("60.00", purpose=purpose, ref="V1")])).status_code == 201
    row = lines(c, fin)[0]
    assert row["suggestion"] == "invoice"
    _lock(club, datetime.date(2025, 3, 3))
    before = _bookings(club)
    resp = c.post(f"{fin}/bank-lines/apply-suggestions/", {}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    result = resp.json()
    assert result["done"] == 0
    assert len(result["failed"]) == 1 and "festgeschrieben" in result["failed"][0]
    assert _bookings(club) == before
    with rls_bypass():
        assert BankLine.objects.get(pk=row["id"]).status == BankLine.Status.OPEN
    assert not offen.payments.exists()


# --- 4. Kassenzählung mit Differenzbuchung (finance.cash_count.create) ---


def test_kassenzaehlung_im_festgeschriebenen_zeitraum(club, c, fin, kasse):
    _lock(club, datetime.date(2025, 6, 30))  # Tag der Zählung
    before = _bookings(club)
    resp = zaehlung(
        c,
        fin,
        kasse,
        note="Wechselgeld falsch herausgegeben",
        category=kasse["Kassendifferenz"],
    )
    _abgewiesen(resp)
    assert _bookings(club) == before
    assert not CashCount.objects.exists()


# --- 5. Quittung abschließen und stornieren (finance.quittung) ---


def test_quittung_abschliessen_heute_festgeschrieben(club, c, q, bestand):
    r = draft(c, q)
    sign(c, q, r["id"], "treasurer")
    sign(c, q, r["id"], "counterparty")
    _lock(club, timezone.localdate())  # Tag der Unterschrift
    before = _bookings(club)
    _abgewiesen(finalize(c, q, r["id"]))
    assert _bookings(club) == before
    with rls_bypass():
        assert CashReceipt.objects.get(pk=r["id"]).status == CashReceipt.Status.DRAFT


def test_quittung_stornieren_heute_festgeschrieben(club, c, q, bestand):
    r = draft(c, q)
    sign(c, q, r["id"], "treasurer")
    sign(c, q, r["id"], "counterparty")
    done = finalize(c, q, r["id"])
    assert done.status_code == 200, done.json()
    _lock(club, timezone.localdate())  # Storno bucht mit heutigem Datum
    before = _bookings(club)
    resp = c.post(f"{q['url']}{r['id']}/cancel/", {"reason": "Betrag falsch"}, content_type=JSON)
    _abgewiesen(resp)
    assert _bookings(club) == before
    with rls_bypass():
        assert CashReceipt.objects.get(pk=r["id"]).status == CashReceipt.Status.FINAL


# --- 6. Storno und Splitbuchung im Kassenbuch (finance.services) ---


def test_storno_heute_festgeschrieben(club, c, fin, setup):
    b = _buchung(c, fin, setup)
    _lock(club, timezone.localdate())  # Gegenbuchung mit heutigem Datum
    before = _bookings(club)
    resp = c.post(
        f"{fin}/bookings/{b['id']}/storno/", {"reason": "doppelt erfasst"}, content_type=JSON
    )
    _abgewiesen(resp)
    assert _bookings(club) == before
    with rls_bypass():
        assert not Booking.objects.filter(cancels_id=b["id"]).exists()


def test_splitbuchung_im_festgeschriebenen_zeitraum(club, c, fin, setup):
    b = _buchung(c, fin, setup)
    other = c.post(
        f"{fin}/categories/", {"name": "Spenden Jugend", "kind": "income"}, content_type=JSON
    ).json()["id"]
    _lock(club, timezone.localdate())  # Teile bekämen das Datum der Buchung
    before = _bookings(club)
    resp = c.post(
        f"{fin}/bookings/{b['id']}/split/",
        {
            "parts": [
                {"category": setup["cat"], "amount": "60.00"},
                {"category": other, "amount": "40.00"},
            ]
        },
        content_type=JSON,
    )
    _abgewiesen(resp)
    assert _bookings(club) == before
    with rls_bypass():
        assert str(Booking.objects.get(pk=b["id"]).amount) == "100.00"


# --- 7. Verbundrechnung als bezahlt melden (peering.packet_invoices.report_paid) ---


def test_verbundrechnung_bezahlt_melden_heute_festgeschrieben(net, world):
    verein = world["club"]
    lower, upper = coupled(net, world)
    fed_settings(world["fed"])
    issue(net, world, upper)
    incoming = RemoteInvoice.objects.get(coupling=lower)
    konto, kat = account(verein), category(verein, "expense")
    today = timezone.localdate()
    _lock(verein, today)
    before = _bookings(verein)
    with net.on(VEREIN):
        resp = api(world["club_board"]).post(
            f"/api/orgs/{verein.pk}/peering/couplings/{lower.pk}/invoices/{incoming.pk}/paid/",
            {"date": today.isoformat(), "account": konto.pk, "category": kat.pk},
            content_type=JSON,
        )
    _abgewiesen(resp)
    assert _bookings(verein) == before
    incoming.refresh_from_db()
    assert incoming.paid_reported_on is None
