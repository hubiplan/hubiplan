# ruff: noqa: F811  (Fixtures aus anderen Testmodulen)
"""Stornorechnung (konzepte/bankanbindung-stornorechnung.md, Teil A): eigener Beleg mit Nummer,
Datum und Grund; bezahlte Rechnungen mit Guthaben (erstatten oder verrechnen); Kopie als Entwurf."""

import hashlib
import uuid
from decimal import Decimal

import pytest
from django.core import mail

from billing.models import Invoice, Payment
from finance.models import Booking
from finance.vat import totals

from .test_m9_billing import _private, base, c, club, members, setup, start_run, zug  # noqa: F401

pytestmark = pytest.mark.django_db
JSON = "application/json"


def single(client, url, membership, amount="80.00", subject="Uniform", **extra):
    resp = client.post(
        f"{url}/invoices/",
        {
            "recipient_kind": "member",
            "membership": membership.pk,
            "date": "2025-03-01",
            "subject": subject,
            "lines": [{"text": subject, "amount": amount, **extra}],
        },
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.json()
    pk = resp.json()["id"]
    assert client.post(f"{url}/invoices/{pk}/finalize/").status_code == 200
    return Invoice.objects.get(pk=pk)


def pay(client, url, invoice, account, amount=None):
    data = {"date": "2025-03-10", "method": "transfer", "account": account}
    if amount is not None:
        data["amount"] = amount
    resp = client.post(
        f"{url}/invoices/{invoice.pk}/payments/",
        data,
        content_type=JSON,
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert resp.status_code == 200, resp.json()
    return resp.json()


def cancel(client, url, invoice, reason="Größe falsch berechnet"):
    return client.post(
        f"{url}/invoices/{invoice.pk}/cancel/", {"reason": reason}, content_type=JSON
    )


class TestStornobeleg:
    def test_grund_ist_pflicht(self, c, base, members):
        invoice = single(c, base, members["erika"])
        resp = cancel(c, base, invoice, reason=" ")
        assert resp.status_code == 400
        assert "reason" in resp.json()
        invoice.refresh_from_db()
        assert invoice.status == "open"

    def test_eigener_beleg_mit_nummer_datum_grund(self, c, base, members):
        invoice = single(c, base, members["erika"])
        original = c.get(f"{base}/invoices/{invoice.pk}/pdf/").content
        resp = cancel(c, base, invoice)
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert data["status"] == "cancelled"
        assert data["cancellation_number"] == f"{invoice.display_number}-S"
        assert data["cancel_reason"] == "Größe falsch berechnet"
        assert data["cancellation_date"]
        assert data["has_cancellation_pdf"] is True
        invoice.refresh_from_db()
        assert invoice.cancellation_pdf_sha256
        storno = c.get(f"{base}/invoices/{invoice.pk}/cancellation-pdf/")
        assert storno.status_code == 200
        assert storno["Content-Type"] == "application/pdf"
        assert hashlib.sha256(storno.content).hexdigest() == invoice.cancellation_pdf_sha256
        # Die ausgegebene Rechnung bleibt unverändert
        assert c.get(f"{base}/invoices/{invoice.pk}/pdf/").content == original

    def test_ohne_stornobeleg_404(self, c, base, members):
        invoice = single(c, base, members["erika"])
        assert c.get(f"{base}/invoices/{invoice.pk}/cancellation-pdf/").status_code == 404

    def test_versand_per_email(self, c, base, members):
        invoice = single(c, base, members["erika"])
        cancel(c, base, invoice)
        mail.outbox.clear()
        resp = c.post(f"{base}/invoices/{invoice.pk}/send-cancellation/")
        assert resp.status_code == 200, resp.json()
        assert resp.json()["cancellation_sent_at"]
        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert f"{invoice.display_number}-S" in msg.subject
        assert "Größe falsch berechnet" in msg.body
        assert msg.attachments[0][0].startswith("Stornorechnung-")


class TestBezahlt:
    def test_bezahlte_rechnung_stornieren_und_erstatten(self, club, c, base, setup, members):
        invoice = single(c, base, members["erika"], vat_rate="19.00")
        pay(c, base, invoice, setup["bank"])
        invoice.refresh_from_db()
        assert invoice.status == "paid"
        resp = cancel(c, base, invoice)
        assert resp.status_code == 200, resp.json()
        assert resp.json()["status"] == "cancelled"
        assert resp.json()["credit"] == "80.00"
        # Eine Zahlung an einer stornierten Rechnung ändert den Status nicht mehr
        resp = c.post(f"{base}/invoices/{invoice.pk}/refund/")
        assert resp.status_code == 200, resp.json()
        assert resp.json()["status"] == "cancelled"
        assert resp.json()["credit"] == "0.00"
        assert not Payment.objects.filter(invoice=invoice).exists()
        counter = Booking.objects.get(cancels__isnull=False)
        assert counter.amount == Decimal("80.00")
        assert "-S" in counter.text
        # Einnahme und Erstattung heben sich in Kasse und Umsatzsteuer auf
        income = Booking.objects.get(pk=counter.cancels_id)
        assert income.kind == "income"
        assert c.post(f"{base}/invoices/{invoice.pk}/refund/").status_code == 400

    def test_guthaben_verrechnen(self, c, base, setup, members):
        erika = members["erika"]
        old = single(c, base, erika, amount="30.00", subject="Fahne")
        pay(c, base, old, setup["bank"])
        cancel(c, base, old)
        other = single(c, base, members["jung"], amount="50.00", subject="Fahrt")
        target = single(c, base, erika, amount="50.00", subject="Fahrt")
        targets = c.get(f"{base}/invoices/{old.pk}/credit-targets/").json()
        assert [t["id"] for t in targets] == [target.pk]
        resp = c.post(f"{base}/invoices/{old.pk}/credit/", {"target": other.pk}, content_type=JSON)
        assert resp.status_code == 400
        resp = c.post(f"{base}/invoices/{old.pk}/credit/", {"target": target.pk}, content_type=JSON)
        assert resp.status_code == 200, resp.json()
        assert resp.json()["credit"] == "0.00"
        target.refresh_from_db()
        assert target.paid == Decimal("30.00")
        assert target.status == "open"
        assert Booking.objects.filter(cancels__isnull=False).count() == 0

    def test_guthaben_hoeher_als_offen(self, c, base, setup, members):
        erika = members["erika"]
        old = single(c, base, erika, amount="80.00")
        pay(c, base, old, setup["bank"])
        cancel(c, base, old)
        target = single(c, base, erika, amount="20.00", subject="Fahrt")
        resp = c.post(f"{base}/invoices/{old.pk}/credit/", {"target": target.pk}, content_type=JSON)
        assert resp.status_code == 400
        assert "höher" in str(resp.json())


class TestNeuAnlegen:
    def test_kopie_als_entwurf(self, c, base, members):
        assert (
            c.patch(f"{base}/settings/", {"vat_enabled": True}, content_type=JSON).status_code
            == 200
        )
        invoice = single(c, base, members["erika"], vat_rate="19.00")
        cancel(c, base, invoice)
        resp = c.post(f"{base}/invoices/{invoice.pk}/copy/")
        assert resp.status_code == 200, resp.json()
        copy = resp.json()
        assert copy["status"] == "draft"
        assert copy["id"] != invoice.pk
        assert copy["total"] == "80.00"
        assert copy["subject"] == "Uniform"
        assert copy["lines"][0]["vat_rate"] == "19.00"
        assert copy["membership"] == invoice.membership_id

    def test_beitragslauf_nicht_kopierbar(self, c, base, members):
        run = start_run(c, base).json()
        c.post(f"{base}/runs/{run['id']}/finalize/")
        invoice = Invoice.objects.get(membership=members["erika"])
        assert c.get(f"{base}/invoices/{invoice.pk}/").json()["copyable"] is False
        cancel(c, base, invoice)
        assert c.post(f"{base}/invoices/{invoice.pk}/copy/").status_code == 400


def test_vat_erstattung_mindert_umsatz(club, c, base, setup, members):
    """Die Erstattung ist ein Storno der Einnahme und zählt nicht als Vorsteuer."""
    from finance.models import Category

    cat = Category.objects.get(pk=setup["cat"])
    cat.vat_rate = ""
    cat.tax_area = "business"
    cat.save()
    assert c.patch(f"{base}/settings/", {"vat_enabled": True}, content_type=JSON).status_code == 200
    invoice = single(c, base, members["erika"], amount="119.00", vat_rate="19.00")
    assert invoice.lines.get().vat_rate == Decimal("19.00")
    pay(c, base, invoice, setup["bank"])
    import datetime

    t = totals([club], datetime.date(2025, 1, 1), datetime.date(2026, 12, 31))
    assert t["base_19"] == Decimal("100.00")
    assert t["tax_19"] == Decimal("19.00")
    cancel(c, base, invoice)
    assert c.post(f"{base}/invoices/{invoice.pk}/refund/").status_code == 200

    t = totals([club], datetime.date(2025, 1, 1), datetime.date(2026, 12, 31))
    assert t["base_19"] == Decimal("0.00")
    assert t["input_tax"] == Decimal("0.00")
