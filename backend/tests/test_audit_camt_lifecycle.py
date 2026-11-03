"""CAMT-Originale: Rollback, Zeitraum und bereinigte historische Daten."""
# ruff: noqa: F811

import datetime
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection, connections, transaction
from django.utils import timezone

from core.tenancy import tenant_context
from finance import bank_import, bank_views, camt, retention, services
from finance.models import Account, BankStatement, YearClosing

from .factories import make_org, make_user
from .test_kontoauszug import camt_xml, entry
from .test_m9_billing import base, c, club, members, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db


def test_failed_import_removes_new_original_but_preserves_reused_original(club, setup):
    data = camt_xml([entry("5.00")])
    with patch.object(bank_import, "suggest_all", side_effect=RuntimeError("rollback")):
        with pytest.raises(RuntimeError, match="rollback"):
            bank_import.import_file(club, data, "test.xml", None)
    assert not BankStatement.objects.filter(organization=club).exists()
    storage = BankStatement._meta.get_field("source").storage
    saved = []
    original_save = storage.save

    def save(name, content, **kwargs):
        result = original_save(name, content, **kwargs)
        saved.append(result)
        return result

    with (
        patch.object(storage, "save", save),
        patch.object(bank_import, "suggest_all", side_effect=RuntimeError("rollback")),
    ):
        with pytest.raises(RuntimeError):
            bank_import.import_file(club, data, "test.xml", None)
    assert saved and all(not storage.exists(name) for name in saved)
    record = bank_import.import_file(club, data, "test.xml", None)["statements"][0]
    with patch.object(bank_import, "suggest_all", side_effect=RuntimeError("rollback")):
        with pytest.raises(RuntimeError):
            bank_import.import_file(club, data, "test.xml", None)
    assert record.source.storage.exists(record.source.name)
    assert BankStatement.objects.filter(organization=club).count() == 1


def test_validate_all_accounts_before_writing_any_file(club, setup):
    statements = camt.parse(camt_xml([entry("5.00")]))
    bad = camt.Statement(iban="not-an-account")
    with patch.object(camt, "parse", return_value=[*statements, bad]):
        with patch("django.db.models.fields.files.FieldFile.save") as save:
            with pytest.raises(ValidationError):
                bank_import.import_file(club, b"synthetic", "test.xml", None)
            save.assert_not_called()


def test_cleanup_storage_failure_preserves_original_error_without_logging_paths(
    club, setup, caplog
):
    original = RuntimeError("synthetic original import error")
    storage = BankStatement._meta.get_field("source").storage
    with (
        patch.object(bank_import, "suggest_all", side_effect=original),
        patch.object(storage, "delete", side_effect=OSError("private-path-must-not-be-logged")),
    ):
        with pytest.raises(RuntimeError) as error:
            bank_import.import_file(club, camt_xml([]), "test.xml", None)
    assert error.value is original
    assert "Neue Originaldatei nach Rollback nicht entfernt" in caplog.text
    assert "private-path-must-not-be-logged" not in caplog.text


def test_undated_statement_uses_line_dates_and_empty_one_import_date(club, setup):
    st = camt.parse(camt_xml([entry("5.00")]))[0]
    st.date_from = st.date_to = None
    with patch.object(camt, "parse", return_value=[st]):
        record = bank_import.import_file(club, b"synthetic", "test.xml", None)["statements"][0]
    assert record.date_from == record.date_to == datetime.date(2025, 3, 3)
    st.lines = []
    with patch.object(camt, "parse", return_value=[st]):
        record = bank_import.import_file(club, b"synthetic-empty", "empty.xml", None)["statements"][
            0
        ]
    assert record.date_from == record.date_to == timezone.localdate()


