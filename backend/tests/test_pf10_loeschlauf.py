"""Löschlauf: schnell bei vielen ehemaligen Mitgliedern, fehlerisoliert, nie doppelt (PF-10).

Gesamtaudit 15.11., PF-10: Der tägliche Löschfrist-Lauf fragte je ehemaliger Mitgliedschaft
einzeln nach dem letzten Austritt; bei 10.000 ehemaligen Mitgliedern lief eine Abfrage über
70 Minuten. Ein einzelner Fehler hielt alle übrigen Löschungen an, und zwei Läufe konnten
gleichzeitig arbeiten.
"""

import datetime
import json
import time
from unittest import mock

import pytest
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext

from core.tenancy import rls_bypass, tenant_context
from members import loeschliste, tasks, workflows
from members.models import Membership, MembershipPeriod, Person

from .factories import make_member, make_org

pytestmark = pytest.mark.django_db

TODAY = datetime.date(2026, 11, 15)
LONG_AGO = datetime.date(2015, 1, 1)  # Frist (24 Monate) längst um
RECENT = datetime.date(2026, 10, 15)  # Frist läuft noch


@pytest.fixture(autouse=True)
def _liste(settings, tmp_path):
    settings.LOESCHLISTE_PATH = str(tmp_path / "loeschliste" / "loeschliste.jsonl")


def _former(club, n: int, exit_date: datetime.date) -> list[int]:
    """n ehemalige Mitglieder ohne Fachlogik anlegen (schnell, nur für Mengenmessungen)."""
    with tenant_context(club.pk):
        persons = Person.objects.bulk_create(
            Person(scope=club, last_name=f"Muster{i:05d}", first_name="Erika") for i in range(n)
        )
        memberships = Membership.objects.bulk_create(
            Membership(organization=club, scope=club, person=p) for p in persons
        )
        MembershipPeriod.objects.bulk_create(
            MembershipPeriod(
                organization=club,
                membership=m,
                entry_date=datetime.date(2010, 1, 1),
                exit_date=exit_date,
            )
            for m in memberships
        )
    return [m.pk for m in memberships]


def _leave(club, member, exit_date=LONG_AGO):
    with tenant_context(club.pk):
        MembershipPeriod.objects.filter(membership=member).update(exit_date=exit_date)


@pytest.mark.langsam
def test_zehntausend_ehemalige_ohne_faellige_loeschung():
    club = make_org("Löschverein Menge")
    _former(club, 10_000, RECENT)
    with CaptureQueriesContext(connection) as queries:
        start = time.perf_counter()
        assert workflows.purge_expired(on=TODAY) == 0
        seconds = time.perf_counter() - start
    print(f"PF-MESSUNG PF-10 n=10000 queries={len(queries)} s={seconds:.2f}")
    # Vorher: eine Abfrage je ehemaliger Mitgliedschaft und über 70 Minuten
    assert len(queries) <= 5
    assert seconds < 30


def test_abfragen_unabhaengig_von_der_menge():
    club = make_org("Löschverein Zählung")
    _former(club, 5, RECENT)
    with CaptureQueriesContext(connection) as small:
        workflows.purge_expired(on=TODAY)
    _former(club, 300, RECENT)
    due = _former(club, 2, LONG_AGO)
    with CaptureQueriesContext(connection) as large:
        assert workflows.due_for_purge(TODAY - datetime.timedelta(days=730)) == due
    assert len(large) <= 3  # eine Abfrage, dazu Zeilenschutz aus und wieder an
    assert len(small) <= 5


def test_nur_faellige_und_ohne_offenen_zeitraum():
    club = make_org("Löschverein Auswahl")
    due = make_member(club, "Erika", "Fällig")
    _leave(club, due)
    active = make_member(club, "Max", "Aktiv")
    rejoined = make_member(club, "Otto", "Wieder")
    _leave(club, rejoined)
    with tenant_context(club.pk):
        MembershipPeriod.objects.create(
            organization=club, membership=rejoined, entry_date=datetime.date(2020, 1, 1)
        )
    pending = make_member(club, "Lena", "Frist")
    _leave(club, pending, RECENT)
    assert workflows.purge_expired(on=TODAY) == 1
    with rls_bypass():
        purged = set(
            Membership.objects.filter(purged_at__isnull=False).values_list("pk", flat=True)
        )
    assert purged == {due.pk}
    assert {active.pk, rejoined.pk, pending.pk}.isdisjoint(purged)


