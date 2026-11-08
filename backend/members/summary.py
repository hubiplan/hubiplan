"""Kurzüberblick „Auf einen Blick“ in der Mitgliedsakte (Konzept S-03, Schritt A3).

Jeder Teil steht nur drin, wenn das Modul an ist und die Person das Recht für den
zugehörigen Reiter hat; sonst ist er ``None``. So verrät die Akte nichts, was der
Reiter selbst nicht zeigen würde.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import F, Sum
from django.db.models.functions import Greatest
from django.utils import timezone

from access.catalog import BILLING_VIEW, LOGINS_VIEW

from .models import Membership


def member_summary(membership: Membership, org, permissions: set[str]) -> dict:
    return {
        "invoices": _invoices(membership, org, permissions),
        "account": _account(membership, permissions),
    }


def _invoices(membership: Membership, org, permissions: set[str]) -> dict | None:
    if "billing" not in (org.enabled_modules or []) or BILLING_VIEW not in permissions:
        return None
    from billing.models import Invoice

    # Nur Rechnungen an das Mitglied selbst; Sammelrechnungen einer Untereinheit zahlt diese
    open_qs = Invoice.objects.filter(
        organization=org, membership=membership, status=Invoice.Status.OPEN
    )
    rest = Greatest(F("total") - F("paid") - F("prepaid"), Decimal("0.00"))
    total = open_qs.aggregate(s=Sum(rest))["s"] or Decimal("0.00")
    return {
        "open": open_qs.count(),
        "open_amount": f"{total:.2f}",
        "overdue": open_qs.filter(due_date__lt=timezone.localdate()).count(),
    }


def _account(membership: Membership, permissions: set[str]) -> dict | None:
    # Organisationen haben Zugänge je Ansprechpartner; die stehen im Reiter selbst
    if LOGINS_VIEW not in permissions or membership.person.is_organization:
        return None
    from accounts.mfa_policy import has_mfa
    from devices.models import Device
    from portal.models import PortalAccess

    access = (
        PortalAccess.objects.filter(membership=membership, contact_person=None)
        .select_related("user")
        .first()
    )
    if access is None:
        return {"has_access": False, "last_login": None, "mfa": False, "app": False}
    user = access.user
    return {
        "has_access": True,
        "last_login": user.last_login,
        "mfa": has_mfa(user),
        "app": Device.objects.filter(user=user, revoked_at__isnull=True).exists(),
    }
