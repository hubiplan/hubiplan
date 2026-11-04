"""Maschinenstatus und sparsame Dateiinventur für den Betriebsablauf."""

import io

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core import crypto
from core.keyrotation import Rotation
from core.models import DataKey, DataKeyRotation
from core.tenancy import rls_bypass
from exchange.models import ImportJob


@pytest.mark.django_db(transaction=True)
def test_maschinenstatus_ist_lesend_und_erzeugt_keinen_schluessel(orgs):
    def status():
        out = io.StringIO()
        call_command("datenschluessel_wechseln", organisation=orgs["c"].pk, status=True, stdout=out)
        return out.getvalue().strip()

    assert status() == "0 none"
    assert not DataKey.objects.exists() and not DataKeyRotation.objects.exists()
    crypto.key_for_org(orgs["c"].pk)
    call_command(
        "datenschluessel_wechseln",
        organisation=orgs["c"].pk,
        starten=True,
        schreiber_angehalten=True,
        stdout=io.StringIO(),
    )
    rotation = DataKeyRotation.objects.get()
    assert status() == f"{rotation.pk} completed"
    DataKeyRotation.objects.filter(pk=rotation.pk).update(completed_at=None)
    assert status() == f"{rotation.pk} running"


@pytest.mark.django_db
def test_dateiinventur_laesst_grosse_importvorschauen_in_der_datenbank(orgs, settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"
    with rls_bypass():
        job = ImportJob(
            organization=orgs["c"], file_name="test.bin", preview=[{"test": "x" * 1000000}]
        )
        job.file.save("test.bin", ContentFile(b"Testinhalt"), save=False)
        job.save()
        rotation = Rotation(orgs["c"].pk, io.StringIO())
        with CaptureQueriesContext(connection) as queries:
            references = rotation.file_references()
        assert len(references) == 1
        imports = [row["sql"] for row in queries if 'FROM "exchange_importjob"' in row["sql"]]
        assert len(imports) == 2  # Eine Nutzdaten-Seite und die leere Folgeseite.
        assert all('"preview"' not in sql and '"created"' not in sql for sql in imports)
