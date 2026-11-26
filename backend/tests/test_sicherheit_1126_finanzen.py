"""Sicherheitsprüfung 26.11.2026, Paket 2: Kasse, Rechnungen, GoBD (erfundene Daten)."""

# ruff: noqa: F811  (Fixtures als Parameter)
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from billing import sepa
from billing import services as billing_services
from billing.models import Invoice, Mandate
from core.tenancy import tenant_context
from finance import artist_fees, gobd, quittung
from finance.models import Booking, Category, Receipt, VatRate, YearClosing

from .factories import make_member
from .test_gesamtaudit_1111_abschluss import (  # noqa: F401
    _close,
    _private,
    club,
    fin,
    kasse,
    setup,
    vorstand,
)

pytestmark = pytest.mark.django_db
JSON = "application/json"
IBAN = "DE02120300000000202051"


def _fails(fn, exc=IntegrityError) -> bool:
    try:
        with transaction.atomic():
            fn()
    except exc:
        return True
    return False


# --- B-H02: Abschluss aufheben gibt Kategorie und Bereich der Buchungen wieder frei ---


def test_abschluss_aufheben_loest_festgehaltene_kategorie(vorstand, fin, club, setup):
    _close(vorstand, fin)
    with tenant_context(club.pk):
        booking = Booking.objects.get(pk=setup["booking"])
        assert booking.frozen and booking.frozen_category_name == "Spenden"
    resp = vorstand.delete(
        f"{fin}/closings/?jahr=2024", {"reason": "Buchung in falscher Kategorie"}, JSON
    )
    assert resp.status_code == 200, resp.content
    with tenant_context(club.pk):
        booking.refresh_from_db()
        assert not booking.frozen and booking.frozen_category_name == ""
        # Eine umbenannte Kategorie zeigt sich jetzt in den Auswertungen
        Category.objects.filter(pk=setup["cat"]).update(name="Zuwendungen")
        booking.refresh_from_db()
        assert booking.category_label == "Zuwendungen"


# --- B-H04: Guthaben nur mit Rechnungen desselben Empfängers verrechnen ---


def test_guthaben_nicht_zwischen_haushalten():
    a = Invoice(recipient_kind=Invoice.Recipient.HOUSEHOLD, household_id=1)
    b = Invoice(recipient_kind=Invoice.Recipient.HOUSEHOLD, household_id=2)
    same = Invoice(recipient_kind=Invoice.Recipient.HOUSEHOLD, household_id=1)
    assert not billing_services._same_recipient(a, b)
    assert billing_services._same_recipient(a, same)
    # Ohne festen Bezug (Teilnehmende, freie Empfänger) lässt sich nichts verrechnen
    gast = Invoice(recipient_kind=Invoice.Recipient.REGISTRATION)
    assert not billing_services._same_recipient(gast, Invoice(recipient_kind="registration"))
    frei = Invoice(recipient_kind=Invoice.Recipient.HOUSEHOLD)
    assert not billing_services._same_recipient(frei, Invoice(recipient_kind="household"))
    assert not billing_services.credit_targets(gast).exists()
    assert not billing_services.credit_targets(frei).exists()


# --- B-H01: Sperren der Datenbank für Belege und Steuerfelder festgeschriebener Buchungen ---


def test_beleg_festgeschriebener_buchung_laesst_sich_nicht_umhaengen(vorstand, fin, club, setup):
    with tenant_context(club.pk):
        booking = Booking.objects.get(pk=setup["booking"])
        receipt = Receipt.objects.create(
            organization=club,
            booking=booking,
            file="belege/erfunden.pdf",
            name="erfunden.pdf",
            content_type="application/pdf",
            size=10,
        )
    other = vorstand.post(
        f"{fin}/bookings/",
        {
            "date": "2026-02-01",
            "kind": "income",
            "amount": "5",
            "account": setup["bank"],
            "category": setup["cat"],
            "text": "Spende Winterfest",
        },
        content_type=JSON,
    ).json()["id"]
    _close(vorstand, fin)
    with tenant_context(club.pk):
        rows = Receipt.objects.filter(pk=receipt.pk)
        assert _fails(lambda: rows.update(booking_id=other))
        assert _fails(lambda: rows.update(file="belege/anderer.pdf"))
        # Ausblenden mit Grund bleibt möglich
        assert rows.update(hidden_at=timezone.now(), hidden_reason="doppelt") == 1
        fixed = Booking.objects.filter(pk=booking.pk)
        assert _fails(lambda: fixed.update(vat_rate=VatRate.STANDARD))
        # Merkmale ohne Betragswirkung bleiben änderbar
        assert fixed.update(reference="Spendenliste 3") == 1


