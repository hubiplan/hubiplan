"""Verschlüsselte Identität: Bestand, strenge Lesbarkeit und gezielter Rückweg."""

import base64
import inspect
import io
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.exceptions import FieldError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor

from core.crypto import DecryptionError, key_for_org
from core.management.commands.daten_verschluesseln import Command, encrypted_fields
from core.tenancy import rls_bypass
from members import services
from members.models import Person

from .factories import make_member

FIELDS = ("members.Person.last_name", "members.Person.first_name")


def run(*args):
    call_command("daten_verschluesseln", *args, stdout=io.StringIO())


def names_only(*args):
    run(*args, "--feld", FIELDS[0], "--feld", FIELDS[1])


def raw(pk):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT last_name, first_name, birth_date FROM members_person WHERE id = %s", [pk]
        )
        return cursor.fetchone()


def target_backend(tmp_path):
    """Zielfassung mit allen bisherigen Verschlüsselungsfeldern, nur Namen noch offen."""
    target = tmp_path / "backend"
    target.mkdir()
    (target / "manage.py").write_text("# Nur Quelltext zur Deklarationsprüfung.\n")
    for model, _ in encrypted_fields():
        source = Path(inspect.getfile(model))
        dest = target / source.relative_to(settings.BASE_DIR)
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = source.read_text()
        if source == Path(inspect.getfile(Person)):
            text = text.replace(
                'EncryptedCharField("Name", max_length=100, strict=True)',
                'models.CharField("Name", max_length=100)',
            )
            text = text.replace(
                'EncryptedCharField("Vorname", max_length=100, strict=True)',
                'models.CharField("Vorname", max_length=100)',
            )
        dest.write_text(text)
    return target


