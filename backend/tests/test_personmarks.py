"""Suchmarken: gleiche Zuordnungsregeln, keine veralteten Identitätsindizes."""

import base64
import datetime
import io
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import pytest
from django.core.exceptions import FieldError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, OperationalError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor

from audit.log import snapshot
from changes.tracking import dump
from core import crypto
from core.tenancy import rls_bypass
from members import personmarks, services, workflows
from members.models import Person

from .factories import make_member

BIRTH = datetime.date(1980, 5, 17)


def person(scope, last="Muster", first="Erika", **extra):
    return Person.objects.create(
        scope=scope,
        last_name=last,
        first_name=first,
        birth_date=BIRTH,
        **extra,
    )


def marks(p):
    return {field: getattr(p, field) for field in personmarks.DERIVED_FIELDS}


def run(*args):
    out = io.StringIO()
    call_command("personen_suchmarken", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
class TestPersonMarks:
    def test_getrennte_zwecke_bereiche_und_daten(self, orgs):
        with rls_bypass():
            a = person(orgs["a"])
            b = person(orgs["b"])
            c = person(orgs["a"])
            assert marks(a) == marks(c)
            assert a.last_birth_mark != b.last_birth_mark
            assert a.last_birth_mark != a.first_birth_mark
            assert len(a.last_birth_mark) == 22
            assert a.last_year_mark == a.first_year_mark == ""
            raw = bytes(range(32))
            # Auch bei identischem Schlüsselmaterial trennt der Bereich die Marken.
            assert personmarks._mark(raw, 1, "last_birth_mark", "MUSTER", "1980-05-17") != (
                personmarks._mark(raw, 2, "last_birth_mark", "MUSTER", "1980-05-17")
            )
            assert personmarks._mark(raw, 1, "last_birth_mark", "MUSTER", "1980-05-17") != (
                personmarks._mark(raw, 1, "first_birth_mark", "MUSTER", "1980-05-17")
            )
            assert not set(personmarks.DERIVED_FIELDS) & dump(a).keys()
            assert "last_birth_mark" not in snapshot(a)

    def test_streng_und_vorschlaege_bleiben_verschieden(self, orgs):
        with rls_bypass():
            a = person(orgs["c"])
            b = person(orgs["c"], first="Andere")
            person(orgs["a"])
            assert services.persons_matching(orgs["c"].pk, "Muster", "Erika", BIRTH, limit=5) == [a]
            assert {p.pk for p in services.find_duplicates(orgs["c"], "Muster", "X", BIRTH)} == {
                a.pk,
                b.pk,
            }
            assert services.persons_matching(orgs["c"].pk, "Muster", "Erika", None, limit=5) == []
            assert services.find_duplicates(orgs["c"], "Muster", "Erika", None) == []

    @pytest.mark.parametrize(
        "stored,wanted",
        [
            ("Müller", "MÜLLER"),
            ("Straße", "Strasse"),
            ("Straße", "STRAẞE"),
            ("Öster", "O\u0308ster"),
            ("Ipek", "ıpek"),
            ("İpek", "ipek"),
            ("Σίγμα", "σίγμα"),
            ("Muster ", "Muster"),
            ("Muster", " muster "),
        ],
    )
    def test_gleiche_namensregeln_wie_bisherige_datenbank(self, orgs, stored, wanted):
        with rls_bypass():
            a = person(orgs["c"], last=stored)
            expected = list(
                Person.objects.filter(
                    scope=orgs["c"],
                    last_name__iexact=wanted.strip(),
                    first_name__iexact="Erika",
                ).order_by("pk")
            )
            assert (
                services.persons_matching(orgs["c"].pk, wanted, "Erika", BIRTH, limit=5) == expected
            )
            # Der Vorname darf bei Vorschlägen abweichen.
            assert services.find_duplicates(orgs["c"], wanted, "X", BIRTH) == expected
            assert a.marks_version == personmarks.VERSION

    def test_jahresmarken_nur_fuer_gekuerzte_daten(self, orgs):
        with rls_bypass():
            a = person(orgs["c"])
            before = marks(a)
            workflows._reduce_identity(a)
            a.refresh_from_db()
            assert a.birth_date == BIRTH.replace(month=1, day=1)
            assert a.last_birth_mark != before["last_birth_mark"]
            assert a.last_year_mark and a.first_year_mark
            assert services.find_duplicates(orgs["c"], "Muster", "X", BIRTH) == [a]
            assert services.persons_matching(orgs["c"].pk, "Muster", "Erika", BIRTH, limit=5) == []
            # Streng bedeutet das gespeicherte Datum, auch bei birth_year_only.
            assert services.persons_matching(
                orgs["c"].pk, "Muster", "Erika", a.birth_date, limit=5
            ) == [a]
            a.birth_year_only, a.birth_date = False, BIRTH
            a.save(update_fields=["birth_date", "birth_year_only"])
            assert not a.last_year_mark and not a.first_year_mark

    def test_teil_save_uebernimmt_aktuelle_andere_identitaetswerte(self, orgs):
        with rls_bypass():
            a = person(orgs["c"])
            stale = Person.objects.get(pk=a.pk)
            a.first_name = "Else"
            a.save(update_fields=["first_name"])
            stale.last_name = "Neu"
            stale.save(update_fields=["last_name"])
            stale.refresh_from_db()
            assert stale.first_name == "Else"
            assert marks(stale) == personmarks.values(stale)
            assert services.persons_matching(orgs["c"].pk, "Neu", "Else", BIRTH, limit=5) == [stale]

    def test_bereichswechsel_berechnet_marken_und_datumschluessel(self, orgs):
        from core.encfields import decrypt_text

        with rls_bypass():
            a = person(orgs["c"])
            before = marks(a)
            a.scope = orgs["a"]
            a.save(update_fields=["scope"])
            a.refresh_from_db()
            assert a.marks_key_id != before["marks_key_id"]
            assert a.last_birth_mark != before["last_birth_mark"]
            with connection.cursor() as cursor:
                cursor.execute("SELECT birth_date FROM members_person WHERE id = %s", [a.pk])
                raw = cursor.fetchone()[0]
            assert decrypt_text(raw, Person._meta.get_field("birth_date")) == BIRTH.isoformat()
            assert int.from_bytes(base64.b64decode(raw[5:])[:8], "big") == a.marks_key_id
            assert services.persons_matching(orgs["c"].pk, "Muster", "Erika", BIRTH, limit=5) == []
            assert services.persons_matching(orgs["a"].pk, "Muster", "Erika", BIRTH, limit=5) == [a]

    def test_fehler_rollt_identitaet_und_marken_zurueck(self, orgs):
        with rls_bypass():
            a = person(orgs["c"])
            before = marks(a)
            a.last_name = "Neu"
            with patch("members.personmarks.write", side_effect=ValueError("Testabbruch")):
                with pytest.raises(ValueError, match="Testabbruch"):
                    a.save(update_fields=["last_name"])
            a.refresh_from_db()
            assert a.last_name == "Muster" and marks(a) == before

    def test_unsafe_update_bulk_update_upsert_abgewiesen(self, orgs):
        with rls_bypass():
            a = person(orgs["c"])
            with pytest.raises(FieldError):
                Person.objects.filter(pk=a.pk).update(last_name="Neu")
            with pytest.raises(FieldError):
                Person.objects.bulk_update([a], ["last_name"])
            with pytest.raises(FieldError):
                Person.objects.bulk_create(
                    [a], update_conflicts=True, update_fields=["first_name"], unique_fields=["id"]
                )
            with pytest.raises(FieldError):
                a.save(update_fields=["marks_version"])
            Person.objects.filter(pk=a.pk).update(gender="divers")

    def test_bulk_create_pflegt_marken(self, orgs):
        with rls_bypass():
            rows = Person.objects.bulk_create(
                [
                    Person(scope=orgs["c"], last_name="Muster", first_name=str(n), birth_date=BIRTH)
                    for n in range(3)
                ]
            )
            for a in Person.objects.filter(pk__in=[p.pk for p in rows]):
                assert marks(a) == personmarks.values(a)

    def test_als_fertig_markierter_teilbestand_wird_abgewiesen(self, orgs):
        with rls_bypass():
            a = person(orgs["c"])
            with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE members_person SET last_birth_mark = '' WHERE id = %s", [a.pk]
                )

    def test_alte_inserts_ohne_neue_spalten_bleiben_moeglich(self, orgs):
        with rls_bypass():
            a = person(orgs["c"])
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO members_person "
                    "(scope_id, last_name, first_name, birth_date, birth_year_only, gender, "
                    "created_at, updated_at) "
                    "SELECT scope_id, 'Alt', first_name, birth_date, birth_year_only, gender, "
                    "created_at, updated_at FROM members_person WHERE id = %s RETURNING id",
                    [a.pk],
                )
                pk = cursor.fetchone()[0]
            old = Person.objects.get(pk=pk)
            assert old.marks_version == 0 and not old.last_birth_mark
            assert services.persons_matching(orgs["c"].pk, "Alt", "Erika", BIRTH, limit=5) == [old]
            run()
            old.refresh_from_db()
            assert marks(old) == personmarks.values(old)

    def test_alter_writer_entwertet_alle_marken(self, orgs):
        with rls_bypass():
            a = person(orgs["c"])
            with connection.cursor() as cursor:
                cursor.execute("UPDATE members_person SET last_name = 'Neu' WHERE id = %s", [a.pk])
            a.refresh_from_db()
            assert all(getattr(a, field) == "" for field in personmarks.MARK_FIELDS)
            assert a.marks_version == 0 and a.marks_key_id is None
            assert services.persons_matching(orgs["c"].pk, "Neu", "Erika", BIRTH, limit=5) == [a]
            assert services.persons_matching(orgs["c"].pk, "Muster", "Erika", BIRTH, limit=5) == []

    def test_backfill_prueft_alle_werte_und_ist_wiederholbar(self, orgs):
        with rls_bypass():
            a = person(orgs["c"])
            stamp = a.updated_at
            # Auch scheinbar vollständige, aber falsche Marken werden erkannt.
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE members_person SET last_birth_mark = %s WHERE id = %s", ["X" * 22, a.pk]
                )
            with pytest.raises(CommandError):
                run("--pruefen")
            assert "Abweichungen: 1" in run()
            a.refresh_from_db()
            assert marks(a) == personmarks.values(a)
            assert a.updated_at == stamp
            assert "Abweichungen: 0" in run()
            assert "Abweichungen: 0" in run("--pruefen")

    def test_backfill_abbruch_und_wiederaufnahme(self, orgs):
        with rls_bypass():
            rows = [person(orgs["c"], first=str(n)) for n in range(3)]
            with connection.cursor() as cursor:
                cursor.execute("UPDATE members_person SET marks_version = 0")
            original = personmarks.values
            calls = 0

            def interrupted(p, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("Testabbruch")
                return original(p, **kwargs)

            with patch("members.management.commands.personen_suchmarken.values", interrupted):
                with pytest.raises(RuntimeError, match="Testabbruch"):
                    run()
            assert Person.objects.get(pk=rows[0].pk).marks_version == personmarks.VERSION
            assert Person.objects.get(pk=rows[1].pk).marks_version == 0
            assert "Abweichungen: 2" in run()
            run("--pruefen")

    def test_falsche_kandidaten_werden_nicht_zugeordnet(self, orgs):
        with rls_bypass():
            a = person(orgs["c"])
            b = person(orgs["c"], last="Andere", first="Person")
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE members_person SET last_birth_mark = %s, first_birth_mark = %s "
                    "WHERE id = %s",
                    [a.last_birth_mark, a.first_birth_mark, b.pk],
                )
            assert services.persons_matching(orgs["c"].pk, "Muster", "Erika", BIRTH, limit=1) == [a]
            assert services.find_duplicates(orgs["c"], "Muster", "Erika", BIRTH) == [a]

    def test_schluessel_und_formatwechsel_fallen_auf_gepruefte_werte_zurueck(self, orgs):
        with rls_bypass():
            a = person(orgs["c"])
            for sql in ("marks_key_id = -1", "marks_version = 99"):
                with connection.cursor() as cursor:
                    cursor.execute(f"UPDATE members_person SET {sql} WHERE id = %s", [a.pk])  # noqa: S608
                assert services.persons_matching(
                    orgs["c"].pk, "Muster", "Erika", BIRTH, limit=5
                ) == [a]
                with pytest.raises(CommandError):
                    run("--pruefen")
                run()

    def test_unlesbares_datum_wird_gemeldet(self, orgs):
        with rls_bypass():
            a = person(orgs["c"])
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE members_person SET birth_date = %s WHERE id = %s", ["enc1:kaputt", a.pk]
                )
            with pytest.raises(CommandError):
                run()

    def test_pruefen_legt_keinen_fehlenden_datenschluessel_an(self, orgs):
        from core.models import DataKey

        with rls_bypass():
            a = person(orgs["c"])
            # Unverschlüsselter Altbestand ohne Datenschlüssel: Prüfung muss lesend bleiben.
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE members_person SET birth_date = %s WHERE id = %s",
                    [BIRTH.isoformat(), a.pk],
                )
            DataKey.objects.filter(organization=orgs["c"]).delete()
            crypto.reset()
            with pytest.raises(CommandError):
                run("--pruefen")
            assert not DataKey.objects.filter(organization=orgs["c"]).exists()
            run()
            run("--pruefen")

    def test_namensentfernung_loescht_alte_marken(self, orgs):
        m = make_member(orgs["c"], "Erika", "Muster", birth_date=BIRTH)
        with rls_bypass():
            before = marks(m.person)
            workflows.erase_history(m, listed=True)
            p = Person.objects.get(pk=m.person_id)
            assert p.last_name == workflows.NAME_REMOVED
            assert p.last_birth_mark != before["last_birth_mark"]
            assert p.first_birth_mark != before["first_birth_mark"]
            assert services.find_duplicates(orgs["c"], "Muster", "Erika", BIRTH) == []

    def test_umverpacken_aendert_keine_marken(self, orgs, settings):
        with rls_bypass():
            a = person(orgs["c"])
            before = marks(a)
            settings.DATA_ENCRYPTION_KEYS = ["Q" * 43, *settings.DATA_ENCRYPTION_KEYS]
            crypto.reset()
            call_command("datenschluessel_umverpacken", stdout=io.StringIO())
            crypto.reset()
            assert personmarks.values(a) == before


