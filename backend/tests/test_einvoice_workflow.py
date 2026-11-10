"""EN 16931: echte KoSIT-Prüfung, Archiv, Mandantentrennung und Rechnungseingang."""
# ruff: noqa: F811

import copy
import datetime
import hashlib
import io
import uuid
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from billing import einvoice_validator, einvoice_xml
from billing.incoming_check import check_org
from billing.models import (
    BusinessPartner,
    IncomingInvoice,
    IncomingValidation,
    Invoice,
    InvoiceArtifact,
)
from core.tenancy import tenant_context
from finance.models import Booking, Category, Receipt, YearClosing

from .test_e_rechnung import zugferd_pdf
from .test_m9_billing import JSON, base, c, club, setup, zug  # noqa: F401
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def private(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"


def party(name):
    return {
        "name": name,
        "street": "Musterstraße 1",
        "postcode": "12345",
        "city": "Musterstadt",
        "country": "DE",
        "email": "rechnung@example.org",
        "vat_id": "DE123456789",
        "tax_number": "",
        "contact": "Alex Beispiel",
        "phone": "+49 30 123456",
    }


@pytest.fixture
def payload(c, base, club):
    buyer = party("Veranstalter Beispiel")
    response = c.post(
        f"{base}/partners/", {"name": buyer["name"], "details": buyer}, content_type=JSON
    )
    assert response.status_code == 201, response.content
    with tenant_context(club.pk):
        category = Category.objects.create(organization=club, name="Leistungen", kind="income")
    return {
        "partner": response.json()["id"],
        "payment_category": category.pk,
        "date": "2026-11-01",
        "due_date": "2026-11-15",
        "subject": "Vereinsleistung",
        "seller": party("Musikverein Beispiel"),
        "buyer": buyer,
        "buyer_reference": "AUFTRAG-1",
        "service_start": "2026-10-31",
        "service_end": "2026-10-31",
        "iban": "DE89370400440532013000",
        "lines": [
            {
                "text": "Musikalische Begleitung",
                "quantity": "3",
                "unit_price": "100.00",
                "tax_category": "S",
                "tax_rate": "19",
                "allowance": "10.00",
                "charge": "5.00",
                "adjustment_reason": "Vereinbarter Nachlass und Anfahrt",
            },
            {
                "text": "Zusatzleistung",
                "quantity": "1",
                "unit_price": "50.00",
                "tax_category": "S",
                "tax_rate": "7",
            },
        ],
    }


def draft(c, base, payload, key=None):
    response = c.post(
        f"{base}/electronic/",
        payload,
        content_type=JSON,
        HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
    )
    assert response.status_code in (200, 201), response.content
    return response.json()


def issued(c, base, payload):
    item = draft(c, base, payload)
    response = c.post(f"{base}/electronic/{item['id']}/finalize/", {}, content_type=JSON)
    assert response.status_code == 200, response.content
    return response.json()


def test_official_validation_archive_and_cancellation(c, base, payload, club):
    item = issued(c, base, payload)
    assert item["total"] == "404.55"
    path = f"{base}/electronic/{item['id']}"
    xml = c.get(f"{path}/xml/").content
    report = c.post(f"{path}/validate/", {}, content_type=JSON).json()
    assert report["status"] == "valid", report
    assert b"XRechnung" in c.get(f"{path}/report/").content
    with tenant_context(club.pk):
        artifact = InvoiceArtifact.objects.get(invoice_id=item["id"])
        assert artifact.sha256 == hashlib.sha256(xml).hexdigest()
        partner = BusinessPartner.objects.get(pk=payload["partner"])
        partner.name = "Späterer Name"
        partner.save()
    assert c.get(f"{path}/xml/").content == xml
    assert (
        c.patch(
            f"{base}/invoices/{item['id']}/", {"note": "Geändert"}, content_type=JSON
        ).status_code
        == 400
    )
    result = c.post(f"{path}/cancel/", {"reason": "Testgrund Storno"}, content_type=JSON)
    assert result.status_code == 200, result.content
    cancellation = c.get(f"{path}/xml/?cancellation=1").content
    report, _ = einvoice_validator.validate(cancellation)
    assert report["status"] == "valid", report
    assert b"CreditNote" in cancellation and b"BillingReference" in cancellation
    assert c.get(f"{path}/xml/").content == xml


def test_invalid_and_unavailable_do_not_issue(c, base, payload, monkeypatch, club):
    item = draft(c, base, payload)
    monkeypatch.setattr(
        einvoice_validator,
        "validate",
        lambda xml: einvoice_validator.failed("offline", "unavailable"),
    )
    assert (
        c.post(f"{base}/invoices/{item['id']}/finalize/", {}, content_type=JSON).status_code == 400
    )
    with tenant_context(club.pk):
        invoice = Invoice.objects.get(pk=item["id"])
        assert invoice.status == "draft" and invoice.number is None
        assert not InvoiceArtifact.objects.filter(invoice=invoice).exists()
    assert c.get(f"{base}/electronic/{item['id']}/xml/").status_code == 400


def test_repeated_create_and_cross_tenant(c, base, payload, club, orgs):
    key = str(uuid.uuid4())
    first = draft(c, base, payload, key)
    assert draft(c, base, payload, key)["id"] == first["id"]
    with tenant_context(orgs["b"].pk):
        foreign = BusinessPartner.objects.create(
            organization=orgs["b"], name="Fremder Kunde", details=party("Fremder Kunde")
        )
    bad = {**payload, "partner": foreign.pk}
    assert (
        c.post(
            f"{base}/electronic/", bad, content_type=JSON, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())
        ).status_code
        == 404
    )
    with as_app_role(), tenant_context(club.pk):
        assert not BusinessPartner.objects.filter(pk=foreign.pk).exists()
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert not Invoice.objects.filter(pk=first["id"]).exists()


