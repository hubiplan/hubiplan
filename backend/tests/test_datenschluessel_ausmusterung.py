"""Bestandsbericht und Ausmusterung ausschließlich mit erfundenen Daten."""

import datetime
import inspect
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from core import crypto
from core.encfields import encrypt_text_with_key
from core.fieldcompat import require_key_rotation_support
from core.keyinventory import KeyInventory
from core.models import DataKey, DataKeyRotation
from core.tenancy import rls_bypass
from exchange.models import ImportJob, private_storage
from members.models import Person

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def isolated_files(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"


def command(name, **kwargs):
    out = io.StringIO()
    call_command(name, stdout=out, **kwargs)
    return out.getvalue()


def report(org):
    return json.loads(command("datenschluessel_bestand", organisation=org.pk))


def start(org):
    command(
        "datenschluessel_wechseln", organisation=org.pk, starten=True, schreiber_angehalten=True
    )


def retire(org, key, checksum, **kwargs):
    return command(
        "datenschluessel_ausmustern",
        organisation=org.pk,
        schluessel=key,
        pruefsumme=checksum,
        freigabe="TEST-42",
        schreiber_angehalten=True,
        sicherungen_geprueft=True,
        **kwargs,
    )


@pytest.fixture
def rotated(orgs):
    with rls_bypass():
        org = orgs["c"]
        person = Person.objects.create(
            scope=org, first_name="Erika", last_name="Muster", birth_date=datetime.date(1980, 5, 17)
        )
        job = ImportJob(organization=org, file_name="test.bin")
        job.file.save("test.bin", ContentFile(b"Testdatei"), save=False)
        job.save()
        old = crypto.key_for_org(org.pk)
        start(org)
        return org, old, person, job


def test_bericht_ist_lesend_und_gibt_weder_schluessel_noch_nutzdaten_aus(rotated):
    org, old, person, job = rotated
    before = list(DataKey.objects.values())
    rotations = list(DataKeyRotation.objects.values())
    content = Path(job.file.path).read_bytes()
    result = report(org)
    assert result == report(org)
    keys = {key["id"]: key for key in result["keys"]}
    assert result["complete"] and not result["blockers"]
    assert keys[old[0]]["eligible"]
    assert keys[old[0]]["references"] == {"fields": 0, "files": 0, "marks": 0}
    active = keys[crypto.active_key_id(org.pk)]
    assert not active["eligible"] and active["active"]
    assert active["references"]["fields"] >= 3
    assert active["references"]["files"] == 1 and active["references"]["marks"] == 1
    text = json.dumps(result)
    assert "Erika" not in text and "Muster" not in text and "test.bin" not in text
    assert not any(row["wrapped"] in text for row in before)
    assert list(DataKey.objects.values()) == before
    assert list(DataKeyRotation.objects.values()) == rotations
    assert Path(job.file.path).read_bytes() == content


def test_schluesselloser_bericht_legt_nichts_an(orgs):
    result = report(orgs["c"])
    assert not result["keys"] and not result["complete"]
    assert not DataKey.objects.exists() and not DataKeyRotation.objects.exists()


def test_ausmusterung_entfernt_material_erhaelt_historie_und_weitere_wechsel(rotated):
    org, old, person, job = rotated
    proof = report(org)["checksum"]
    assert "nichts entfernt" in retire(org, old[0], proof, probe=True)
    assert DataKey.objects.get(pk=old[0]).wrapped
    old_cipher = crypto.encrypt_bytes(b"Alte Testkopie", *old)
    retire(org, old[0], proof)
    row = DataKey.objects.get(pk=old[0])
    assert row.wrapped == "" and row.retired_at and row.retirement_reference == "TEST-42"
    assert row.retirement_checksum == proof and not row.is_active
    assert "Bereits" in retire(org, old[0], proof)
    with pytest.raises(CommandError, match="kein neuer Vorher"):
        retire(org, old[0], proof, probe=True)
    with pytest.raises(crypto.DecryptionError, match="ausgemustert"):
        crypto.decrypt_bytes(old_cipher)
    with rls_bypass():
        person.refresh_from_db()
        assert person.first_name == "Erika"
        assert job.file.read() == b"Testdatei"
    command("datenschluessel_wechseln", organisation=org.pk, pruefen=True)
    # Auch ein früheres Wechselziel darf nach einem weiteren Wechsel ausgemustert
    # werden, ohne die OneToOne-Historie oder spätere Wiederaufnahmen zu beschädigen.
    second = crypto.active_key_id(org.pk)
    start(org)
    retire(org, second, report(org)["checksum"])
    start(org)
    command("datenschluessel_wechseln", organisation=org.pk, pruefen=True)
    assert DataKeyRotation.objects.filter(organization=org).count() == 3
    command("datenschluessel_umverpacken")
    assert DataKey.objects.get(pk=second).wrapped == ""


@pytest.mark.parametrize(
    "kind",
    [
        "field",
        "file",
        "orphan",
        "marks",
        "foreign_marks",
        "corrupt",
        "missing",
        "symlink",
        "pending",
        "foreign_pending",
    ],
)
def test_verweise_und_unvollstaendige_pruefung_sperren_ausmusterung(rotated, orgs, kind, tmp_path):
    org, old, person, job = rotated
    with rls_bypass():
        if kind == "field":
            field = Person._meta.get_field("last_name")
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE members_person SET last_name=%s WHERE id=%s",
                    [encrypt_text_with_key("Muster", field, *old), person.pk],
                )
        elif kind in {"file", "corrupt"}:
            raw = bytearray(crypto.encrypt_bytes(b"Testdatei", *old))
            if kind == "corrupt":
                raw[-1] ^= 1
            Path(job.file.path).write_bytes(raw)
        elif kind == "orphan":
            path = Path(private_storage().path("alte-kopie.bin"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(crypto.encrypt_bytes(b"Verwaist", *old))
        elif kind in {"marks", "foreign_marks"}:
            if kind == "foreign_marks":
                person = Person.objects.create(
                    scope=orgs["b"],
                    first_name="Else",
                    last_name="Test",
                    birth_date=datetime.date(1980, 5, 17),
                )
            # Den geschützten Fach-Schreibweg absichtlich umgehen, um einen
            # bereits beschädigten Altbestand für die Prüfung zu simulieren.
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE members_person SET marks_key_id=%s WHERE id=%s", [old[0], person.pk]
                )
        elif kind == "missing":
            Path(job.file.path).unlink()
        elif kind == "symlink":
            outside = tmp_path / "ausserhalb.bin"
            outside.write_bytes(b"Test")
            Path(job.file.path).unlink()
            Path(job.file.path).symlink_to(outside)
        elif kind == "pending":
            DataKeyRotation.objects.filter(organization=org).update(completed_at=None)
        else:
            crypto.key_for_org(orgs["b"].pk)
            start(orgs["b"])
            DataKeyRotation.objects.filter(organization=orgs["b"]).update(completed_at=None)
    result = report(org)
    assert not next(key for key in result["keys"] if key["id"] == old[0])["eligible"]
    with pytest.raises(CommandError):
        retire(org, old[0], result["checksum"])
    assert DataKey.objects.get(pk=old[0]).wrapped and not DataKey.objects.get(pk=old[0]).retired_at


def test_aktive_fremde_und_veraltet_freigegebene_schluessel_werden_nicht_entfernt(rotated, orgs):
    org, old, _, _ = rotated
    proof = report(org)["checksum"]
    with pytest.raises(CommandError, match="Aktiver"):
        retire(org, crypto.active_key_id(org.pk), proof)
    with pytest.raises(CommandError, match="nicht zum"):
        retire(org, crypto.key_for_org(orgs["b"].pk)[0], proof)
    DataKey.objects.filter(pk=old[0]).update(rewrapped_at=datetime.datetime.now(datetime.UTC))
    with pytest.raises(CommandError, match="veraltet"):
        retire(org, old[0], proof)
    with pytest.raises(CommandError, match="ausdrücklich"):
        command(
            "datenschluessel_ausmustern",
            organisation=org.pk,
            schluessel=old[0],
            pruefsumme=proof,
            freigabe="TEST-42",
            schreiber_angehalten=True,
        )
    with transaction.atomic(), pytest.raises(CommandError, match="Transaktion"):
        retire(org, old[0], report(org)["checksum"])
    assert DataKey.objects.get(pk=old[0]).wrapped


def test_veraenderung_nach_bestandspruefung_und_db_constraint_schuetzen_material(rotated):
    org, old, _, _ = rotated
    proof = report(org)["checksum"]
    original = KeyInventory.state

    def changed(self, *, lock=False):
        if lock:
            DataKey.objects.filter(pk=old[0]).update(
                rewrapped_at=datetime.datetime.now(datetime.UTC)
            )
        return original(self, lock=lock)

    with (
        patch.object(KeyInventory, "state", changed),
        pytest.raises(CommandError, match="seit der Prüfung"),
    ):
        retire(org, old[0], proof)
    assert DataKey.objects.get(pk=old[0]).wrapped
    with pytest.raises(IntegrityError), transaction.atomic():
        DataKey.objects.filter(pk=old[0]).update(retired_at=datetime.datetime.now(datetime.UTC))


@pytest.mark.migration
def test_ausmusterungsschema_und_rueckweg_erhalten_nachweise(rotated, tmp_path):
    org, old, _, _ = rotated
    retire(org, old[0], report(org)["checksum"])
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        with pytest.raises(DatabaseError, match="Ausmusterungsnachweise"):
            executor.migrate([("core", "0034_datenschluesselwechsel")])
        assert DataKey.objects.get(pk=old[0]).retired_at
    finally:
        MigrationExecutor(connection).migrate(latest)
    target = tmp_path / "backend"
    (target / "core").mkdir(parents=True)
    source = Path(inspect.getfile(DataKey)).read_text()
    (target / "core/models.py").write_text(source)
    require_key_rotation_support(target)
    source = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("retired_at =")
    )
    (target / "core/models.py").write_text(source)
    with pytest.raises(CommandError, match="Zielfassung unterstützt"):
        require_key_rotation_support(target)
