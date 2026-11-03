"""Audit 02.11., P2: Budgets atomar (BP-S02), weniger Abfragen (BP-P01, BP-P02, BP-P03)."""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime
import threading

import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from billing import services as billing_services
from billing.models import Mandate
from core import jobquota
from core.tenancy import tenant_context
from exchange.models import ExportJob
from finance import bank_import
from finance.models import BankLine
from members.models import MemberType, MemberTypeAssignment

from .factories import make_member, named
from .test_kontoauszug import camt_xml, entry, fin, upload  # noqa: F401
from .test_m9_billing import JSON, base, c, club, members, setup, zug  # noqa: F401
from .test_m10_billing import fbase, fc, fed, fsetup  # noqa: F401

pytestmark = pytest.mark.django_db

EXPORT = {
    "active_statuses": [ExportJob.Status.PENDING, ExportJob.Status.RUNNING],
    "max_active": 3,
    "max_per_hour": 60,
    "what": "Listen-Exporte",
}


def _key(qs) -> int:
    import zlib

    return jobquota.LOCK_BASE + zlib.crc32(qs.model._meta.label.encode()) % 1_000_000


# --- BP-S02: Jobplätze ---


class TestJobplatz:
    def test_sperre_bis_ende_der_transaktion(self, orgs):
        org = orgs["a"]
        qs = ExportJob.objects.filter(organization=org)
        with transaction.atomic():
            jobquota.ensure_capacity(qs, org_id=org.pk, **EXPORT)
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                    "AND pid = pg_backend_pid() AND classid::bigint = %s AND objid::bigint = %s",
                    [org.pk, _key(qs)],
                )
                assert cur.fetchone()[0] == 1


@pytest.mark.django_db(transaction=True)
def test_zweite_pruefung_wartet(orgs):
    """Zwei getrennte Datenbankverbindungen: Die zweite bekommt den Platz erst danach."""
    org = orgs["a"]
    qs = ExportJob.objects.filter(organization=org)
    seen = {}

    def other():
        try:
            with transaction.atomic(), connection.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_xact_lock(%s, %s)", [org.pk, _key(qs)])
                seen["free"] = cur.fetchone()[0]
        finally:
            connection.close()

    with transaction.atomic():
        jobquota.ensure_capacity(qs, org_id=org.pk, **EXPORT)
        worker = threading.Thread(target=other)
        worker.start()
        worker.join(10)
    assert seen == {"free": False}
    worker = threading.Thread(target=other)
    worker.start()
    worker.join(10)
    assert seen == {"free": True}


# --- BP-P03: Beitragszählung ---


class TestBeitragszaehlung:
    def _count(self, fed, club, on):
        with CaptureQueriesContext(connection) as ctx:
            counts = billing_services.reported_counts(fed, club, on)
        return counts, len(ctx.captured_queries)

    def test_abfragen_unabhaengig_von_der_mitgliederzahl(self, fed, fsetup, orgs):
        a = orgs["a"]
        on = datetime.date(2025, 3, 1)
        counts, few = self._count(fed, a, on)
        assert sum(counts.values()) == 4
        for i in range(12):
            make_member(a, f"Neu{i}", "Mitglied")
        counts, many = self._count(fed, a, on)
        assert sum(counts.values()) == 16
        assert many == few

    def test_artwechsel_am_stichtag(self, fed, fsetup, orgs):
        a = orgs["a"]
        with tenant_context(a.pk):
            aktiv = MemberType.objects.get(organization=a, name="aktiv")
            old = named(
                MemberTypeAssignment.objects.filter(organization=a),
                membership__person__first_name="Paula",
            ).get()
            old.valid_until = datetime.date(2025, 5, 31)
            old.save()
            MemberTypeAssignment.objects.create(
                organization=a,
                membership=old.membership,
                member_type=aktiv,
                valid_from=datetime.date(2025, 6, 1),
            )

        def kinds(on):
            counts = billing_services.reported_counts(fed, a, on)
            result = {}
            for (kind, _stage, _titles), n in counts.items():
                result[kind] = result.get(kind, 0) + n
            return result

        assert kinds(datetime.date(2025, 5, 31)) == {"active": 3, "passive": 1}
        assert kinds(datetime.date(2025, 6, 1)) == {"active": 4}


# --- BP-P02: Kontoauszugsliste ---


class TestAuszugsliste:
    def test_saldo_und_offene_ohne_abfragen_je_auszug(self, c, fin, club):
        for i in range(2):
            data = camt_xml([entry("1.00", ref=f"L{i}")], closing="1.00")
            assert upload(c, fin, data, name=f"a{i}.xml").status_code == 201
        with CaptureQueriesContext(connection) as ctx:
            few = c.get(f"{fin}/bank-statements/").json()["results"]
        n_few = len(ctx.captured_queries)
        for i in range(2, 6):
            data = camt_xml([entry("1.00", ref=f"L{i}")], closing="1.00")
            assert upload(c, fin, data, name=f"a{i}.xml").status_code == 201
        with CaptureQueriesContext(connection) as ctx:
            many = c.get(f"{fin}/bank-statements/").json()["results"]
        assert len(ctx.captured_queries) == n_few
        assert len(few) == 2 and len(many) == 6
        assert all(s["open_count"] == 1 for s in many)
        # Gleicher Stand wie die Einzelansicht
        single = c.get(f"{fin}/bank-statements/{many[0]['id']}/").json()
        assert single["balance"] == many[0]["balance"]
        assert many[0]["balance"]["bank"] == "1.00"


# --- BP-P01: Vorschläge ---


class TestVorschlaege:
    def test_mandate_einmal_je_lauf(self, c, fin, club, members, monkeypatch):
        with tenant_context(club.pk):
            for i, key in enumerate(("erika", "jung")):
                Mandate.objects.create(
                    organization=club,
                    membership=members[key],
                    reference=f"M-{i}",
                    holder="Inhaber",
                    iban="DE02120300000000202051" if i == 0 else "DE44500105175407324931",
                    signed_on=datetime.date(2024, 1, 1),
                    source="paper",
                )
        data = camt_xml(
            [entry("3.00", ref=f"V{i}", purpose="Spende") for i in range(5)],
        )
        assert upload(c, fin, data).status_code == 201
        built = []
        real = bank_import._iban_index
        monkeypatch.setattr(bank_import, "_iban_index", lambda org: built.append(1) or real(org))
        with tenant_context(club.pk):
            bank_import.suggest_all(club)
            lines = list(BankLine.objects.filter(organization=club))
        assert len(built) == 1
        assert {line.suggested_membership_id for line in lines} == {members["erika"].pk}
