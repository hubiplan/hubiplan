"""Eingehende E-Rechnungen im Hintergrund prüfen und Abgelehnte löschen (Gesamtaudit 10.11., S05).

Ohne Java: Die echte KoSIT-Prüfung decken test_einvoice_workflow.py ab.
"""
# ruff: noqa: F811

import datetime
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.utils import timezone

from billing import einvoice_validator, incoming_check, tasks
from billing.incoming_check import LOCK_KEY, check_all, check_org, purge_rejected
from billing.models import IncomingInvoice, IncomingValidation
from core.tenancy import tenant_context
from finance.models import YearClosing

from .test_m9_billing import JSON, c, club  # noqa: F401

pytestmark = pytest.mark.django_db

XML = (Path(__file__).parent / "data" / "einvoice-en16931.xml").read_bytes()


@pytest.fixture(autouse=True)
def private(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def checks(monkeypatch):
    """Schnelle Prüfung statt Java; merkt sich das Zeitlimit jedes Aufrufs."""
    calls = []

    def validate(xml, timeout=None):
        calls.append(timeout)
        return {"status": "valid", "validator": "Test", "messages": []}, b"<report/>"

    monkeypatch.setattr(einvoice_validator, "validate", validate)
    return calls


def upload(c, club, data, name="invoice.xml"):
    response = c.post(
        f"/api/orgs/{club.pk}/finance/incoming/",
        {"file": SimpleUploadedFile(name, data, content_type="application/xml")},
    )
    assert response.status_code in (200, 201), response.content
    return response.json()


def variant(number):
    # Gleiche Rechnung, andere Datei (anderer SHA-256)
    return XML + f"<!-- {number} -->".encode()


def test_upload_waits_and_schedules_after_commit(
    c, club, checks, monkeypatch, django_capture_on_commit_callbacks, settings
):
    started = []
    monkeypatch.setattr(tasks.check_incoming, "delay", started.append)
    with django_capture_on_commit_callbacks(execute=True):
        item = upload(c, club, XML)
    assert item["validation"] == "pending" and item["report"]["status"] == "pending"
    assert item["data"]["payable"] == "119.00" and not item["has_report"]
    assert started == [club.pk] and checks == []
    assert check_org(club.pk) == 1
    assert checks == [settings.EINVOICE_VALIDATOR_BACKGROUND_TIMEOUT]
    item = c.get(f"/api/orgs/{club.pk}/finance/incoming/{item['id']}/").json()
    assert item["validation"] == "done" and item["report"]["status"] == "valid"
    assert item["has_report"]
    assert check_org(club.pk) == 0


def test_broker_missing_keeps_upload(
    c, club, checks, monkeypatch, django_capture_on_commit_callbacks
):
    def offline(org_id):
        raise ConnectionError("kein Broker")

    monkeypatch.setattr(tasks.check_incoming, "delay", offline)
    with django_capture_on_commit_callbacks(execute=True):
        item = upload(c, club, XML)
    assert item["validation"] == "pending"
    # Der minütliche Nachlauf holt die Prüfung nach.
    assert check_all() == 1
    with tenant_context(club.pk):
        assert IncomingInvoice.objects.get(pk=item["id"]).report["status"] == "valid"


def test_unreadable_upload_is_done_at_once(c, club, checks):
    item = upload(c, club, b"keine Rechnung")
    assert item["validation"] == "done" and item["report"]["status"] == "invalid"
    assert check_org(club.pk) == 0 and checks == []


def test_one_check_per_club_at_a_time(c, club, checks):
    first = upload(c, club, variant(1))
    second = upload(c, club, variant(2))
    other = connections.create_connection("default")
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s, %s)", [club.pk, LOCK_KEY])
        # Läuft schon eine Prüfung für den Verein, startet keine zweite.
        assert check_org(club.pk) == 0 and checks == []
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [club.pk, LOCK_KEY])
    finally:
        other.close()
    # Wer die Sperre hat, prüft alle wartenden Eingänge nacheinander.
    assert check_org(club.pk) == 2 and len(checks) == 2
    with tenant_context(club.pk):
        states = IncomingInvoice.objects.filter(pk__in=[first["id"], second["id"]])
        assert {row.validation for row in states} == {"done"}


