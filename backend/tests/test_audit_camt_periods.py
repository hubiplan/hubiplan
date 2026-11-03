"""Originalschutz über Kopf-, Umsatz- und abweichende Geschäftsjahre hinweg."""

import datetime
import hashlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from rest_framework.exceptions import ValidationError as ApiValidationError

from core.tenancy import tenant_context
from finance import bank_import, bank_originals, bank_views, camt, retention
from finance.models import Account, BankLine, BankStatement, YearClosing

from .factories import make_org, make_user
from .test_kontoauszug import camt_xml, entry
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db


@pytest.fixture
def data():
    org = make_org("Perioden-Testverein")
    account = Account.objects.create(
        organization=org,
        name="Testbank",
        iban="DE89370400440532013000",
        opening_date=datetime.date(2020, 1, 1),
    )
    return org, account, make_user("periods@example.invalid")


def legacy(org, account, user, start, end, day):
    """Simuliert bereits vor der neuen Eingangsvalidierung vorhandene Daten."""
    data = camt_xml([entry("5.00", date=day.isoformat())], closing="5.00")
    st = BankStatement.objects.create(
        organization=org,
        account=account,
        imported_by=user,
        file_name="synthetic.xml",
        date_from=start,
        date_to=end,
        source_sha256=hashlib.sha256(data).hexdigest(),
    )
    st.source.save("synthetic.xml", ContentFile(data))
    BankLine.objects.create(
        organization=org,
        account=account,
        statement=st,
        date=day,
        amount="5.00",
        credit=True,
        name="Synthetic",
        fingerprint=hashlib.sha256(data).hexdigest(),
    )
    return st


@pytest.mark.parametrize("spans", [False, True])
@pytest.mark.parametrize("fiscal_month,fiscal_day", [(1, 1), (4, 15)])
def test_earlier_held_year_protects_original_even_if_header_omits_book_day(
    data, monkeypatch, django_capture_on_commit_callbacks, spans, fiscal_month, fiscal_day
):
    org, account, user = data
    org.fiscal_start_month, org.fiscal_start_day = fiscal_month, fiscal_day
    org.save(update_fields=["fiscal_start_month", "fiscal_start_day"])
    target = 2025 if fiscal_month == 1 else 2024
    start, end = org.fiscal_range(target)
    day = start - datetime.timedelta(days=1)
    statement = legacy(org, account, user, day if spans else start, end, day)
    YearClosing.objects.create(organization=org, year=target - 1, retention_hold="Testhold")
    closing = YearClosing.objects.create(organization=org, year=target)
    monkeypatch.setattr(retention, "_today", lambda: datetime.date(end.year + 9, 1, 1))
    storage, name = statement.source.storage, statement.source.name
    with as_app_role(), tenant_context(org.pk):
        with django_capture_on_commit_callbacks(execute=True):
            with pytest.raises(ValidationError, match="Löschsperre"):
                retention.purge(org, target, user)
        statement.refresh_from_db()
        closing.refresh_from_db()
        assert statement.source.name == name and storage.exists(name)
        assert closing.documents_purged_at is None
        retention.set_hold(org, target - 1, "", user)
        with django_capture_on_commit_callbacks(execute=True):
            retention.purge(org, target, user)
        assert not storage.exists(name)


def test_later_actual_booking_year_delays_original_until_that_year_is_due(
    data, monkeypatch, django_capture_on_commit_callbacks
):
    org, account, user = data
    statement = legacy(
        org,
        account,
        user,
        datetime.date(2025, 3, 1),
        datetime.date(2025, 3, 31),
        datetime.date(2026, 3, 3),
    )
    YearClosing.objects.create(organization=org, year=2025)
    closing = YearClosing.objects.create(organization=org, year=2026)
    storage, name = statement.source.storage, statement.source.name
    monkeypatch.setattr(retention, "_today", lambda: datetime.date(2034, 1, 1))
    with as_app_role(), tenant_context(org.pk):
        with django_capture_on_commit_callbacks(execute=True):
            result = retention.purge(org, 2025, user)
        assert result["counts"]["Kontoauszugsdateien"] == 0
        statement.refresh_from_db()
        assert statement.source.name == name and storage.exists(name)
        assert not retention.state(org, closing)["documents_due"]
        monkeypatch.setattr(retention, "_today", lambda: datetime.date(2035, 1, 1))
        with django_capture_on_commit_callbacks(execute=True):
            retention.purge(org, 2026, user)
        assert not storage.exists(name)


def test_normal_delete_preserves_closed_intermediate_year(data, django_capture_on_commit_callbacks):
    org, account, user = data
    statement = legacy(
        org,
        account,
        user,
        datetime.date(2023, 1, 1),
        datetime.date(2025, 3, 31),
        datetime.date(2023, 3, 3),
    )
    YearClosing.objects.create(organization=org, year=2024, retention_hold="Testhold")
    view = bank_views.BankStatementViewSet()
    view.org, view.request = org, SimpleNamespace(user=user)
    storage, name = statement.source.storage, statement.source.name
    with as_app_role(), tenant_context(org.pk), django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(ApiValidationError, match="abgeschlossenen"):
            view.perform_destroy(statement)
    assert storage.exists(name)
    assert BankStatement.objects.filter(pk=statement.pk).exists()


@pytest.mark.parametrize("day", ["2024-12-30", "2026-03-03"])
def test_new_inconsistent_period_rejected_before_any_original_is_written(data, day):
    org, _, user = data
    with patch("django.db.models.fields.files.FieldFile.save") as save:
        with pytest.raises(ValidationError, match="Zeitraum"):
            bank_import.import_file(org, camt_xml([entry("5.00", date=day)]), "test.xml", user)
        save.assert_not_called()
    assert not BankStatement.objects.filter(organization=org).exists()


def test_direct_iso_period_dates_are_parsed_even_without_closing_balance(data):
    org, _, user = data
    xml = camt_xml([entry("5.00")])
    parsed = camt.parse(xml)[0]
    assert parsed.date_from == datetime.date(2025, 3, 1)
    assert parsed.date_to == datetime.date(2025, 3, 31)
    statement = bank_import.import_file(org, xml, "test.xml", user)["statements"][0]
    assert statement.date_to == parsed.date_to
    assert bank_originals.queryset(org).get(pk=statement.pk).original_last_day == parsed.date_to


def test_reversed_statement_period_is_rejected(data):
    org, _, user = data
    xml = camt_xml([]).replace(b"2025-03-01T00:00:00", b"2025-04-01T00:00:00")
    with pytest.raises(ValidationError, match="Zeitraum"):
        bank_import.import_file(org, xml, "test.xml", user)