@pytest.mark.parametrize("field", ["documents_purged_at", "records_purged_at"])
def test_reimport_cannot_restore_already_purged_historical_data(club, setup, field):
    YearClosing.objects.create(organization=club, year=2025, **{field: timezone.now()})
    with pytest.raises(ValidationError, match="bereinigt"):
        bank_import.import_file(club, camt_xml([entry("5.00")]), "test.xml", None)
    assert not BankStatement.objects.filter(organization=club).exists()


def test_import_rejects_outer_rollback_boundary(club, setup):
    with transaction.atomic(), pytest.raises(RuntimeError, match="durable"):
        bank_import.import_file(club, camt_xml([entry("5.00")]), "test.xml", None)


def test_backfilled_original_can_be_purged_again_but_holds_still_apply(
    club, setup, monkeypatch, django_capture_on_commit_callbacks
):
    record = bank_import.import_file(club, camt_xml([entry("5.00")]), "test.xml", None)[
        "statements"
    ][0]
    name, storage = record.source.name, record.source.storage
    BankStatement.objects.filter(pk=record.pk).update(date_from=None, date_to=None)
    migration = import_module("finance.migrations.0022_bankstatement_retention_dates")
    migration.fill_dates(apps, SimpleNamespace(connection=connection))
    record.refresh_from_db()
    assert record.date_from == record.date_to == datetime.date(2025, 3, 3)
    closing = YearClosing.objects.create(
        organization=club, year=2025, documents_purged_at=timezone.now(), retention_hold="Prüfung"
    )
    monkeypatch.setattr(retention, "_today", lambda: datetime.date(2034, 1, 1))
    assert retention.state(club, closing)["documents_due"]
    user = make_user("retention@example.invalid")
    with pytest.raises(ValidationError, match="Löschsperre"):
        retention.purge(club, 2025, user)
    assert storage.exists(name)
    closing.retention_hold = ""
    closing.save(update_fields=["retention_hold"])
    with django_capture_on_commit_callbacks(execute=True):
        retention.purge(club, 2025, user)
    assert not storage.exists(name)
    record.refresh_from_db()
    assert record.source.name == ""
    closing.refresh_from_db()
    assert not retention.state(club, closing)["documents_due"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_delete_and_import_never_reuse_a_scheduled_deleted_path():
    org = make_org("CAMT Parallelverein")
    user = make_user("camt-race@example.invalid")
    Account.objects.create(
        organization=org,
        name="Testbank",
        iban="DE89370400440532013000",
        opening_date=datetime.date(2025, 1, 1),
    )
    with tenant_context(org.pk):
        first = bank_import.import_file(org, camt_xml([]), "empty.xml", user)["statements"][0]
    old_path = first.source.name
    queued = Event()
    release = Event()
    importing = Event()
    original_delete = bank_views.delete_on_commit
    original_lock = services.lock_bank_sources

    def delete_later(field):
        original_delete(field)
        queued.set()
        assert release.wait(10)

    def lock(org):
        if queued.is_set():
            importing.set()
        original_lock(org)

    def delete():
        try:
            with tenant_context(org.pk):
                view = bank_views.BankStatementViewSet()
                view.org = org
                view.request = SimpleNamespace(user=user)
                view.perform_destroy(first)
        finally:
            connections.close_all()

    def upload_again():
        try:
            with tenant_context(org.pk):
                return bank_import.import_file(org, camt_xml([]), "empty.xml", user)["statements"][
                    0
                ]
        finally:
            connections.close_all()

    with (
        patch.object(bank_views, "delete_on_commit", delete_later),
        patch.object(services, "lock_bank_sources", lock),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        deletion = pool.submit(delete)
        assert queued.wait(10)
        upload = pool.submit(upload_again)
        try:
            assert importing.wait(10)
            assert not upload.done()
        finally:
            release.set()
        deletion.result(timeout=10)
        second = upload.result(timeout=10)
    assert second.source.name != old_path
    assert not first.source.storage.exists(old_path)
    with second.source.open("rb") as stream:
        assert stream.read() == camt_xml([])