def test_ein_fehler_haelt_die_uebrigen_nicht_auf():
    club = make_org("Löschverein Fehler")
    members = [make_member(club, f"Erika{i}", "Muster") for i in range(3)]
    for m in members:
        _leave(club, m)
    original = workflows.purge_membership
    calls = []

    def first_fails(membership, **kw):
        calls.append(membership.pk)
        if len(calls) == 1:
            raise RuntimeError("erfundener Einzelfehler")
        return original(membership, **kw)

    with (
        mock.patch.object(workflows, "purge_membership", first_fails),
        mock.patch("core.alarm.send_alert") as alert,
    ):
        assert workflows.purge_expired(on=TODAY) == 2
        workflows.purge_expired(on=TODAY)  # nächster Lauf: der erste klappt jetzt
    with rls_bypass():
        assert not Membership.objects.filter(organization=club, purged_at__isnull=True).exists()
    assert alert.call_count == 1
    assert "Löschfrist: Löschungen gescheitert" in alert.call_args.args[0]
    assert str(members[0].pk) in "\n".join(alert.call_args.args[1])


def test_zweiter_lauf_endet_sofort():
    club = make_org("Löschverein Sperre")
    member = make_member(club, "Erika", "Muster")
    _leave(club, member)
    other = connections.create_connection("default")
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [workflows.PURGE_LOCK])
        with mock.patch.object(tasks, "purge_expired") as purge:
            assert tasks.purge_expired_members() is None
        purge.assert_not_called()
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [workflows.PURGE_LOCK])
    finally:
        other.close()
    with mock.patch.object(tasks, "purge_expired", return_value=0) as purge:
        assert tasks.purge_expired_members() == 0
    purge.assert_called_once()


def _write_list(settings, items):
    path = loeschliste.path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item) + "\n")


def _entry(membership, **extra):
    return {
        "m": membership.pk,
        "o": membership.organization_id,
        "p": membership.person_id,
        "c": membership.created_at.isoformat(),
        "d": True,
        **extra,
        "at": "2026-01-01T00:00:00+00:00",
    }


def test_loeschliste_liest_gesammelt(settings):
    club = make_org("Löschverein Liste")
    pks = _former(club, 300, LONG_AGO)
    with rls_bypass():
        Membership.objects.filter(pk__in=pks).update(purged_at=datetime.datetime(2026, 1, 1))
        rows = list(Membership.objects.filter(pk__in=pks))
    _write_list(settings, [_entry(m) for m in rows])
    with CaptureQueriesContext(connection) as queries:
        assert loeschliste.apply() == 0
    # Vorher eine Abfrage je Eintrag der (wachsenden) Liste
    assert len(queries) <= 3


def test_loeschliste_fehler_haelt_die_uebrigen_nicht_auf(settings):
    club = make_org("Löschverein Liste Fehler")
    members = [make_member(club, f"Erika{i}", "Muster") for i in range(3)]
    with rls_bypass():
        rows = list(Membership.objects.filter(pk__in=[m.pk for m in members]).order_by("pk"))
    # Liste sagt „gelöscht“, die Datenbank (eingespieltes Backup) nicht
    _write_list(settings, [_entry(m) for m in rows])
    original = workflows.purge_membership
    calls = []

    def first_fails(membership, **kw):
        calls.append(membership.pk)
        if len(calls) == 1:
            raise RuntimeError("erfundener Einzelfehler")
        return original(membership, **kw)

    with (
        mock.patch.object(workflows, "purge_membership", first_fails),
        mock.patch("core.alarm.send_alert") as alert,
    ):
        assert loeschliste.apply() == 2
    with rls_bypass():
        left = list(
            Membership.objects.filter(
                pk__in=[m.pk for m in rows], purged_at__isnull=True
            ).values_list("pk", flat=True)
        )
    assert left == [rows[0].pk]
    assert any("Löschliste: Löschungen gescheitert" in c.args[0] for c in alert.call_args_list)


def test_loeschliste_name_bei_zwei_mitgliedschaften_im_selben_verein(settings):
    """Verein und Untereinheit: Nach dem Einspielen ist der Name wieder da und wird wieder
    entfernt, auch ohne Würden oder Ehrungen (Durchsicht #508)."""
    club = make_org("Löschverein Baum")
    unit = make_org("Löschverein Abteilung", "unit", parent=club)
    member = make_member(club, "Erika", "Baum")
    with rls_bypass():
        Membership.objects.create(organization=unit, scope=club, person=member.person)
        Membership.objects.filter(person=member.person).update(
            purged_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
        )
        row = Membership.objects.get(pk=member.pk)
    _write_list(settings, [_entry(row, h=True)])
    assert loeschliste.apply() == 1
    with rls_bypass():
        person = Person.objects.get(pk=member.person_id)
    assert person.last_name == workflows.NAME_REMOVED
    assert loeschliste.apply() == 0