def test_import_original_duplicate_invalid_and_approval(c, base, payload, club):
    item = issued(c, base, payload)
    xml = c.get(f"{base}/electronic/{item['id']}/xml/").content
    incoming = f"/api/orgs/{club.pk}/finance/incoming/"

    def upload(data):
        return c.post(
            incoming,
            {"file": SimpleUploadedFile("invoice.xml", data, content_type="application/xml")},
        )

    response = upload(xml)
    assert response.status_code == 201, response.content
    received = response.json()
    # Die KoSIT-Prüfung läuft im Hintergrund, nicht in der Anfrage.
    assert received["report"]["status"] == "pending", received
    assert received["validation"] == "pending"
    assert (
        c.post(
            f"{incoming}{received['id']}/review/",
            {"status": "approved", "note": "Noch nicht geprüft"},
            content_type=JSON,
        ).status_code
        == 400
    )
    assert check_org(club.pk) == 1
    received = c.get(f"{incoming}{received['id']}/").json()
    assert received["report"]["status"] == "valid", received
    assert received["validation"] == "done" and received["has_report"]
    assert received["status"] == "review" and received["booking"] is None
    assert upload(xml).json()["id"] == received["id"]
    assert c.get(f"{incoming}{received['id']}/download/").content == xml
    approved = c.post(
        f"{incoming}{received['id']}/review/",
        {"status": "approved", "note": "Leistung und Empfänger geprüft"},
        content_type=JSON,
    )
    assert approved.status_code == 200, approved.content
    broken = upload(b"<Invoice>broken</Invoice>").json()
    check_org(club.pk)
    broken = c.get(f"{incoming}{broken['id']}/").json()
    assert broken["report"]["status"] == "invalid" and broken["validation"] == "done"
    assert (
        c.post(
            f"{incoming}{broken['id']}/review/",
            {"status": "approved", "note": "x"},
            content_type=JSON,
        ).status_code
        == 400
    )
    assert c.get(f"{incoming}{broken['id']}/download/").content == b"<Invoice>broken</Invoice>"
    with as_app_role(), tenant_context(club.pk + 100000):
        assert IncomingInvoice.objects.count() == 0
        assert InvoiceArtifact.objects.count() == 0


