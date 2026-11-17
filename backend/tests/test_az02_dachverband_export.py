"""Mitgliederexport des Dachverbands im Hintergrund (Gesamtaudit 15.11., AZ-02).

Der Auftrag lief in ``tenant_context``; das setzte die Freigabe des Dachverbands auf die
Mitgliedsdaten seiner Vereine zurück. Unter der Rolle der Anwendung (wie im Betrieb) blieb
die Datei leer. Jetzt setzt der Auftrag die Freigabe wie die Ansicht. Erfundene Daten.
"""

# ruff: noqa: F401, F811  (Fixtures aus test_m6_federation_ops)

import pytest

from core.tenancy import federation_access, get_rls, org_context, rls_bypass
from exchange.models import ExportJob
from exchange.tasks import run_export

from .test_m6_federation_ops import _eager, board_fed, members, set_access, types
from .verbund_netz import app_role

pytestmark = pytest.mark.django_db


def _job(orgs, user):
    with rls_bypass():
        return ExportJob.objects.create(
            organization=orgs["federation"],
            created_by=user,
            kind="federation_members",
            file_format="xlsx",
            columns=["club", "last_name"],
            filters={"status": "alle"},
        )


def _run(job):
    with app_role():
        run_export(job.pk)
    with rls_bypass():
        job.refresh_from_db()
    return job


def test_export_im_hintergrund_unter_anwendungsrolle(orgs, members, board_fed):
    set_access(orgs, "read")
    job = _run(_job(orgs, board_fed))
    assert job.status == ExportJob.Status.DONE, job.error
    assert job.row_count == 2  # Adler (Verein A), Berg (Verein B)


def test_ohne_freigabe_keine_vereinsmitglieder(orgs, members, board_fed):
    set_access(orgs, "none")
    job = _run(_job(orgs, board_fed))
    assert job.status == ExportJob.Status.DONE, job.error
    assert job.row_count == 0


def test_freigabe_wie_in_der_anfrage(orgs):
    set_access(orgs, "write")
    with rls_bypass():
        fed = type(orgs["federation"]).objects.get(pk=orgs["federation"].pk)
    assert federation_access(fed) == "write"
    assert federation_access(orgs["a"]) == ""
    before = get_rls()
    with org_context(fed):
        assert get_rls().fed_access == "write"
        assert get_rls().org_id == fed.pk
    assert get_rls() == before
