"""SEPA-Mandate und Haushaltszahler werden bereinigt (Gesamtaudit 15.11., PF-16).

Vorher blieben Kontoinhaber und IBAN in Mandaten ehemaliger Mitglieder sowie Name, Anschrift
und Mail externer Haushaltszahler unbefristet. Erfundene Daten.
"""

import datetime

import pytest

from billing.models import HouseholdPayer, Mandate
from core.tenancy import rls_bypass, tenant_context
from finance import retention
from members.models import Household, HouseholdMember, Membership
from members.workflows import purge_membership

from .factories import make_member, make_org

pytestmark = pytest.mark.django_db
IBAN = "DE02120300000000202051"


def _mandate(club, member, ref, signed, **extra):
    with tenant_context(club.pk):
        return Mandate.objects.create(
            organization=club,
            membership=member,
            reference=ref,
            holder="Erika Muster",
            iban=IBAN,
            signed_on=signed,
            source="paper",
            **extra,
        )


def test_beendete_mandate_mit_den_buechern_anonymisiert():
    club = make_org("Mandatsverein")
    member = make_member(club, "Erika", "Muster")
    revoked = _mandate(
        club,
        member,
        "M-1",
        datetime.date(2020, 1, 1),
        status="revoked",
        revoked_on=datetime.date(2025, 6, 1),
    )
    # Je Zahler höchstens ein gültiges Mandat (B-M07): das ungenutzte gehört einem zweiten Mitglied
    other = make_member(club, "Otto", "Beispiel")
    unused = _mandate(
        club, other, "M-2", datetime.date(2020, 1, 1), last_used_on=datetime.date(2022, 3, 1)
    )  # 36 Monate ohne Lastschrift: endete am 01.03.2025
    running = _mandate(
        club, member, "M-3", datetime.date(2024, 1, 1), last_used_on=datetime.date(2025, 11, 1)
    )
    later = _mandate(
        club,
        member,
        "M-4",
        datetime.date(2020, 1, 1),
        status="revoked",
        revoked_on=datetime.date(2026, 2, 1),
    )
    with tenant_context(club.pk):
        counts = retention._anonymize_records(
            club, datetime.date(2025, 1, 1), datetime.date(2025, 12, 31)
        )
    assert counts["SEPA-Mandate"] == 2
    with rls_bypass():
        rows = {m.pk: m for m in Mandate.objects.all()}
    for gone in (revoked, unused):
        m = rows[gone.pk]
        assert (m.holder, m.iban, m.bic) == (retention.ANON, "", "")
        assert m.reference == gone.reference  # Referenz bleibt als Beleg
    for kept in (running, later):
        assert (rows[kept.pk].holder, rows[kept.pk].iban) == ("Erika Muster", IBAN)


def test_externer_zahler_geht_mit_dem_letzten_mitglied():
    from members.workflows import _purge_household_payers

    club = make_org("Haushaltsverein")
    first = make_member(club, "Erika", "Muster")
    second = make_member(club, "Max", "Muster")
    with tenant_context(club.pk):
        home = Household.objects.create(organization=club, name="Familie Muster")
        for m in (first, second):
            HouseholdMember.objects.create(
                organization=club,
                household=home,
                membership=m,
                kind=home.kind,
                valid_from=datetime.date(2020, 1, 1),
            )
        HouseholdPayer.objects.create(
            organization=club,
            household=home,
            kind=HouseholdPayer.Kind.EXTERNAL,
            name="Oma Muster",
            street="Lindenweg 4",
            postal_code="12345",
            city="Musterstadt",
            email="oma@example.org",
        )
        # Max ist bereinigt, Erika noch Mitglied: Zahler bleibt
        Membership.objects.filter(pk=second.pk).update(
            purged_at=datetime.datetime.now(datetime.UTC)
        )
        _purge_household_payers([home.pk])
        assert HouseholdPayer.objects.get(household=home).name == "Oma Muster"
        # Auch Erika bereinigt (der Haushalt bleibt, etwa wegen Einzug über sein Mandat)
        Membership.objects.filter(pk=first.pk).update(purged_at=datetime.datetime.now(datetime.UTC))
        _purge_household_payers([home.pk])
        payer = HouseholdPayer.objects.get(household=home)
    assert (payer.name, payer.street, payer.city, payer.email) == ("", "", "", "")
    assert payer.kind == HouseholdPayer.Kind.EXTERNAL


def test_haushalt_ohne_mitglieder_entfaellt_mit_zahler():
    club = make_org("Haushaltsverein 2")
    only = make_member(club, "Lena", "Muster")
    with tenant_context(club.pk):
        home = Household.objects.create(organization=club, name="Familie Muster")
        HouseholdMember.objects.create(
            organization=club,
            household=home,
            membership=only,
            kind=home.kind,
            valid_from=datetime.date(2020, 1, 1),
        )
        HouseholdPayer.objects.create(
            organization=club, household=home, kind=HouseholdPayer.Kind.EXTERNAL, name="Opa"
        )
        purge_membership(Membership.objects.get(pk=only.pk), after_deadline=True)
    with rls_bypass():
        assert not HouseholdPayer.objects.filter(household_id=home.pk).exists()