def test_revalidate_runs_in_background(c, club, checks):
    item = upload(c, club, XML)
    check_org(club.pk)
    path = f"/api/orgs/{club.pk}/finance/incoming/{item['id']}"
    response = c.post(f"{path}/revalidate/", {}, content_type=JSON)
    assert response.status_code == 200 and response.json()["validation"] == "pending"
    assert len(checks) == 1
    # Zweimal klicken legt keine zweite Vorprüfung an.
    c.post(f"{path}/revalidate/", {}, content_type=JSON)
    with tenant_context(club.pk):
        assert IncomingValidation.objects.filter(incoming_id=item["id"]).count() == 1
    assert check_org(club.pk) == 1
    assert c.get(f"{path}/").json()["report"]["status"] == "valid"


def test_timeout_in_background_is_reported(c, club, monkeypatch):
    monkeypatch.setattr(
        einvoice_validator,
        "validate",
        lambda xml, timeout=None: einvoice_validator.failed("Zeit abgelaufen", "unavailable"),
    )
    item = upload(c, club, XML)
    assert check_org(club.pk) == 1
    item = c.get(f"/api/orgs/{club.pk}/finance/incoming/{item['id']}/").json()
    assert item["validation"] == "done" and item["report"]["status"] == "unavailable"


def test_purge_rejected_and_unreadable_after_90_days(c, club, checks):
    path = f"/api/orgs/{club.pk}/finance/incoming"
    rejected = upload(c, club, variant(1))
    recent = upload(c, club, variant(2))
    invalid = upload(c, club, variant(3))
    approved = upload(c, club, variant(4))
    upload(c, club, b"keine Rechnung")  # nicht lesbar: wird gelöscht
    check_org(club.pk)
    c.post(f"{path}/{rejected['id']}/revalidate/", {}, content_type=JSON)
    check_org(club.pk)
    for item, decision in ((rejected, "rejected"), (recent, "rejected"), (approved, "approved")):
        response = c.post(
            f"{path}/{item['id']}/review/",
            {"status": decision, "note": "Geprüft"},
            content_type=JSON,
        )
        assert response.status_code == 200, response.content
    now = timezone.now()
    old = now - datetime.timedelta(days=91)
    with tenant_context(club.pk):
        IncomingInvoice.objects.update(created_at=old)
        IncomingInvoice.objects.filter(pk__in=[rejected["id"], approved["id"]]).update(
            reviewed_at=old
        )
        # Lesbar, aber fehlerhaft: bleibt, bis jemand ablehnt
        row = IncomingInvoice.objects.get(pk=invalid["id"])
        row.report = {"status": "invalid", "messages": []}
        row.save()
    assert purge_rejected(now) == 2
    with tenant_context(club.pk):
        left = set(IncomingInvoice.objects.values_list("pk", flat=True))
        assert left == {recent["id"], invalid["id"], approved["id"]}
        assert not IncomingValidation.objects.exists()
        from audit.models import AuditEntry

        assert AuditEntry.objects.filter(
            organization=club, action="delete", object_id=str(rejected["id"])
        ).exists()


def test_purge_respects_retention_hold(c, club, checks):
    item = upload(c, club, b"keine Rechnung")
    old = timezone.now() - datetime.timedelta(days=91)
    with tenant_context(club.pk):
        IncomingInvoice.objects.update(created_at=old)
        YearClosing.objects.create(
            organization=club,
            year=club.fiscal_year_of(timezone.localdate(old)),
            retention_hold="Betriebsprüfung",
        )
    assert purge_rejected() == 0
    with tenant_context(club.pk):
        assert IncomingInvoice.objects.filter(pk=item["id"]).exists()


def test_purge_skips_pending(c, club, checks):
    item = upload(c, club, XML)
    with tenant_context(club.pk):
        IncomingInvoice.objects.update(created_at=timezone.now() - datetime.timedelta(days=91))
    assert purge_rejected() == 0
    assert incoming_check.check_org(club.pk) == 1
    with tenant_context(club.pk):
        assert IncomingInvoice.objects.get(pk=item["id"]).data