@pytest.mark.django_db
class TestNames:
    def test_chiffrate_schluessel_und_klartextlaenge(self, orgs):
        m = make_member(orgs["a"], "É" * 100, "Ö" * 100)
        with rls_bypass():
            stored = raw(m.person_id)
            key_id, _ = key_for_org(orgs["federation"].pk)
            assert all(value.startswith("enc1:") for value in stored)
            assert all(
                int.from_bytes(base64.b64decode(value[5:])[:8], "big") == key_id for value in stored
            )
            p = Person.objects.get(pk=m.person_id)
            assert p.first_name == "É" * 100 and p.last_name == "Ö" * 100
            p.scope = orgs["c"]
            p.save(update_fields=["scope"])
            new_key, _ = key_for_org(orgs["c"].pk)
            assert all(
                int.from_bytes(base64.b64decode(value[5:])[:8], "big") == new_key
                for value in raw(p.pk)
            )
            names_only("--pruefen")

    @pytest.mark.parametrize("field", ["last_name", "first_name"])
    def test_sql_namensvergleiche_und_sortierung_gesperrt(self, orgs, field):
        m = make_member(orgs["c"], "Erika", "Muster")
        with rls_bypass():
            with pytest.raises(FieldError):
                list(Person.objects.filter(**{field: "Muster"}))
            with pytest.raises(FieldError):
                list(Person.objects.filter(**{f"{field}__icontains": "mus"}))
            with pytest.raises(FieldError):
                list(Person.objects.order_by(field))
            assert list(Person.objects.values_list("pk", flat=True)) == [m.person_id]

    def test_bestand_gezielt_verschluesseln_und_erneut_markieren(self, orgs):
        m = make_member(orgs["c"], "Erika", "Muster")
        with rls_bypass():
            birth = raw(m.person_id)[2]
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE members_person SET last_name = 'Muster', first_name = 'Erika' "
                    "WHERE id = %s",
                    [m.person_id],
                )
            with pytest.raises(CommandError):
                names_only("--pruefen")
            assert Person.objects.get(pk=m.person_id).last_name == "Muster"
            names_only()
            assert raw(m.person_id)[2] == birth
            assert Person.objects.get(pk=m.person_id).marks_version == 0
            call_command("personen_suchmarken", stdout=io.StringIO())
            call_command("personen_suchmarken", "--pruefen", stdout=io.StringIO())
            names_only("--pruefen")
            before = raw(m.person_id)
            names_only()
            assert raw(m.person_id) == before
            assert services.persons_matching(
                orgs["c"].pk, "Muster", "Erika", m.person.birth_date, limit=2
            )

    def test_rueckweg_oeffnet_nur_neue_namensfelder(self, orgs, tmp_path):
        m = make_member(orgs["c"], "Erika", "Muster", email="erika@example.org")
        with rls_bypass():
            before = raw(m.person_id)
            target = target_backend(tmp_path)
            run("--rueckweg-zu", str(target))
            assert raw(m.person_id) == ("Muster", "Erika", before[2])
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT email, phone, street FROM members_contactdetails WHERE person_id = %s",
                    [m.person_id],
                )
                email, _, street = cursor.fetchone()
                assert email.startswith("enc1:") and street.startswith("enc1:")
            # Die ältere Fassung findet unmarkierte Personen weiterhin korrekt.
            assert services.persons_matching(
                orgs["c"].pk, "Muster", "Erika", m.person.birth_date, limit=2
            )
            names_only()
            names_only("--pruefen")

    def test_unbekannter_zieltyp_bricht_vor_jeder_aenderung_ab(self, orgs, tmp_path):
        m = make_member(orgs["c"], "Erika", "Muster")
        with rls_bypass():
            target = target_backend(tmp_path)
            file = target / "members/models.py"
            file.write_text(
                file.read_text().replace(
                    'models.CharField("Vorname", max_length=100)', "UnbekanntesFeld()"
                )
            )
            before = raw(m.person_id)
            with pytest.raises(CommandError, match="Unbekanntes Zielfeld"):
                run("--rueckweg-zu", str(target))
            assert raw(m.person_id) == before

    def test_zielcode_wird_nicht_ausgefuehrt(self, orgs, tmp_path):
        m = make_member(orgs["c"], "Erika", "Muster")
        with rls_bypass():
            target = target_backend(tmp_path)
            file = target / "members/models.py"
            file.write_text('raise RuntimeError("Nicht ausführen")\n' + file.read_text())
            names_only("--rueckweg-zu", str(target))
            assert raw(m.person_id)[0] == "Muster"

    def test_beschaedigter_name_bleibt_fehler_statt_leerwert(self, orgs):
        m = make_member(orgs["c"], "Erika", "Muster")
        with rls_bypass():
            original = raw(m.person_id)[0]
            blob = bytearray(base64.b64decode(original[5:]))
            blob[-1] ^= 1
            broken = "enc1:" + base64.b64encode(blob).decode()
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE members_person SET last_name = %s WHERE id = %s", [broken, m.person_id]
                )
            with pytest.raises(DecryptionError):
                Person.objects.get(pk=m.person_id)
            with pytest.raises(CommandError):
                names_only("--pruefen")
            with pytest.raises(CommandError):
                call_command("personen_suchmarken", "--pruefen", stdout=io.StringIO())

    def test_unbekanntes_feld_ist_kein_erfolgreicher_leerlauf(self):
        with pytest.raises(CommandError, match="Unbekannte verschlüsselte Felder"):
            run("--feld", "members.Person.last_nam")

    def test_backfill_ueberschreibt_keine_zwischenzeitliche_aenderung(self, orgs):
        m = make_member(orgs["c"], "Erika", "Alt")
        with rls_bypass():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE members_person SET last_name = 'Alt' WHERE id = %s", [m.person_id]
                )
            original = Command._write

            def race(table, pk_col, pk, updates, **kwargs):
                p = Person.objects.get(pk=pk)
                p.last_name = "Neu"
                p.save(update_fields=["last_name"])
                original(table, pk_col, pk, updates, **kwargs)

            with patch.object(Command, "_write", staticmethod(race)):
                names_only()
            assert Person.objects.get(pk=m.person_id).last_name == "Neu"
            names_only("--pruefen")


@pytest.mark.langsam
@pytest.mark.django_db(transaction=True)
def test_migration_schuetzt_chiffrate_beim_rueckweg(orgs):
    with rls_bypass():
        m = make_member(orgs["c"], "É" * 100, "Ö" * 100)
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [("members", "0023_personen_suchmarken")]
        before = raw(m.person_id)
        try:
            with pytest.raises(DatabaseError, match="Personennamen entschlüsseln"):
                executor.migrate(previous)
            assert raw(m.person_id) == before
            names_only("--entschluesseln")
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE members_person SET last_name = %s WHERE id = %s",
                    ["Ö" * 101, m.person_id],
                )
            with pytest.raises(DatabaseError, match="Längen prüfen"):
                MigrationExecutor(connection).migrate(previous)
            assert len(raw(m.person_id)[0]) == 101
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE members_person SET last_name = %s WHERE id = %s",
                    ["Ö" * 100, m.person_id],
                )
            executor = MigrationExecutor(connection)
            executor.migrate(previous)
            old = executor.loader.project_state(previous).apps.get_model("members", "Person")
            p = old.objects.get(pk=m.person_id)
            assert p.last_name == "Ö" * 100 and p.first_name == "É" * 100
            assert raw(m.person_id)[2] == before[2]
        finally:
            MigrationExecutor(connection).migrate(latest)
        names_only()
        names_only("--pruefen")
        call_command("personen_suchmarken", stdout=io.StringIO())
        call_command("personen_suchmarken", "--pruefen", stdout=io.StringIO())