@pytest.mark.parametrize(
    "category,rate,reason",
    [
        ("Z", "0", ""),
        ("E", "0", "Kleinunternehmer nach § 19 UStG"),
        ("O", "0", "Nicht steuerbarer Umsatz"),
        ("AE", "0", "Steuerschuldnerschaft des Leistungsempfängers"),
    ],
)
def test_tax_categories_use_real_validator(c, base, payload, category, rate, reason):
    data = copy.deepcopy(payload)
    data["lines"] = [
        {
            "text": "Leistung",
            "quantity": "1",
            "unit_price": "100",
            "tax_category": category,
            "tax_rate": rate,
            "tax_reason": reason,
        }
    ]
    if category == "O":
        data["seller"]["vat_id"] = data["buyer"]["vat_id"] = ""
        data["seller"]["identifier"] = "MUSIKVEREIN-01"
    issued(c, base, data)


def test_group_rounding_and_decimal_precision():
    source = {
        "text": "Kleinbetrag",
        "quantity": "1",
        "unit_price": "0.03",
        "tax_category": "S",
        "tax_rate": "19",
    }
    totals = einvoice_xml.calculate([source, source, source])
    assert totals["net"] == Decimal("0.09")
    assert totals["tax"] == Decimal("0.02")
    assert sum(line["gross"] for line in totals["lines"]) == totals["gross"]
    many = einvoice_xml.calculate([source] * 200)
    assert many["tax"] == Decimal("1.14")
    assert all(Decimal("0.03") <= line["gross"] <= Decimal("0.04") for line in many["lines"])
    assert sum(line["gross"] for line in many["lines"]) == many["gross"]


def test_encoded_entities_rejected():
    xml = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE Invoice [<!ENTITY leak SYSTEM "file:///etc/passwd">]><Invoice>&leak;</Invoice>'.encode(
        "utf-16"
    )
    report, _ = einvoice_validator.validate(xml)
    assert report["status"] == "invalid"


