"""Mitgliedsakte „Auf einen Blick“ (S-03 A3): Zusammenfassung nur mit passendem Recht."""

import datetime
from decimal import Decimal

from django.utils import timezone

from core.tenancy import tenant_context

from .factories import give_role, make_member, make_user


def _billing_on(org):
    org.enabled_modules = sorted({*org.enabled_modules, "billing"})
    org.save()


def _invoice(org, membership, *, total, paid="0", due_in=14, status="open"):
    from billing.models import Invoice

    with tenant_context(org.pk):
        return Invoice.objects.create(
            organization=org,
            membership=membership,
            recipient_kind="member",
            recipient_name="Erika Muster",
            date=timezone.localdate(),
            due_date=timezone.localdate() + datetime.timedelta(days=due_in),
            status=status,
            total=Decimal(total),
            paid=Decimal(paid),
        )


def _summary(client, org, membership):
    res = client.get(f"/api/orgs/{org.pk}/members/{membership.pk}/")
    assert res.status_code == 200
    return res.json()["summary"]


def test_offene_rechnungen_mit_summe_und_ueberfaelligkeit(api, orgs, board_a):
    org = orgs["a"]
    _billing_on(org)
    erika = make_member(org, "Erika", "Muster")
    _invoice(org, erika, total="40.00", paid="10.00")
    _invoice(org, erika, total="25.00", due_in=-3)
    _invoice(org, erika, total="99.00", status="paid")
    _invoice(org, erika, total="50.00", status="draft")
    summary = _summary(api(board_a), org, erika)
    assert summary["invoices"] == {"open": 2, "open_amount": "55.00", "overdue": 1}


def test_ohne_beitragsrecht_oder_modul_keine_rechnungen(api, orgs):
    org = orgs["a"]
    org.enabled_modules = [m for m in org.enabled_modules if m != "billing"]
    org.save()
    erika = make_member(org, "Erika", "Muster")
    leser = make_user("leser@example.org")
    give_role(leser, org, permissions=["members.view"], name="Mitglieder lesen")
    # Modul aus: auch der Vorstand sieht nichts
    vorstand = make_user("vorstand@example.org")
    give_role(vorstand, org)
    assert _summary(api(vorstand), org, erika)["invoices"] is None
    _billing_on(org)
    _invoice(org, erika, total="40.00")
    summary = _summary(api(leser), org, erika)
    assert summary["invoices"] is None
    assert summary["account"] is None


def test_konto_nur_mit_zugangsrecht(api, orgs, board_a):
    from devices.models import Device
    from portal.models import PortalAccess

    org = orgs["a"]
    erika = make_member(org, "Erika", "Muster")
    assert _summary(api(board_a), org, erika)["account"] == {
        "has_access": False,
        "last_login": None,
        "mfa": False,
        "app": False,
    }
    konto = make_user("erika.konto@example.org")
    with tenant_context(org.pk):
        PortalAccess.objects.create(organization=org, membership=erika, user=konto)
    Device.objects.create(user=konto, name="Telefon", token_hash="e" * 64)
    account = _summary(api(board_a), org, erika)["account"]
    assert account["has_access"] is True
    assert account["app"] is True
    assert account["mfa"] is False


def test_speichern_liefert_keine_zusammenfassung(api, orgs, board_a):
    org = orgs["a"]
    erika = make_member(org, "Erika", "Muster")
    res = api(board_a).patch(
        f"/api/orgs/{org.pk}/members/{erika.pk}/",
        {"phone": "0123 456"},
        content_type="application/json",
    )
    assert res.status_code == 200
    assert "summary" not in res.json()
