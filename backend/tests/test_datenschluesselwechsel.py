"""Datenschlüsselwechsel mit erfundenen Beständen, Abbrüchen und Fehlerfällen."""

import base64
import datetime
import inspect
import io
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor

from audit.chain import seal, verify
from audit.models import AuditEntry
from changes.models import ChangeRecord, ChangeSet
from core import crypto, keyrotation
from core.encfields import encrypt_text_with_key
from core.fieldcompat import require_key_rotation_support
from core.models import DataKey, DataKeyRotation
from core.tenancy import rls_bypass
from exchange.models import ImportJob, private_storage
from members import personmarks, services
from members.models import ContactDetails, Person
from organizations.models import Organization
from outbox.models import OutgoingMail
from todos.models import Todo

from .factories import make_member, make_org

pytestmark = pytest.mark.django_db(transaction=True)
BIRTH = datetime.date(1980, 5, 17)


@pytest.fixture(autouse=True)
def private_root(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"


def run(org, *args):
    out = io.StringIO()
    call_command("datenschluessel_wechseln", "--organisation", str(org.pk), *args, stdout=out)
    return out.getvalue()


def start(org):
    return run(org, "--starten", "--schreiber-angehalten")


def resume(org):
    return run(org, "--schreiber-angehalten")


def value(obj, field):
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {quote(field)} FROM {quote(obj._meta.db_table)} WHERE id = %s",  # noqa: S608
            [obj.pk],
        )
        return cursor.fetchone()[0]


def field_key(raw):
    if isinstance(raw, dict):
        raw = raw["enc1"]
    if raw.startswith("{"):
        raw = json.loads(raw)["enc1"]
    return int.from_bytes(base64.b64decode(raw[5:])[:8], "big")


def private_file(org, content=b"Testdatei", name="datei.bin"):
    job = ImportJob(organization=org, file_name=name)
    job.file.save(name, ContentFile(content), save=False)
    job.save()
    return job, Path(job.file.path)


def person(org, **extra):
    return Person.objects.create(
        scope=org, last_name="Muster", first_name="Erika", birth_date=BIRTH, **extra
    )