def test_hybrid_cii_review_posting_history_and_export(c, club, setup, monkeypatch):
    instant = timezone.make_aware(datetime.datetime(2026, 11, 4, 12))
    monkeypatch.setattr(timezone, "now", lambda: instant)
    xml = (Path(__file__).parent / "data" / "einvoice-en16931.xml").read_bytes()
    pdf = zugferd_pdf(xml)
    fin = f"/api/orgs/{club.pk}/finance"
    response = c.post(
        f"{fin}/incoming/",
        {"file": SimpleUploadedFile("factur-x.pdf", pdf, content_type="application/pdf")},
    )
    assert response.status_code == 201, response.content
    value = response.json()
    assert response.get("X-Change-Undoable", "0") == "0"
    assert value["report"]["status"] == "pending" and value["data"]["payable"] == "119.00"
    assert check_org(club.pk) == 1
    value = c.get(f"{fin}/incoming/{value['id']}/").json()
    assert value["report"]["status"] == "valid", value["report"]
    assert value["data"]["payable"] == "119.00" and value["has_report"]
    path = f"{fin}/incoming/{value['id']}"
    assert c.get(f"{path}/download/?part=xml").content == xml
    assert c.get(f"{path}/download/").content == pdf
    original_report = c.get(f"{path}/download/?part=report_xml").content
    response = c.post(f"{path}/revalidate/", {}, content_type=JSON)
    assert response.status_code == 200 and response.json()["report"]["status"] == "pending"
    assert check_org(club.pk) == 1
    assert c.get(f"{path}/").json()["report"]["status"] == "valid"
    with tenant_context(club.pk):
        check = IncomingValidation.objects.get(incoming_id=value["id"])
    assert c.get(f"{path}/download/?check={check.pk}").content == original_report
    assert (
        c.post(
            f"{path}/review/", {"status": "approved", "note": "Leistung geprüft"}, content_type=JSON
        ).status_code
        == 200
    )
    category = c.post(
        f"{fin}/categories/", {"name": "Leistungen", "kind": "expense"}, content_type=JSON
    ).json()["id"]
    booking = c.post(
        f"{fin}/bookings/",
        {
            "date": "2026-11-04",
            "amount": "119.00",
            "kind": "expense",
            "category": category,
            "account": setup["bank"],
            "text": "Leistung bezahlt",
        },
        content_type=JSON,
    )
    assert booking.status_code == 201, booking.content
    booking_id = booking.json()["id"]
    for _ in range(2):
        response = c.post(f"{path}/link/", {"booking": booking_id}, content_type=JSON)
        assert response.status_code == 200, response.content
    assert (
        c.patch(
            f"{fin}/bookings/{booking_id}/", {"amount": "118.00"}, content_type=JSON
        ).status_code
        == 400
    )
    with tenant_context(club.pk):
        receipt = Receipt.objects.get(booking_id=booking_id)
        incoming = IncomingInvoice.objects.get(pk=value["id"])
        assert receipt.file.name != incoming.original.name
        with receipt.file.open("rb") as stream:
            assert stream.read() == pdf
        from changes.tracking import lock_reason

        assert lock_reason(Booking, {"id": booking_id, "year": 2026, "organization_id": club.pk})
    response = c.get(f"{fin}/export/?jahr=2026")
    assert response.status_code == 200, response.content if not response.streaming else ""
    with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
        assert "erechnungen.csv" in archive.namelist()
        originals = [name for name in archive.namelist() if name.endswith("/original.pdf")]
        assert len(originals) == 1 and archive.read(originals[0]) == pdf
        assert any(name.endswith(f"/validation-{check.pk}.xml") for name in archive.namelist())
    assert c.get(f"{fin}/incoming/").json()["count"] == 1
    from audit.models import AuditEntry
    from finance import retention

    with tenant_context(club.pk):
        YearClosing.objects.create(organization=club, year=2026)
    # Keine Bereinigung vor Ablauf der vorhandenen gesetzlichen Fristen.
    assert (
        c.post(f"{fin}/closings/aufbewahrung/", {"year": 2026}, content_type=JSON).status_code
        == 400
    )
    monkeypatch.setattr(retention, "_today", lambda: datetime.date(2037, 1, 1))
    response = c.post(f"{fin}/closings/aufbewahrung/", {"year": 2026}, content_type=JSON)
    assert response.status_code == 200, response.content
    with tenant_context(club.pk):
        incoming.refresh_from_db()
        check.refresh_from_db()
        assert not incoming.original and not incoming.xml and not incoming.report_xml
        assert incoming.report == {} and "seller" not in incoming.data
        assert not check.report_xml and check.report == {}
        assert not AuditEntry.objects.filter(
            organization=club,
            object_type="Rechnungseingang",
            object_id=str(incoming.pk),
            cleared=False,
        ).exists()


def test_payment_uses_commercial_category(c, base, club, payload, setup):
    value = issued(c, base, payload)
    response = c.post(
        f"{base}/invoices/{value['id']}/payments/",
        {
            "date": "2026-11-04",
            "amount": "404.55",
            "method": "transfer",
            "account": setup["bank"],
        },
        content_type=JSON,
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert response.status_code == 200, response.content
    with tenant_context(club.pk):
        assert Booking.objects.get(amount="404.55").category_id == payload["payment_category"]


def test_module_boundaries(c, base, club, payload):
    club.enabled_modules = ["finance"]
    club.save(update_fields=["enabled_modules"])
    assert c.get(f"{base}/partners/").status_code == 200
    assert c.get(f"{base}/electronic/").status_code == 404
    assert c.get(f"/api/orgs/{club.pk}/finance/incoming/").status_code == 200
    club.enabled_modules = ["billing"]
    club.save(update_fields=["enabled_modules"])
    assert c.get(f"{base}/partners/").status_code == 200
    assert c.get(f"/api/orgs/{club.pk}/finance/incoming/").status_code == 404
