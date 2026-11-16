"""Bereinigungen alles oder nichts und fehlerisoliert (Gesamtaudit 15.11., PF-14, PF-10 Rest).

PF-14: Die Umfrage-Bereinigung vermerkte „bereinigt“, bevor sie die Antworten löschte; brach sie
dazwischen ab, blieben die Antworten unbegrenzt. PF-10: Eine Rechnung, deren Ablage scheiterte,
stand immer vorn, und keine weitere Rechnung wurde je abgelegt. Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime
from unittest import mock

import pytest
from django.core.cache import cache
from django.db.models.query import QuerySet
from django.utils import timezone

from billing import archive
from billing.models import Invoice
from core.tenancy import rls_bypass, tenant_context
from surveys import services
from surveys.models import Survey, SurveyAnswer, SurveyParticipation, SurveyQuestion

from .factories import make_member, make_org
from .test_audit_finanzen import invoice  # noqa: F401
from .test_m9_billing import _private, base, c, club, members, setup, start_run, zug  # noqa: F401

pytestmark = pytest.mark.django_db
OLD = timezone.now() - datetime.timedelta(days=500)


def _survey(org, title):
    member = make_member(org, "Erika", title)
    with tenant_context(org.pk):
        survey = Survey.objects.create(
            organization=org, title=title, status=Survey.Status.CLOSED, closed_at=OLD, keep_months=1
        )
        question = SurveyQuestion.objects.create(
            organization=org, survey=survey, kind="text", text="Warum?"
        )
        part = SurveyParticipation.objects.create(
            organization=org, survey=survey, membership=member, answered_at=OLD
        )
        SurveyAnswer.objects.create(
            organization=org,
            survey=survey,
            question=question,
            participation=part,
            text="persönliche Antwort",
        )
    return survey


def test_umfrage_bereinigung_alles_oder_nichts():
    org = make_org("Umfrageverein")
    broken = _survey(org, "Kaputt")
    fine = _survey(org, "Heil")
    original = QuerySet.delete

    def fails_once(qs):
        if qs.model is SurveyAnswer and qs.filter(survey=broken).exists():
            raise RuntimeError("erfundener Abbruch")
        return original(qs)

    with mock.patch.object(QuerySet, "delete", fails_once):
        assert services.purge_due() == 1  # die andere Umfrage läuft weiter
    with rls_bypass():
        broken.refresh_from_db()
        fine.refresh_from_db()
        # Abgebrochen: nichts vermerkt, nichts halb gelöscht, nächster Lauf holt es nach
        assert broken.purged_at is None
        assert SurveyParticipation.objects.filter(survey=broken).exists()
        assert fine.purged_at is not None
        assert not SurveyAnswer.objects.filter(survey=fine).exists()
    assert services.purge_due() == 1
    with rls_bypass():
        broken.refresh_from_db()
        assert broken.purged_at and not SurveyAnswer.objects.filter(survey=broken).exists()


def test_rechnungsablage_haelt_bei_einem_fehler_nicht_an(invoice):
    cache.clear()
    with rls_bypass():
        Invoice.objects.filter(pk=invoice.pk).update(issued_pdf="")
    with (
        mock.patch.object(archive, "archived_pdf", side_effect=RuntimeError("kaputt")),
        mock.patch("core.alarm.send_alert") as alert,
    ):
        assert archive.archive_missing() == 0
        assert archive.archive_missing() == 0  # ruht einen Tag, keine zweite Mail
    assert alert.call_count == 1
    assert invoice.pk in cache.get(archive.FAILED_KEY)
    # Die übrigen gehen weiter: ohne Pause wird die Rechnung abgelegt
    cache.clear()
    assert archive.archive_missing() >= 1
    with rls_bypass():
        assert Invoice.objects.get(pk=invoice.pk).issued_pdf
