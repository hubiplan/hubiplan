"""Gesamtaudit 05.11. GA-08 (F-06): Kasse und Protokoll auch in der Datenbank geschützt."""

import datetime

import pytest
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.test import override_settings

from audit.chain import seal
from audit.log import record
from audit.models import AuditEntry
from core.tenancy import rls_bypass, tenant_context
from finance import gobd
from finance.models import Account, Booking, Receipt
from organizations.models import Organization

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
DAY = datetime.date(2025, 3, 1)


def _booking(org, number=1, day=DAY):
    account = Account.objects.get_or_create(
        organization=org, name="Bank", defaults={"opening_date": "2025-01-01"}
    )[0]
    return Booking.objects.create(
        organization=org,
        account=account,
        year=day.year,
        number=number,
        date=day,
        kind="income",
        amount="10.00",
        text="Spende",
    )


def _lock(org, until=DAY):
    Organization.objects.filter(pk=org.pk).update(finance_locked_until=until)


def _blocked(fn) -> bool:
    try:
        with transaction.atomic():
            fn()
    except IntegrityError:
        return True
    return False


def test_festgeschriebene_buchung_nur_text_aenderbar(orgs):
    org = orgs["a"]
    with tenant_context(org.pk):
        b = _booking(org)
        _lock(org)
        qs = Booking.objects.filter(pk=b.pk)
        assert _blocked(lambda: qs.update(amount="99.00"))
        assert _blocked(lambda: qs.update(date=DAY - datetime.timedelta(days=1)))
        assert _blocked(lambda: qs.delete())
        assert not _blocked(lambda: qs.update(reference="K-1", frozen=True))
        b.text = "Spende (neu verschlüsselt)"
        b.save(update_fields=["text"])
        assert qs.get().amount == 10


def test_offene_buchung_bleibt_frei(orgs):
    org = orgs["a"]
    with tenant_context(org.pk):
        b = _booking(org, day=DAY + datetime.timedelta(days=1))
        _lock(org)
        Booking.objects.filter(pk=b.pk).update(amount="12.00")
        Booking.objects.filter(pk=b.pk).delete()
        assert not Booking.objects.filter(pk=b.pk).exists()


def test_beleg_einer_festgeschriebenen_buchung_nicht_loeschbar(orgs):
    org = orgs["a"]
    with tenant_context(org.pk):
        b = _booking(org)
        receipt = Receipt.objects.create(
            organization=org,
            booking=b,
            file=ContentFile(b"%PDF-1.4", name="beleg.pdf"),
            name="beleg.pdf",
            content_type="application/pdf",
        )
        _lock(org)
        assert _blocked(lambda: Receipt.objects.filter(pk=receipt.pk).delete())
        with transaction.atomic():
            gobd.release_unit(org.pk)
            Receipt.objects.filter(pk=receipt.pk).delete()
            Booking.objects.filter(pk=b.pk).delete()
        assert not Booking.objects.filter(pk=b.pk).exists()


def test_einheit_loeschen_trotz_festschreibung(api, orgs, django_user_model):
    org = orgs["c"]
    with tenant_context(org.pk):
        b = _booking(org)
    _lock(org)
    admin = django_user_model.objects.create_superuser(email="erase@example.org", password="x")
    resp = api(admin).post(
        f"/api/platform/orgs/{org.pk}/erase/",
        {"confirmation": org.name},
        content_type="application/json",
    )
    assert resp.status_code == 204, resp.content
    assert not Booking.objects.filter(pk=b.pk).exists()


def test_versiegelter_protokolleintrag_unveraenderbar(orgs, board_a):
    club = orgs["a"]
    with tenant_context(club.pk):
        record(club, board_a, "update", club, {"Name": ["A", "B"]})
    with rls_bypass():
        entry = AuditEntry.objects.filter(organization=club).latest("pk")
        # Noch nicht versiegelt: die Kette darf ihn einsortieren
        assert entry.hash == ""
    seal(club.pk)
    with rls_bypass():
        qs = AuditEntry.objects.filter(pk=entry.pk)
        assert qs.get().hash
        assert _blocked(lambda: qs.update(action="delete"))
        assert _blocked(lambda: qs.update(hash="0" * 64))
        assert _blocked(lambda: qs.update(timestamp=entry.timestamp - datetime.timedelta(days=1)))
        # Löschfristen und DSGVO-Auskunft leeren weiter den Inhalt
        qs.update(changes={}, object_repr="", cleared=True)
        assert qs.get().cleared


@override_settings(HUBIPLAN_LANGUAGES=["de", "en"])
def test_kettenkopf_woechentlich_an_kassenpruefer(orgs, board_a, mailoutbox):
    from audit.models import AuditCheck
    from audit.tasks import check_chains, mail_heads

    club = orgs["a"]
    pruefer = make_user("pruefer@example.org", language="en")
    with tenant_context(club.pk):
        give_role(pruefer, club, ["finance.view"], name="Kassenprüfer")
        record(club, board_a, "update", club, {"Name": ["A", "B"]})
    check_chains()
    check = AuditCheck.objects.get(organization=club)
    mailoutbox.clear()
    assert mail_heads() >= 1
    mails = [m for m in mailoutbox if "pruefer@example.org" in m.to]
    assert len(mails) == 1
    line = f"{club.pk} {check.head_seq} {check.head_hash}"
    assert line in mails[0].body
    assert "Change log checksum" in mails[0].subject
    # Vorstand mit Bearbeitungsrecht bekommt sie nicht
    assert not [m for m in mailoutbox if board_a.email in m.to]