@pytest.fixture
def sample(orgs):
    with rls_bypass():
        a, b = orgs["c"], orgs["b"]
        p = person(a)
        other = person(b)
        todo = Todo.objects.create(organization=a, title="Privater Test", description="Inhalt")
        audit = AuditEntry.objects.create(
            organization=a,
            action="update",
            object_type="Test",
            object_id="1",
            changes={"name": "Erika Muster"},
        )
        change_set = ChangeSet.objects.create(organization=a)
        record = ChangeRecord.objects.create(
            organization=a,
            change_set=change_set,
            seq=1,
            model="members.person",
            object_id=str(p.pk),
            operation="update",
            before={"name": "Vorher"},
            after={"name": "Nachher"},
        )
        job, path = private_file(a, b"Testdatei" * (crypto.CHUNK // 2))
        foreign_job, foreign_path = private_file(b, b"Fremde Testdatei", "fremd.bin")
        with crypto.owner(a.pk):
            attachment = private_storage().save("outbox/anhang.bin", ContentFile(b"Mailanhang"))
            orphan = private_storage().save(
                "verwaist/datei.bin", ContentFile(b"Verwaiste Testdatei")
            )
        mail = OutgoingMail.objects.create(
            organization=a,
            to="test@example.org",
            subject="Test",
            body="Testmail",
            attachments=[{"path": attachment}],
        )
        unit = make_org("Testuntereinheit", "unit", parent=a)
        unit_todo = Todo.objects.create(organization=unit, title="Unteraufgabe")
        return locals()


def test_vorpruefung_ist_lesend_und_vollstaendiger_wechsel_idempotent(sample):
    s = sample
    with rls_bypass():
        before_keys = list(DataKey.objects.values())
        old = crypto.key_for_org(s["a"].pk)
        foreign_key = crypto.key_for_org(s["b"].pk)
        foreign = (value(s["other"], "last_name"), s["foreign_path"].read_bytes())
        times = (
            s["p"].updated_at,
            s["todo"].updated_at,
            s["audit"].timestamp,
            s["path"].stat().st_mtime_ns,
        )
        assert "Vorprüfung erfolgreich" in run(s["a"], "--probe")
        assert list(DataKey.objects.values()) == before_keys
        assert not DataKeyRotation.objects.exists()
        assert "vollständig abgeschlossen" in start(s["a"])
        rotation = DataKeyRotation.objects.get(organization=s["a"])
        assert rotation.completed_at and rotation.phase == "completed"
        assert rotation.source_key_ids == [old[0]]
        assert crypto.key_for_org(s["a"].pk)[0] == rotation.target_key_id != old[0]
        assert crypto.key_by_id(old[0]) == old[1]
        for obj, field in (
            (s["p"], "last_name"),
            (s["todo"], "title"),
            (s["audit"], "changes"),
            (s["record"], "before"),
            (s["record"], "after"),
            (s["mail"], "body"),
            (s["unit_todo"], "title"),
        ):
            assert field_key(value(obj, field)) == rotation.target_key_id
        for path in (
            s["path"],
            Path(private_storage().path(s["attachment"])),
            Path(private_storage().path(s["orphan"])),
        ):
            assert keyrotation.file_key_id(path) == rotation.target_key_id
        assert crypto.decrypt_bytes(s["path"].read_bytes()) == b"Testdatei" * (crypto.CHUNK // 2)
        s["p"].refresh_from_db()
        s["todo"].refresh_from_db()
        s["audit"].refresh_from_db()
        assert (
            s["p"].updated_at,
            s["todo"].updated_at,
            s["audit"].timestamp,
            s["path"].stat().st_mtime_ns,
        ) == times
        assert s["p"].marks_key_id == rotation.target_key_id
        assert (
            personmarks.values(s["p"], create_key=False)["marks_key_id"] == rotation.target_key_id
        )
        assert services.persons_matching(s["a"].pk, "Muster", "Erika", BIRTH, limit=5) == [s["p"]]
        assert (value(s["other"], "last_name"), s["foreign_path"].read_bytes()) == foreign
        assert crypto.key_for_org(s["b"].pk) == foreign_key
        assert AuditEntry.objects.filter(organization=s["a"]).count() == 1
        assert "Abschlussprüfung erfolgreich" in run(s["a"], "--pruefen")
        new_value, new_file = value(s["p"], "last_name"), s["path"].read_bytes()
        assert "Bereits abgeschlossen" in resume(s["a"])
        assert value(s["p"], "last_name") == new_value and s["path"].read_bytes() == new_file
        assert DataKeyRotation.objects.count() == 1
        assert DataKey.objects.filter(organization=s["a"]).count() == 2


@pytest.mark.parametrize("phase", ["database", "files", "marks", "verification"])
def test_abbruch_und_wiederaufnahme_nutzen_dieselbe_zielgeneration(orgs, phase):
    with rls_bypass():
        org = orgs["c"]
        p = person(org)
        _, path = private_file(org)
        method = {
            "database": "scan_database",
            "files": "scan_files",
            "marks": "scan_marks",
            "verification": "verify",
        }[phase]
        original = getattr(keyrotation.Rotation, method)

        def interrupt(self, *args):
            if phase == "verification" or args == ("rewrite",):
                raise RuntimeError("Testabbruch")
            return original(self, *args)

        with patch.object(keyrotation.Rotation, method, interrupt):
            with pytest.raises(RuntimeError, match="Testabbruch"):
                start(org)
        rotation = DataKeyRotation.objects.get(organization=org)
        target = rotation.target_key_id
        assert rotation.completed_at is None
        with pytest.raises(CommandError, match="Wechsel ist offen"):
            start(org)
        assert "vollständig abgeschlossen" in resume(org)
        assert DataKeyRotation.objects.get(pk=rotation.pk).target_key_id == target
        assert DataKey.objects.filter(organization=org).count() == 2
        p.refresh_from_db()
        assert p.first_name == "Erika" and p.marks_key_id == target
        assert crypto.decrypt_bytes(path.read_bytes()) == b"Testdatei"


def test_abbruch_nach_einer_zeile_bleibt_dauerhaft_und_fortsetzbar(orgs):
    with rls_bypass():
        org = orgs["c"]
        p = person(org)
        todo = Todo.objects.create(organization=org, title="Testaufgabe")
        original = keyrotation.FieldCommand._write
        written = []

        def interrupt(*args, **kwargs):
            if written:
                raise RuntimeError("Testabbruch")
            result = original(*args, **kwargs)
            written.append(result)
            return result

        with patch.object(keyrotation.FieldCommand, "_write", interrupt):
            with pytest.raises(RuntimeError):
                start(org)
        assert written == [True]
        target = DataKeyRotation.objects.get(organization=org).target_key_id
        assert target in {field_key(value(p, "last_name")), field_key(value(todo, "title"))}
        resume(org)
        assert field_key(value(p, "last_name")) == field_key(value(todo, "title")) == target


@pytest.mark.parametrize(
    "fault", ["name", "date", "json", "file", "missing", "plain_field", "plain_file", "wrong_owner"]
)
def test_fehler_in_der_vorpruefung_aendern_keinen_schluessel(orgs, fault):
    with rls_bypass():
        org = orgs["c"]
        p = person(org)
        todo = Todo.objects.create(organization=org, title="Test", central_attachment_ids=[1])
        _, path = private_file(org)
        if fault in {"name", "date", "json", "plain_field", "wrong_owner"}:
            if fault == "wrong_owner":
                other = person(orgs["b"])
                table, column, pk, raw = (
                    "members_person",
                    "last_name",
                    p.pk,
                    value(other, "last_name"),
                )
            elif fault == "json":
                table, column, pk, raw = (
                    "todos_todo",
                    "central_attachment_ids",
                    todo.pk,
                    json.dumps({"enc1": "enc1:kaputt"}),
                )
            else:
                table, column, pk = (
                    "members_person",
                    "birth_date" if fault == "date" else "last_name",
                    p.pk,
                )
                raw = "Klartext" if fault == "plain_field" else "enc1:kaputt"
            with connection.cursor() as cursor:
                cursor.execute(f'UPDATE "{table}" SET "{column}" = %s WHERE id = %s', [raw, pk])  # noqa: S608
        elif fault == "missing":
            path.unlink()
        elif fault == "plain_file":
            path.write_bytes(b"Alte Klartextdatei")
        else:
            data = bytearray(path.read_bytes())
            data[-1] ^= 1
            path.write_bytes(data)
        before = list(DataKey.objects.values())
        with pytest.raises(CommandError):
            start(org)
        assert list(DataKey.objects.values()) == before
        assert not DataKeyRotation.objects.exists()


def test_geaenderte_zeile_wird_nicht_mit_altem_stand_ueberschrieben(orgs):
    with rls_bypass():
        org = orgs["c"]
        todo = Todo.objects.create(organization=org, title="Alt")
        original = keyrotation.FieldCommand._write

        def concurrent(*args, **kwargs):
            todo.title = "Neuer Stand"
            todo.save(update_fields=["title"])
            return original(*args, **kwargs)

        with patch.object(keyrotation.FieldCommand, "_write", concurrent):
            with pytest.raises(CommandError, match="Datensatz während"):
                start(org)
        todo.refresh_from_db()
        assert todo.title == "Neuer Stand"
        assert DataKeyRotation.objects.get().completed_at is None
        resume(org)
        todo.refresh_from_db()
        assert todo.title == "Neuer Stand"


def test_datei_wird_vor_atomarem_austausch_vollstaendig_geprueft(orgs):
    with rls_bypass():
        org = orgs["c"]
        _, path = private_file(org)
        before = path.read_bytes()
        replace = keyrotation.os.replace

        def inspect(source, destination):
            assert path.read_bytes() == before
            assert crypto.decrypt_bytes(Path(source).read_bytes()) == b"Testdatei"
            assert (
                keyrotation.file_key_id(Path(source)) == DataKeyRotation.objects.get().target_key_id
            )
            return replace(source, destination)

        with patch("core.keyrotation.os.replace", inspect):
            start(org)


def test_hart_abgebrochene_dateiumstellung_laesst_sich_fortsetzen(orgs):
    with rls_bypass():
        org = orgs["c"]
        _, path = private_file(org)
        before = path.read_bytes()
        with patch.object(
            keyrotation.Rotation, "rewrite_file", side_effect=RuntimeError("Testabbruch")
        ):
            with pytest.raises(RuntimeError):
                start(org)
        rotation = DataKeyRotation.objects.get()
        stage = path.parents[2] / f".datenschluesselwechsel-{rotation.token.hex}"
        stage.mkdir()
        (stage / f"{uuid.uuid4().hex}.part").write_bytes(b"HUBENC1\nTeil eines Chiffrats")
        assert path.read_bytes() == before
        resume(org)
        assert not stage.exists()
        assert crypto.decrypt_bytes(path.read_bytes()) == b"Testdatei"


def test_abschlusspruefung_authentifiziert_auch_zielchiffrate(orgs):
    with rls_bypass():
        org = orgs["c"]
        _, path = private_file(org)
        start(org)
        data = bytearray(path.read_bytes())
        data[-1] ^= 1
        path.write_bytes(data)
        with pytest.raises(CommandError, match="nicht vollständig lesbar"):
            run(org, "--pruefen")
        with pytest.raises(CommandError):
            resume(org)
        assert DataKey.objects.filter(organization=org).count() == 2


def test_markenpruefung_schreibt_nichts(orgs):
    with rls_bypass():
        org = orgs["c"]
        p = person(org)
        start(org)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE members_person SET last_birth_mark = %s WHERE id = %s", ["X" * 22, p.pk]
            )
        with pytest.raises(CommandError, match="Personensuchmarken"):
            run(org, "--pruefen")
        p.refresh_from_db()
        assert p.last_birth_mark == "X" * 22


def test_keine_automatische_neuanlage_bei_falscher_bedienung(orgs):
    org = orgs["c"]
    with pytest.raises(CommandError, match="Schreibdienste"):
        run(org, "--starten")
    with pytest.raises(CommandError, match="Kein Wechsel"):
        resume(org)
    with pytest.raises(CommandError, match="Genau ein aktiver"):
        run(org, "--probe")
    unit = make_org("Untergliederung", "unit", parent=org)
    with pytest.raises(CommandError, match="Schlüsselinhaber"):
        start(unit)
    with transaction.atomic():
        with pytest.raises(CommandError, match="übergeordneten Transaktion"):
            start(org)
    assert not DataKeyRotation.objects.exists() and not DataKey.objects.exists()


def test_plattform_schuetzt_mails_ohne_organisation(orgs):
    with rls_bypass():
        platform = Organization.platform()
        mail = OutgoingMail.objects.create(
            to="test@example.org", subject="Test", body="Ohne Verein"
        )
        before = value(mail, "body")
        start(platform)
        rotation = DataKeyRotation.objects.get(organization=platform)
        assert field_key(value(mail, "body")) == rotation.target_key_id != field_key(before)
        mail.refresh_from_db()
        assert mail.body == "Ohne Verein"


def test_sperre_verhindert_parallele_wechsel_und_wird_freigegeben(orgs):
    crypto.key_for_org(orgs["c"].pk)

    def other():
        try:
            return run(orgs["c"], "--probe")
        finally:
            connections.close_all()

    with keyrotation.rotation_lock():
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(CommandError, match="anderer Datenschlüsselwechsel"):
                pool.submit(other).result(timeout=10)
    assert "Vorprüfung erfolgreich" in other()


def test_schluesselwechsel_erlaubt_spaetere_generation_ohne_alte_zu_loeschen(orgs):
    with rls_bypass():
        org = orgs["c"]
        p = person(org)
        first = crypto.key_for_org(org.pk)
        start(org)
        second = crypto.key_for_org(org.pk)
        start(org)
        third = crypto.key_for_org(org.pk)
        assert len({first[0], second[0], third[0]}) == 3
        assert crypto.key_by_id(first[0]) == first[1]
        assert field_key(value(p, "last_name")) == third[0]
        assert DataKeyRotation.objects.filter(organization=org).count() == 2
        # Die bestehende Fachregel schützt Organisationen mit Personenbestand.
        p.delete()
        org.delete()
        assert not DataKey.objects.filter(pk__in=[first[0], second[0], third[0]]).exists()


def test_migration_schuetzt_auftraege_vor_verlust_beim_rueckweg(orgs):
    org = orgs["c"]
    crypto.key_for_org(org.pk)
    start(org)
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        with pytest.raises(DatabaseError, match="Aufträge"):
            executor.migrate([("core", "0033_datenschluessel_generationen")])
        assert DataKeyRotation.objects.get(organization=org).completed_at
    finally:
        MigrationExecutor(connection).migrate(latest)


def test_protokollkette_bleibt_unveraendert_pruefbar(orgs):
    with rls_bypass():
        org = orgs["c"]
        entry = AuditEntry.objects.create(
            organization=org,
            action="update",
            object_type="Test",
            object_id="1",
            changes={"Name": ["Vorher", "Nachher"]},
        )
        seal(org.pk)
        entry.refresh_from_db()
        hashes = (entry.seq, entry.hash, entry.prev_hash, entry.changes_hash)
        assert verify(org.pk)["ok"]
        start(org)
        entry.refresh_from_db()
        assert (entry.seq, entry.hash, entry.prev_hash, entry.changes_hash) == hashes
        assert verify(org.pk)["ok"]


def test_alte_zielfassung_wird_vor_daten_rueckweg_abgewiesen(orgs, tmp_path):
    org = orgs["c"]
    crypto.key_for_org(org.pk)
    start(org)
    target = tmp_path / "backend"
    (target / "core").mkdir(parents=True)
    source = Path(inspect.getfile(DataKey)).read_text()
    (target / "core/models.py").write_text('raise RuntimeError("Nie ausführen")\n' + source)
    require_key_rotation_support(target)
    # Auch die vorige generationsfähige Fassung kennt Wechselaufträge noch nicht.
    (target / "core/models.py").write_text(source.split("class DataKeyRotation")[0])
    with pytest.raises(CommandError, match="Zielfassung unterstützt"):
        call_command("daten_verschluesseln", "--rueckweg-zu", str(target), stdout=io.StringIO())


@pytest.mark.parametrize("kind", ["symbolischer_link", "pfad_ausserhalb"])
def test_unsichere_dateipfade_verhindern_aktivierung(orgs, tmp_path, kind):
    with rls_bypass():
        org = orgs["c"]
        job, path = private_file(org)
        outside = tmp_path / "ausserhalb.bin"
        outside.write_bytes(b"Unveraenderte Testdatei")
        if kind == "symbolischer_link":
            path.unlink()
            path.symlink_to(outside)
        else:
            ImportJob.objects.filter(pk=job.pk).update(file="../ausserhalb.bin")
        with pytest.raises(CommandError):
            start(org)
        assert not DataKeyRotation.objects.exists()
        assert outside.read_bytes() == b"Unveraenderte Testdatei"


def test_fremder_datensatz_mit_eigenem_schluesselverweis_stoppt_start(orgs):
    with rls_bypass():
        own = person(orgs["c"])
        foreign = person(orgs["b"])
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE members_person SET last_name = %s WHERE id = %s",
                [value(own, "last_name"), foreign.pk],
            )
        with pytest.raises(CommandError, match="fremden Datenbereich"):
            start(orgs["c"])
        assert not DataKeyRotation.objects.exists()


def test_beschaedigter_zwischenspeicher_wird_nicht_als_fertige_datei_ersetzt(orgs):
    with rls_bypass():
        org = orgs["c"]
        _, path = private_file(org)
        before = path.read_bytes()
        original = crypto.encrypt_chunks

        def corrupted(*args):
            for i, chunk in enumerate(original(*args)):
                if i:
                    chunk = chunk[:-1] + bytes([chunk[-1] ^ 1])
                yield chunk

        with patch("core.keyrotation.crypto.encrypt_chunks", corrupted):
            with pytest.raises(CommandError, match="nicht vollständig lesbar"):
                start(org)
        assert path.read_bytes() == before
        assert DataKeyRotation.objects.get().completed_at is None
        resume(org)
        assert crypto.decrypt_bytes(path.read_bytes()) == b"Testdatei"


def test_geaenderte_datei_wird_nicht_mit_einem_alten_stand_ersetzt(orgs):
    with rls_bypass():
        org = orgs["c"]
        _, path = private_file(org)
        newer = crypto.encrypt_bytes(b"Neuer Dateistand", *crypto.key_for_org(org.pk))
        original = crypto.encrypt_chunks

        def concurrent(*args):
            yield from original(*args)
            path.write_bytes(newer)

        with patch("core.keyrotation.crypto.encrypt_chunks", concurrent):
            with pytest.raises(CommandError, match="Datei während"):
                start(org)
        assert path.read_bytes() == newer
        resume(org)
        assert crypto.decrypt_bytes(path.read_bytes()) == b"Neuer Dateistand"


def test_vereinswechsel_laesst_gemeinsame_verbandsidentitaet_unveraendert(orgs):
    member = make_member(orgs["a"], "Erika", "Muster")
    with rls_bypass():
        p = member.person
        contact = ContactDetails.objects.get(person=p)
        todo = Todo.objects.create(organization=orgs["a"], title="Vereinsaufgabe")
        identity = (
            value(p, "last_name"),
            value(p, "birth_date"),
            value(contact, "email"),
            p.marks_key_id,
        )
        start(orgs["a"])
        p.refresh_from_db()
        assert (
            value(p, "last_name"),
            value(p, "birth_date"),
            value(contact, "email"),
            p.marks_key_id,
        ) == identity
        club_copy = value(todo, "title")
        start(orgs["federation"])
        p.refresh_from_db()
        assert p.first_name == "Erika" and p.marks_key_id != identity[3]
        assert field_key(value(contact, "email")) == p.marks_key_id
        assert value(todo, "title") == club_copy


def test_abschlusspruefung_findet_altes_restchiffrat_auch_nach_erfolgreichem_auftrag(orgs):
    with rls_bypass():
        org = orgs["c"]
        todo = Todo.objects.create(organization=org, title="Testaufgabe")
        old = value(todo, "title")
        start(org)
        completed = DataKeyRotation.objects.get().completed_at
        with connection.cursor() as cursor:
            cursor.execute("UPDATE todos_todo SET title = %s WHERE id = %s", [old, todo.pk])
        with pytest.raises(CommandError, match="alte Schlüsselgeneration"):
            run(org, "--pruefen")
        assert DataKeyRotation.objects.get().completed_at == completed


@pytest.mark.parametrize(
    "field_name,text", [("birth_date", "kein Datum"), ("central_attachment_ids", "kein JSON")]
)
def test_authentifiziertes_aber_ungueltiges_datum_oder_json_stoppt_vor_aktivierung(
    orgs, field_name, text
):
    with rls_bypass():
        org = orgs["c"]
        obj = (
            person(org)
            if field_name == "birth_date"
            else Todo.objects.create(organization=org, title="Test")
        )
        field = obj._meta.get_field(field_name)
        cipher = encrypt_text_with_key(text, field, *crypto.key_for_org(org.pk))
        stored = cipher if field_name == "birth_date" else json.dumps({"enc1": cipher})
        quote = connection.ops.quote_name
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {quote(obj._meta.db_table)} SET {quote(field_name)} = %s WHERE id = %s",  # noqa: S608
                [stored, obj.pk],
            )
        with pytest.raises(CommandError, match="Feldbestand"):
            start(org)
        assert not DataKeyRotation.objects.exists()


