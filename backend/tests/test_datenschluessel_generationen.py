"""Aktive Schreibgeneration und alte Leseschlüssel bleiben sauber getrennt."""

import base64
import datetime
import io
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test.utils import CaptureQueriesContext

from core import crypto
from core.models import DataKey
from core.tenancy import rls_bypass
from members import personmarks, services
from members.models import Person

from .factories import make_org

BIRTH = datetime.date(1980, 5, 17)


def next_generation(org):
    """Nur Testaufbau; ein Betriebsbefehl zum Umschalten ist noch nicht vorgesehen."""
    raw = os.urandom(32)
    with transaction.atomic():
        DataKey.objects.filter(organization=org, is_active=True).update(is_active=False)
        row = DataKey.objects.create(
            organization=org, wrapped=crypto.wrap_key(raw, crypto._context(org.pk))
        )
    return row.pk, raw


def stored_names(pk):
    with connection.cursor() as cursor:
        cursor.execute("SELECT last_name, first_name FROM members_person WHERE id = %s", [pk])
        return cursor.fetchone()


def field_key_id(value):
    return int.from_bytes(base64.b64decode(value[5:])[:8], "big")


@pytest.mark.django_db
class TestGenerations:
    def test_ein_aktiver_schluessel_mehrere_alte_generationen(self, orgs):
        first = crypto.key_for_org(orgs["a"].pk)
        second = next_generation(orgs["a"])
        third = next_generation(orgs["a"])
        for key_id, raw in (third, first, second, first):
            assert crypto.key_by_id(key_id) == raw
            assert crypto.key_for_org(orgs["a"].pk) == third
        assert DataKey.objects.filter(organization=orgs["a"]).count() == 3
        with pytest.raises(IntegrityError), transaction.atomic():
            DataKey.objects.create(organization=orgs["a"], wrapped="nicht verwendet")

    def test_bereiche_und_untereinheiten_bleiben_getrennt(self, orgs):
        unit = make_org("Testzug", "unit", parent=orgs["a"])
        old = crypto.key_for_org(unit.pk)
        other = crypto.key_for_org(orgs["b"].pk)
        new = next_generation(orgs["a"])
        assert crypto.key_for_org(unit.pk) == new
        assert crypto.key_for_org(orgs["b"].pk) == other
        assert crypto.key_by_id(old[0]) == old[1]
        assert not DataKey.objects.filter(organization=unit).exists()
        row = DataKey.objects.get(pk=old[0])
        with pytest.raises(crypto.DecryptionError):
            crypto.unwrap_key(row.wrapped, crypto._context(orgs["b"].pk))

    def test_fehlende_aktive_generation_erzeugt_keinen_ersatz(self, orgs):
        old = crypto.key_for_org(orgs["c"].pk)
        DataKey.objects.filter(pk=old[0]).update(is_active=False)
        assert crypto.active_key_id(orgs["c"].pk) is None
        with pytest.raises(ImproperlyConfigured, match="aktive Datenschlüssel"):
            crypto.key_for_org(orgs["c"].pk)
        assert DataKey.objects.filter(organization=orgs["c"]).count() == 1
        assert crypto.key_by_id(old[0]) == old[1]

    def test_lesende_auswahl_legt_keinen_schluessel_an(self, orgs):
        assert crypto.active_key_id(orgs["c"].pk) is None
        assert not DataKey.objects.filter(organization=orgs["c"]).exists()

    def test_parallele_anlage_zwischen_lesenden_abfragen(self, orgs):
        # Ein anderer Prozess ist nach der ersten aktiven Auswahl schon fertig.
        original = crypto.active_key_id
        calls = 0

        def select(owner_id):
            nonlocal calls
            calls += 1
            if calls == 1:
                crypto.key_for_owner(owner_id)
                return None
            return original(owner_id)

        with patch("core.crypto.active_key_id", select):
            selected = crypto.key_for_org(orgs["c"].pk)
        assert selected[0] == DataKey.objects.get(organization=orgs["c"]).pk

    def test_rollback_der_anlage_hinterlaesst_keinen_lesbaren_schluessel(self, orgs):
        with pytest.raises(RuntimeError, match="Testabbruch"), transaction.atomic():
            key_id, raw = crypto.key_for_org(orgs["c"].pk)
            assert crypto.key_by_id(key_id) == raw
            raise RuntimeError("Testabbruch")
        assert not DataKey.objects.filter(pk=key_id).exists()
        with pytest.raises(crypto.DecryptionError):
            crypto.key_by_id(key_id)
        assert crypto.key_for_org(orgs["c"].pk)[0] != key_id

    def test_rollback_eines_wechsels_veraendert_keinen_schreibcache(self, orgs):
        old = crypto.key_for_org(orgs["c"].pk)
        with pytest.raises(RuntimeError), transaction.atomic():
            new = next_generation(orgs["c"])
            assert crypto.key_for_org(orgs["c"].pk) == new
            raise RuntimeError("Testabbruch")
        assert crypto.key_for_org(orgs["c"].pk) == old
        with pytest.raises(crypto.DecryptionError):
            crypto.key_by_id(new[0])

    def test_lesecache_beachtet_weiterhin_ablaufzeit(self, orgs, settings):
        settings.DATA_KEY_CACHE_SECONDS = 5
        key_id, raw = crypto.key_for_org(orgs["c"].pk)
        crypto._keys_by_id[key_id] = (raw, 10)
        with patch("core.crypto.time.monotonic", return_value=14):
            with patch("core.crypto._load") as load:
                assert crypto.key_by_id(key_id) == raw
                load.assert_not_called()
        with patch("core.crypto.time.monotonic", return_value=16):
            with patch("core.crypto._load", return_value=raw) as load:
                assert crypto.key_by_id(key_id) == raw
                load.assert_called_once_with(key_id)

    def test_transaktionscache_vermeidet_zusaetzliche_abfragen_beim_lesen(self, orgs):
        with rls_bypass():
            p = Person.objects.create(
                scope=orgs["c"], last_name="Muster", first_name="Erika", birth_date=BIRTH
            )
            with CaptureQueriesContext(connection) as queries:
                loaded = Person.objects.get(pk=p.pk)
            assert loaded.last_name == "Muster" and loaded.birth_date == BIRTH
            assert len(queries) == 1
            # Auch nach dem Leeren höchstens einmal je unterschiedlichem Schlüssel
            # entpacken, nicht für jedes Feld und jede gelesene Person erneut.
            crypto.reset()
            with CaptureQueriesContext(connection) as queries:
                list(Person.objects.filter(pk=p.pk))
                list(Person.objects.filter(pk=p.pk))
            assert len(queries) == 3

    def test_alte_namen_dateien_und_marken_bleiben_lesbar(self, orgs):
        with rls_bypass():
            p = Person.objects.create(
                scope=orgs["c"], last_name="Muster", first_name="Erika", birth_date=BIRTH
            )
            old = crypto.key_for_org(orgs["c"].pk)
            before = stored_names(p.pk)
            old_file = crypto.encrypt_bytes(b"Alte Testdatei", *old)
            new = next_generation(orgs["c"])
            # Auch nach vollständigem Neustart müssen die alten Nummern lesbar sein.
            crypto.reset()
            assert Person.objects.get(pk=p.pk).last_name == "Muster"
            assert crypto.decrypt_bytes(old_file) == b"Alte Testdatei"
            assert stored_names(p.pk) == before
            assert crypto.key_for_org(orgs["c"].pk) == new
            assert services.persons_matching(orgs["c"].pk, "Muster", "Erika", BIRTH, limit=5) == [p]
            with pytest.raises(CommandError):
                call_command("personen_suchmarken", "--pruefen", stdout=io.StringIO())
            call_command("personen_suchmarken", stdout=io.StringIO())
            call_command("personen_suchmarken", "--pruefen", stdout=io.StringIO())
            p.refresh_from_db()
            assert p.marks_key_id == new[0]
            assert personmarks.values(p, create_key=False)["marks_key_id"] == new[0]
            assert stored_names(p.pk) == before
            fresh = Person.objects.create(
                scope=orgs["c"], last_name="Neu", first_name="Else", birth_date=BIRTH
            )
            assert all(field_key_id(value) == new[0] for value in stored_names(fresh.pk))
            new_file = crypto.encrypt_bytes(b"Neue Testdatei", *crypto.key_for_org(orgs["c"].pk))
            assert crypto.decrypt_bytes(new_file) == b"Neue Testdatei"
            assert all(field_key_id(value) == old[0] for value in before)

    def test_markenpruefung_ohne_aktive_generation_bleibt_lesend(self, orgs):
        with rls_bypass():
            p = Person.objects.create(
                scope=orgs["c"], last_name="Muster", first_name="Erika", birth_date=BIRTH
            )
            DataKey.objects.filter(organization=orgs["c"]).update(is_active=False)
            with pytest.raises(ValueError, match="Datenschlüssel fehlt"):
                personmarks.values(p, create_key=False)
            assert DataKey.objects.filter(organization=orgs["c"]).count() == 1

    def test_umverpacken_erfasst_aktive_und_alte_generationen(self, orgs, settings):
        first = crypto.key_for_org(orgs["c"].pk)
        second = next_generation(orgs["c"])
        files = [crypto.encrypt_bytes(b"Testinhalt", *key) for key in (first, second)]
        master = crypto._b64(os.urandom(32))
        settings.DATA_ENCRYPTION_KEYS = [master, *settings.DATA_ENCRYPTION_KEYS]
        crypto.reset()
        call_command("datenschluessel_umverpacken", stdout=io.StringIO())
        settings.DATA_ENCRYPTION_KEYS = [master]
        crypto.reset()
        assert all(crypto.decrypt_bytes(value) == b"Testinhalt" for value in files)
        assert crypto.key_for_org(orgs["c"].pk) == second
        assert list(
            DataKey.objects.filter(organization=orgs["c"])
            .order_by("pk")
            .values_list("is_active", flat=True)
        ) == [False, True]