def test_belegfreigabe_nur_fuer_zeitraum_im_geschaeftsjahr(orgs):
    org = orgs["a"]
    YearClosing.objects.get_or_create(organization=org, year=2014)
    sql = "SELECT finance_gobd_freigeben_belege(%s, %s, %s, %s)"
    fremd = [datetime.date(2015, 1, 1), datetime.date(2015, 12, 31)]
    assert _fails(lambda: gobd._call(sql, [org.pk, 2014, *fremd]))
    passend = [datetime.date(2014, 1, 1), datetime.date(2014, 12, 31)]
    with transaction.atomic():
        gobd._call(sql, [org.pk, 2014, *passend])
        transaction.set_rollback(True)


# --- B-M07: höchstens ein gültiges Mandat je Zahler ---


def test_nur_ein_gueltiges_mandat_je_zahler(orgs, board_a):
    club = orgs["a"]
    member = make_member(club, "Erika", "Muster")
    with tenant_context(club.pk):
        data = {"holder": "Erika Muster", "iban": IBAN, "bic": ""}
        today = timezone.localdate()
        first = sepa.create_mandate(
            club, membership=member, signed_on=today, source="paper", user=board_a, **data
        )
        second = sepa.create_mandate(
            club, membership=member, signed_on=today, source="paper", user=board_a, **data
        )
        first.refresh_from_db()
        assert first.status == Mandate.Status.REVOKED and second.status == Mandate.Status.ACTIVE
        assert _fails(
            lambda: Mandate.objects.create(
                organization=club,
                membership=member,
                reference="ERFUNDEN-2",
                holder="Erika Muster",
                iban=IBAN,
                signed_on=today,
                source="paper",
            )
        )


# --- B-M02: Umsatzsteuer und Künstlersozialabgabe ---


def test_quittung_uebernimmt_steuersatz(orgs):
    from finance.models import CashReceipt

    with tenant_context(orgs["a"].pk):
        cat = Category.objects.create(
            organization=orgs["a"], name="Getränke", kind="income", vat_rate=VatRate.REDUCED
        )
        assert quittung._booking_vat(CashReceipt(vat_rate=None, category=cat)) == VatRate.REDUCED
        mit = CashReceipt(vat_rate=Decimal("19.0"), category=cat)
        assert quittung._booking_vat(mit) == VatRate.STANDARD
    assert quittung._booking_vat(CashReceipt(vat_rate=None)) == ""


def test_kuenstlersozialabgabe_auf_netto(monkeypatch, orgs):
    rows = [
        Booking(id=1, amount=Decimal("119.00"), vat_rate=VatRate.STANDARD, counterparty="Band"),
        Booking(id=2, amount=Decimal("100.00"), vat_rate="", counterparty="Band"),
    ]
    for row in rows:
        row.date, row.year, row.number, row.organization = (
            datetime.date(2025, 5, 1),
            2025,
            row.id,
            orgs["a"],
        )
    monkeypatch.setattr(artist_fees, "bookings", lambda org, year: rows)
    monkeypatch.setattr(artist_fees, "_name", lambda b: "Band")
    report = artist_fees.report(orgs["a"], 2025)
    assert report["total"] == Decimal("200.00")
    assert [r["amount"] for r in report["bookings"]] == [Decimal("100.00"), Decimal("100.00")]
