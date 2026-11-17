# ruff: noqa: F811  (Fixtures aus test_mitgliedsantrag als Parameter)
"""Ermäßigung mit Nachweis im Online-Mitgliedsantrag (Fachfrage F10)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from core.tenancy import rls_bypass, tenant_context
from feeproofs.models import ApplicationProof, DiscountAssignment, FeeProof, ProofDiscount

from .test_beitragsnachweise import bescheinigung
from .test_mitgliedsantrag import club, leichte_aufgabe, schema, submit_and_confirm  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def test_antrag_mit_ermaessigung_und_nachweis(club):
    org = club["org"]
    with tenant_context(org.pk):
        rabatt = ProofDiscount.objects.create(
            organization=org, name="Studierende", discount_percent=50
        )
    offered = schema(club["key"])["discounts"]
    assert [d["name"] for d in offered] == ["Studierende"]
    app, token = submit_and_confirm(club, discount=rabatt.pk)
    status = Client().get(f"/api/public/join/application/{token}/").json()
    assert status["fee_proof"]["name"] == "Studierende" and status["fee_proof"]["can_upload"]
    res = Client().post(
        f"/api/public/join/application/{token}/fee-proof/",
        {"file": SimpleUploadedFile("b.pdf", bescheinigung("Max"), content_type="application/pdf")},
    )
    assert res.status_code == 201, res.content
    assert res.json()["fee_proof"]["files"] == ["b.pdf"]
    c = club["client"]
    base = f"/api/orgs/{org.pk}/admission/{app.pk}/"
    detail = c.get(base).json()
    assert detail["fee_proof"]["files"][0]["precheck"]["level"] in ("green", "yellow", "red")
    res = c.post(f"{base}accept/", {"invite": False}, "application/json")
    assert res.status_code == 200, res.content
    app.refresh_from_db()
    with rls_bypass():
        assert DiscountAssignment.objects.filter(membership_id=app.membership_id).count() == 1
        proof = FeeProof.objects.get(membership_id=app.membership_id)
        assert proof.channel == "application" and proof.file
        assert not ApplicationProof.objects.exists()


def test_ermaessigung_nur_passend(club):
    org = club["org"]
    with tenant_context(org.pk):
        rabatt = ProofDiscount.objects.create(
            organization=org, name="Nur Fördernde", amount=10, member_type=club["foerder"]
        )
    from .test_mitgliedsantrag import submit

    res = submit(club["key"], discount=rabatt.pk)
    assert res.status_code == 400 and "discount" in res.json()