@pytest.mark.django_db(transaction=True)
def test_parallele_erste_anlage_verwendet_denselben_schluessel(orgs):
    barrier = Barrier(2)
    generate = crypto.AESGCM.generate_key

    def synchronized(*args, **kwargs):
        raw = generate(*args, **kwargs)
        barrier.wait(timeout=10)
        return raw

    def create():
        try:
            return crypto.key_for_org(orgs["c"].pk)
        finally:
            connections.close_all()

    with patch("core.crypto.AESGCM.generate_key", side_effect=synchronized):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(create) for _ in range(2)]
            results = [future.result(timeout=15) for future in futures]
    assert results[0] == results[1]
    assert DataKey.objects.filter(organization=orgs["c"]).count() == 1
    # Der Cache wird hier nach echten Commits genutzt, nicht nur im Test-Savepoint.
    old = results[0]
    assert crypto.key_by_id(old[0]) == old[1]
    new = next_generation(orgs["c"])
    assert crypto.key_by_id(old[0]) == old[1]
    assert crypto.key_for_org(orgs["c"].pk) == new


@pytest.mark.langsam
@pytest.mark.django_db(transaction=True)
def test_migration_erhaelt_bestand_alte_inserts_und_sicheren_rueckweg(orgs):
    old = crypto.key_for_org(orgs["c"].pk)
    before = DataKey.objects.values().get(pk=old[0])
    cipher = crypto.encrypt_bytes(b"Bestandsdatei", *old)
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    previous = [("core", "0032_datenschluessel")]
    try:
        executor.migrate(previous)
        legacy = executor.loader.project_state(previous).apps.get_model("core", "DataKey")
        assert legacy.objects.get(pk=old[0]).wrapped == before["wrapped"]
        MigrationExecutor(connection).migrate(latest)
        assert DataKey.objects.values().get(pk=old[0]) == before
        # Die alte Anwendung kennt is_active noch nicht und muss weiterhin einfügen können.
        other_key = os.urandom(32)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO core_datakey (organization_id, wrapped, created_at) "
                "VALUES (%s, %s, NOW()) RETURNING id, is_active",
                [orgs["b"].pk, crypto.wrap_key(other_key, crypto._context(orgs["b"].pk))],
            )
            inserted, active = cursor.fetchone()
        assert active and crypto.key_for_org(orgs["b"].pk) == (inserted, other_key)
        new = next_generation(orgs["c"])
        with pytest.raises(DatabaseError, match="Generationen erhalten"):
            MigrationExecutor(connection).migrate(previous)
        # Frühere additive Migrationen können vor der gesperrten Stufe bereits
        # rückgängig sein; vor Zugriff mit den aktuellen Modellen wiederherstellen.
        MigrationExecutor(connection).migrate(latest)
        assert DataKey.objects.get(pk=new[0]).is_active
        assert crypto.key_by_id(old[0]) == old[1]
        assert crypto.decrypt_bytes(cipher) == b"Bestandsdatei"
        # Nur im Test: Noch keine Nutzdaten der neuen Generation, daher entfernbar.
        # Die leere spätere Auftragstabelle kann vor der gesperrten Rückmigration
        # bereits entfernt sein. Den Modellstand dieser tatsächlichen Schemafassung
        # verwenden, damit der Collector keine spätere Rückwärtsrelation abfragt.
        current_keys = (
            MigrationExecutor(connection)
            .loader.project_state([("core", "0033_datenschluessel_generationen")])
            .apps.get_model("core", "DataKey")
        )
        current_keys.objects.filter(pk=new[0]).delete()
        DataKey.objects.filter(pk=old[0]).update(is_active=False)
        with pytest.raises(DatabaseError, match="Generationen erhalten"):
            MigrationExecutor(connection).migrate(previous)
        DataKey.objects.filter(pk=old[0]).update(is_active=True)
        MigrationExecutor(connection).migrate(previous)
        assert legacy.objects.get(pk=old[0]).wrapped == before["wrapped"]
    finally:
        MigrationExecutor(connection).migrate(latest)
        crypto.reset()
