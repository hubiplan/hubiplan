# ruff: noqa: F401, F811  (Fixtures aus anderen Testdateien)
"""Festgeschriebene Kasse: keine neuen Buchungen und kein Verschieben in den Zeitraum
(Gesamtaudit 15.11., PUB-08). Erfundene Daten.

Abläufe, die festgeschriebene Buchungen berühren, und was hier geprüft ist:
- Anlegen (Oberfläche, Datenbank): abgewiesen.
- Datum, Betrag, Konto, Kategorie ändern (in den Zeitraum hinein oder darin): abgewiesen.
- Löschen: abgewiesen (finance/0024, hier mitgeprüft).
- Text ändern (Anonymisieren nach der Aufbewahrungsfrist, Schlüsselwechsel): erlaubt.
- Storno: Gegenbuchung mit heutigem Datum, also nach der Festschreibung: erlaubt.
- Datenübernahme (Umzug einer Einheit): „festgeschrieben bis“ wird erst nach den Buchungen
  gesetzt, die Buchungen kommen vollständig mit.
- Jahresabschluss legt keine Buchungen an (nur Abschlussstand); nicht betroffen.
"""

import datetime

import pytest
from django.db import IntegrityError, transaction

from core.tenancy import rls_bypass, tenant_context
from finance.models import Account, Booking
from organizations.models import Organization

from .test_datatransfer import _eager, _on_commit_now, club_c, export, types, upload
from .verbund_netz import app_role

pytestmark = pytest.mark.django_db
DAY = datetime.date(2025, 3, 31)
JSON = "application/json"


def _account(org):
    return Account.objects.get_or_create(
        organization=org, name="Bank", defaults={"opening_date": "2025-01-01"}
    )[0]


def _booking(org, date, number):
    return Booking.objects.create(
        organization=org,
        account=_account(org),
        year=date.year,
        number=number,
        date=date,
        kind="income",
        amount="10.00",
        text="Spende Erika Muster",
    )


def _lock(org, until=DAY):
    Organization.objects.filter(pk=org.pk).update(finance_locked_until=until)
    org.refresh_from_db()


def _fails(fn) -> bool:
    try:
        with transaction.atomic():
            fn()
    except IntegrityError:
        return True
    return False


def test_datenbank_weist_neue_und_verschobene_buchungen_ab(orgs):
    org = orgs["a"]
    with tenant_context(org.pk):
        alt = _booking(org, DAY - datetime.timedelta(days=10), 1)
        offen = _booking(org, DAY + datetime.timedelta(days=10), 2)
    _lock(org)
    with app_role(), tenant_context(org.pk):
        assert _fails(lambda: _booking(org, DAY, 3))
        assert not _fails(lambda: _booking(org, DAY + datetime.timedelta(days=1), 4))

        def verschieben():
            Booking.objects.filter(pk=offen.pk).update(date=DAY - datetime.timedelta(days=1))

        assert _fails(verschieben)
        assert _fails(lambda: Booking.objects.filter(pk=alt.pk).update(amount="11.00"))
        assert _fails(lambda: Booking.objects.filter(pk=alt.pk).delete())

        # Text bleibt änderbar (Anonymisieren, Schlüsselwechsel; verschlüsselt, also über save)
        def anonymisieren():
            b = Booking.objects.get(pk=alt.pk)
            b.text = "Spende"
            b.save(update_fields=["text"])

        assert not _fails(anonymisieren)


def test_oberflaeche_nennt_den_grund(api, orgs, board_a):
    org = orgs["a"]
    org.enabled_modules = sorted({*(org.enabled_modules or []), "finance"})
    org.save()
    from finance.models import Category

    with tenant_context(org.pk):
        account = _account(org)
        category = Category.objects.create(organization=org, name="Spenden", kind="income")
    _lock(org)
    resp = api(board_a).post(
        f"/api/orgs/{org.pk}/finance/bookings/",
        {
            "date": DAY.isoformat(),
            "kind": "income",
            "amount": "5.00",
            "text": "Nachtrag",
            "account": account.pk,
            "category": category.pk,
        },
        content_type=JSON,
    )
    assert resp.status_code == 400, resp.content
    assert "festgeschrieben" in str(resp.json())


def test_datenuebernahme_mit_festschreibung(api, orgs, club_c, board_c):
    from .factories import give_role, make_user

    club = club_c["club"]
    _lock(club, datetime.date(2024, 12, 31))  # die Buchung vom 01.02.2024 ist festgeschrieben
    content, _ = export(api(board_c), f"/api/orgs/{club.pk}")
    admin = make_user("plattform-pub08@example.org")
    give_role(admin, Organization.platform())
    c = api(admin)
    job = upload(c, "/api/platform", content)
    c.post(f"/api/platform/datatransfer/imports/{job['id']}/run/")
    job = c.get(f"/api/platform/datatransfer/imports/{job['id']}/").json()
    assert job["status"] == "done", job
    with rls_bypass():
        new = Organization.objects.get(pk=job["result_organization"]["id"])
        assert new.finance_locked_until == datetime.date(2024, 12, 31)
        assert (
            Booking.objects.filter(organization=new).count()
            == Booking.objects.filter(organization=club).count()
        )