def test_geteilter_dokumentanhang_behaelt_den_schluessel_des_dokumentinhabers(orgs):
    with rls_bypass():
        org = orgs["c"]
        document, path = private_file(orgs["b"])
        before = path.read_bytes()
        OutgoingMail.objects.create(
            organization=org,
            to="test@example.org",
            subject="Test",
            body="Anhang",
            attachments=[{"path": document.file.name}],
        )
        start(org)
        assert path.read_bytes() == before
        assert keyrotation.file_key_id(path) == crypto.key_for_org(orgs["b"].pk)[0]


def test_vorpruefung_prueft_verpackung_auch_bei_gefuelltem_lesecache(orgs):
    org = orgs["c"]
    key_id, _ = crypto.key_for_org(org.pk)
    DataKey.objects.filter(pk=key_id).update(wrapped="unlesbar")
    with pytest.raises(CommandError, match="nicht entpacken"):
        start(org)
    assert not DataKeyRotation.objects.exists()


@pytest.mark.parametrize("completed", [False, True])
def test_leere_dateien_werden_vor_und_nach_dem_wechsel_authentifiziert(orgs, completed):
    with rls_bypass():
        org = orgs["c"]
        _, path = private_file(org, b"")
        if completed:
            start(org)
        damaged = bytearray(path.read_bytes())
        damaged[-1] ^= 1
        path.write_bytes(damaged)
        before_keys = list(DataKey.objects.values())
        with pytest.raises(CommandError, match="nicht vollständig lesbar"):
            run(org, "--pruefen") if completed else start(org)
        assert list(DataKey.objects.values()) == before_keys
        assert DataKeyRotation.objects.exists() == completed
        with pytest.raises(crypto.DecryptionError):
            crypto.decrypt_bytes(path.read_bytes())