@pytest.mark.langsam
@pytest.mark.django_db(transaction=True)
def test_migration_bestand_und_rueckweg(orgs):
    with rls_bypass():
        a = person(orgs["c"])
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [("members", "0022_geburtsdatum_verschluesselt")]
        try:
            executor.migrate(previous)
            old = executor.loader.project_state(previous).apps.get_model("members", "Person")
            assert old.objects.get(pk=a.pk).birth_date == BIRTH
            old.objects.create(
                scope_id=orgs["c"].pk,
                last_name="Bestand",
                first_name="Else",
                birth_date=BIRTH,
            )
        finally:
            MigrationExecutor(connection).migrate(latest)
        a.refresh_from_db()
        assert a.last_name == "Muster" and a.birth_date == BIRTH
        assert a.marks_version == 0
        assert services.persons_matching(orgs["c"].pk, "Bestand", "Else", BIRTH, limit=5)
        run()
        run("--pruefen")


@pytest.mark.django_db(transaction=True)
def test_backfill_sperrt_gegen_gleichzeitige_identitaetsaenderung(orgs):
    with rls_bypass():
        a = person(orgs["c"])
        with connection.cursor() as cursor:
            cursor.execute("UPDATE members_person SET marks_version = 0 WHERE id = %s", [a.pk])
    locked, resume = Event(), Event()
    original = personmarks.values

    def pause(p, **kwargs):
        result = original(p, **kwargs)
        locked.set()
        assert resume.wait(10), "Test: Bestandslauf nicht freigegeben"
        return result

    def backfill():
        try:
            return run()
        finally:
            connections.close_all()

    with patch("members.management.commands.personen_suchmarken.values", pause):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(backfill)
            try:
                assert locked.wait(10), "Test: Zeilensperre nicht erreicht"
                with rls_bypass():
                    # Ein echter zweiter DB-Zugang muss an derselben Zeile warten.
                    with pytest.raises(OperationalError), transaction.atomic():
                        with connection.cursor() as cursor:
                            cursor.execute("SET LOCAL lock_timeout = '100ms'")
                        a.last_name = "Neu"
                        a.save(update_fields=["last_name"])
            finally:
                resume.set()
            future.result(timeout=10)
    with rls_bypass():
        a.save(update_fields=["last_name"])
        a.refresh_from_db()
        assert a.last_name == "Neu"
        assert marks(a) == personmarks.values(a)
        run("--pruefen")


@pytest.mark.langsam
@pytest.mark.django_db(transaction=True)
def test_kandidaten_5000_personen(orgs):
    with rls_bypass():
        Person.objects.bulk_create(
            [
                Person(
                    scope=orgs["c"],
                    last_name=f"Muster {i}",
                    first_name=f"Person {i}",
                    birth_date=BIRTH,
                )
                for i in range(5000)
            ]
        )
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE members_person")
        started = time.perf_counter()
        qs = personmarks.candidates(orgs["c"].pk, "Muster 100", "Person 100", BIRTH, strict=True)
        assert qs.count() == 1
        found = services.persons_matching(orgs["c"].pk, "Muster 100", "Person 100", BIRTH, limit=5)
        assert len(found) == 1
        print(
            f"Personenabgleich 5000 / ein Treffer: {(time.perf_counter() - started) * 1000:.1f} ms"
        )
        # Tatsächlicher Plan einschließlich Rückfall für unmarkierte Datensätze.
        print(qs.explain(analyze=True))
