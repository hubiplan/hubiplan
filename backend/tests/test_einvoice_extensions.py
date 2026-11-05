"""Advances without double receipts, immutable hybrid originals, safe gateway retries."""
# ruff: noqa: F811

import copy
import datetime
import hashlib
import uuid
from decimal import Decimal
from unittest.mock import Mock

import pytest
import requests
from django.core.exceptions import ValidationError
from django.test import override_settings

from billing import delivery, hybrid
from billing.advances import split_amount
from billing.einvoice_retention import export_table, purge_files
from billing.models import Invoice, InvoiceAdvance, InvoiceDelivery, InvoiceHybridArtifact
from core.tenancy import tenant_context
from finance.einvoice import as_json, parse_xml, xml_from_pdf
from finance.models import Booking

from .factories import give_role, make_user
from .test_einvoice_workflow import (  # noqa: F401
    JSON,
    base,
    c,
    club,
    draft,
    issued,
    payload,
    private,
    setup,
    zug,
)

pytestmark = pytest.mark.django_db


def pay(c, base, setup, invoice, amount="100.00"):
    result = c.post(
        f"{base}/invoices/{invoice['id']}/payments/",
        {
            "date": "2026-11-01",
            "amount": amount,
            "method": "transfer",
            "account": setup["bank"],
        },
        content_type=JSON,
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert result.status_code == 200, result.content
    return result.json()


def advance(c, base, setup, payload):
    source = issued(c, base, {**payload, "document_kind": "advance"})
    return pay(c, base, setup, source)


def test_partial_advance_final_and_cancel_preserve_single_receipt(c, base, setup, payload, club):
    source = advance(c, base, setup, payload)
    final = issued(
        c, base, {**payload, "document_kind": "final", "advance_invoices": [source["id"]]}
    )
    assert final["prepaid"] == "100.00"
    assert final["outstanding"] == "304.55"
    xml = c.get(f"{base}/electronic/{final['id']}/xml/").content
    info = parse_xml(xml)
    assert info["prepaid"] == Decimal("100") and info["payable"] == Decimal("304.55")
    assert source["number"] in info["note"] and "2026-11-01" in info["note"]
    with tenant_context(club.pk):
        assert Booking.objects.count() == 1
        assert Invoice.objects.get(pk=source["id"]).status == "settled"
        assert InvoiceAdvance.objects.get(final_invoice_id=final["id"]).active
    payment = source["payments"][0]["id"]
    assert c.delete(f"{base}/payments/{payment}/").status_code == 400
    assert (
        c.post(f"{base}/invoices/{source['id']}/cancel/", {}, content_type=JSON).status_code == 400
    )
    assert (
        c.post(f"{base}/invoices/{final['id']}/cancel/", {}, content_type=JSON).status_code == 200
    )
    with tenant_context(club.pk):
        restored = Invoice.objects.get(pk=source["id"])
        assert restored.status == "open" and restored.outstanding == Decimal("304.55")
        assert Booking.objects.count() == 1


def test_full_prepayment_is_paid_and_cancellable(c, base, setup, payload):
    source = issued(c, base, {**payload, "document_kind": "advance"})
    pay(c, base, setup, source, source["total"])
    final = issued(
        c, base, {**payload, "document_kind": "final", "advance_invoices": [source["id"]]}
    )
    assert final["status"] == "paid" and final["paid"] == "0.00" and final["outstanding"] == "0.00"
    assert (
        c.post(f"{base}/invoices/{final['id']}/cancel/", {}, content_type=JSON).status_code == 200
    )


def test_stale_advance_review_and_duplicate_allocation_rejected(c, base, setup, payload):
    source = advance(c, base, setup, payload)
    data = {**payload, "document_kind": "final", "advance_invoices": [source["id"]]}
    first, second = draft(c, base, data), draft(c, base, data)
    pay(c, base, setup, source, "10")
    assert (
        c.post(f"{base}/electronic/{first['id']}/validate/", {}, content_type=JSON).status_code
        == 400
    )
    update = c.patch(f"{base}/electronic/{first['id']}/", data, content_type=JSON)
    assert update.status_code == 200, update.content
    assert (
        c.post(f"{base}/electronic/{first['id']}/finalize/", {}, content_type=JSON).status_code
        == 200
    )
    assert (
        c.post(f"{base}/electronic/{second['id']}/finalize/", {}, content_type=JSON).status_code
        == 400
    )


def test_advance_scope_amount_and_document_kind_are_checked(c, base, setup, payload, club, orgs):
    source = advance(c, base, setup, payload)
    data = {**payload, "document_kind": "final", "advance_invoices": [source["id"]]}
    for patch in [
        {"advance_invoices": [source["id"], source["id"]]},
        {"document_kind": "invoice"},
        {"lines": [{**payload["lines"][0], "quantity": "0.01", "allowance": "0", "charge": "0"}]},
        {"advance_invoices": []},
    ]:
        response = c.post(
            f"{base}/electronic/",
            {**data, **patch},
            content_type=JSON,
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert response.status_code == 400, response.content
    with tenant_context(club.pk):
        Invoice.objects.filter(pk=source["id"]).update(organization=orgs["b"])
    response = c.post(
        f"{base}/electronic/", data, content_type=JSON, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())
    )
    assert response.status_code == 400


def test_remainder_distribution_preserves_exact_cents():
    assert split_amount(Decimal("0.01"), [Decimal(1)] * 3) == [
        Decimal("0.01"),
        Decimal(0),
        Decimal(0),
    ]


def test_incomplete_incoming_tax_identifier_remains_readable():
    xml = b"""<Invoice><ID>INCOMPLETE</ID><AccountingSupplierParty><Party>
      <PartyTaxScheme><TaxScheme><ID>VAT</ID></TaxScheme></PartyTaxScheme>
      </Party></AccountingSupplierParty><LegalMonetaryTotal><PayableAmount>1</PayableAmount>
      </LegalMonetaryTotal></Invoice>"""
    assert parse_xml(xml)["seller_vat_id"] == ""


def test_incoming_unit_price_preserves_precision_in_stored_view():
    data = as_json({"lines": [{"unit_price": Decimal("100.123456"), "amount": Decimal("100.12")}]})
    assert data["lines"][0] == {"unit_price": "100.123456", "amount": "100.12"}


def test_real_hybrid_original_and_cancellation_are_validated_and_immutable(c, base, payload, club):
    item = issued(c, base, payload)
    path = f"{base}/electronic/{item['id']}"
    original = c.get(f"{path}/xml/").content
    for cancellation in [False, True]:
        if cancellation:
            assert c.post(f"{path}/cancel/", {}, content_type=JSON).status_code == 200
        suffix = "?cancellation=1" if cancellation else ""
        result = c.post(f"{path}/hybrid/{suffix}", {}, content_type=JSON)
        assert result.status_code == 200, result.content
        pdf = c.get(f"{path}/hybrid/{suffix}").content
        assert pdf.startswith(b"%PDF")
        data = parse_xml(xml_from_pdf(pdf))
        assert data["credit_note"] == cancellation
        assert data["gross"] == Decimal("404.55")
        assert c.post(f"{path}/hybrid/{suffix}", {}, content_type=JSON).status_code == 200
        assert c.get(f"{path}/hybrid/{suffix}").content == pdf
    assert c.get(f"{path}/xml/").content == original
    with tenant_context(club.pk):
        assert InvoiceHybridArtifact.objects.count() == 2
        row = InvoiceHybridArtifact.objects.filter(document="invoice").get()
        assert row.source_sha256 == hashlib.sha256(original).hexdigest()
        assert b'isCompliant="true"' in row.pdf_report.read()
        row.pdf_report.close()
        paths = []

        def include(name, field):
            with field.open("rb") as stream:
                assert stream.read()
            paths.append(name)
            return name

        period = (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        table = export_table(club, *period, include)
        assert sum(row[0] == "ZUGFeRD" for row in table.rows) == 2
        assert len([path for path in paths if path.endswith("/pdf.pdf")]) == 2
        count = purge_files(club, *period, lambda field: field.delete(save=False))
        assert count == 12
        assert not InvoiceHybridArtifact.objects.exclude(pdf="").exists()


def test_hybrid_never_publishes_failed_conversion(c, base, payload, monkeypatch, club):
    item = issued(c, base, payload)
    monkeypatch.setattr(hybrid, "convert", Mock(side_effect=ValueError("invalid PDF/A")))
    response = c.post(f"{base}/electronic/{item['id']}/hybrid/", {}, content_type=JSON)
    assert response.status_code == 400
    with tenant_context(club.pk):
        assert not InvoiceHybridArtifact.objects.exists()


def test_extension_actions_require_write_rights_and_scope(api, c, base, payload, club, orgs):
    item = issued(c, base, payload)
    reader = make_user("invoice-reader@example.org")
    give_role(reader, club, ["billing.view"], name="E-Rechnung lesen")
    client = api(reader)
    path = f"{base}/electronic/{item['id']}"
    assert client.get(f"{path}/delivery/").status_code == 200
    for action in ["hybrid", "delivery"]:
        assert client.post(f"{path}/{action}/", {}, content_type=JSON).status_code == 403
    foreign = f"/api/orgs/{orgs['b'].pk}/billing/electronic/{item['id']}/delivery/"
    assert c.get(foreign).status_code in [403, 404]


@pytest.fixture
def gateway(settings, monkeypatch, club):
    settings.EINVOICE_GATEWAYS = {
        str(club.pk): {
            "base_url": "https://gateway.example.org/v1",
            "channel": "peppol",
            "participant": "0204:SUPPLIER-1",
            "label": "Musteranbieter",
            "token_env": "EXAMPLE_GATEWAY_TOKEN",
        }
    }
    monkeypatch.setenv("EXAMPLE_GATEWAY_TOKEN", "test-secret-only")


def gateway_payload(payload):
    data = copy.deepcopy(payload)
    for name, identifier in [("seller", "SUPPLIER-1"), ("buyer", "CUSTOMER-1")]:
        data[name].update(endpoint_scheme="0204", endpoint_id=identifier)
    return data


def test_unknown_delivery_reconciles_same_request_without_duplicate_post(
    c, base, payload, club, gateway, monkeypatch
):
    item = issued(c, base, gateway_payload(payload))
    path = f"{base}/electronic/{item['id']}/delivery/"
    calls = []

    def exchange(cfg, row, method, data=None):
        calls.append((method, str(row.request_id)))
        if len(calls) == 1:
            return None
        if len(calls) == 2:
            raise requests.Timeout()
        return {
            "request_id": str(row.request_id),
            "sha256": row.sha256,
            "status": "submitted",
            "reference": "receipt-1",
        }

    monkeypatch.setattr(delivery, "exchange", exchange)
    first = c.post(path, {}, content_type=JSON)
    assert first.status_code == 200 and first.json()["status"] == "unknown"
    second = c.post(path, {}, content_type=JSON)
    assert second.json()["status"] == "submitted"
    assert [method for method, _ in calls] == ["GET", "POST", "GET"]
    assert len({identifier for _, identifier in calls}) == 1
    c.post(path, {}, content_type=JSON)
    assert len(calls) == 3
    overview = c.get(path)
    assert b"test-secret" not in overview.content and b"gateway.example" not in overview.content
    with tenant_context(club.pk):
        assert InvoiceDelivery.objects.count() == 1


def test_gateway_rejects_unregistered_address_and_other_tenant(
    c, base, payload, club, settings, gateway
):
    item = issued(c, base, payload)
    assert (
        c.post(f"{base}/electronic/{item['id']}/delivery/", {}, content_type=JSON).status_code
        == 400
    )
    settings.EINVOICE_GATEWAYS = {}
    assert (
        c.get(f"{base}/electronic/{item['id']}/delivery/").json()["configuration"]["enabled"]
        is False
    )
    assert (
        c.post(f"{base}/electronic/{item['id']}/delivery/", {}, content_type=JSON).status_code
        == 400
    )


def test_gateway_contract_blocks_redirects_and_mismatched_receipts(
    gateway, club, monkeypatch, settings
):
    cfg = delivery.config(club)
    row = Mock(request_id="stable-id", sha256="digest")
    response = Mock(status_code=302)
    session = Mock(trust_env=True)
    session.request.return_value.__enter__ = Mock(return_value=response)
    session.request.return_value.__exit__ = Mock(return_value=False)
    factory = Mock()
    factory.return_value.__enter__ = Mock(return_value=session)
    factory.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(delivery.requests, "Session", factory)
    with pytest.raises(ValueError):
        delivery.exchange(cfg, row, "GET")
    assert session.trust_env is False
    assert session.request.call_args.kwargs["allow_redirects"] is False
    response.status_code = 200
    response.iter_content.return_value = [
        b'{"request_id":"wrong","sha256":"digest","status":"delivered"}'
    ]
    with pytest.raises(ValueError):
        delivery.exchange(cfg, row, "GET")
    bad = copy.deepcopy(settings.EINVOICE_GATEWAYS)
    bad[str(club.pk)]["base_url"] = "http://gateway.example.org"
    with override_settings(EINVOICE_GATEWAYS=bad):
        with pytest.raises(ValidationError):
            delivery.config(club)


def test_server_credential_mapping_is_used_without_exposure(gateway, club, monkeypatch, settings):
    monkeypatch.delenv("EXAMPLE_GATEWAY_TOKEN")
    settings.EINVOICE_GATEWAY_TOKENS = {"EXAMPLE_GATEWAY_TOKEN": "private-server-value"}
    assert delivery.config(club)["token"] == "private-server-value"
