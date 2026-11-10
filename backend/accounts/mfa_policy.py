"""Pflicht zur Zwei-Faktor-Anmeldung für heikle Rechte (Gesamtaudit 31.10.b, Frage 1).

Wer Plattform, Rollen, vollständige Exporte oder die Kasse (schreibend) verwaltet, alle
Mitglieder lesen darf oder Protokoll und Postausgang sieht (Gesamtaudit 05.11. F-02),
braucht eine eingerichtete Zwei-Faktor-Anmeldung. Ab dem ersten Mal, dass ein Konto solche Rechte
hat, bleiben ``GRACE_DAYS`` Tage zum Einrichten; danach ruhen genau diese Rechte, bis die
Zwei-Faktor-Anmeldung eingerichtet ist. Alles andere geht weiter, auch „Mein Konto“.

Für die Plattform-Verwaltung gibt es keine Frist (Gesamtaudit 10.11., Frage 1): Ohne
zweiten Faktor ruhen ihre Rechte sofort. Heikle Einzelaktionen verlangen zusätzlich eine
frische Bestätigung (``accounts/step_up.py``).
"""

from __future__ import annotations

import datetime

from django.conf import settings
from django.utils import timezone

from access import catalog

GRACE_DAYS = 14

# Rechte, die einen zweiten Faktor verlangen (Plattform: alle ihre Rechte)
MFA_PERMISSIONS = frozenset(
    {
        catalog.ROLES_MANAGE,
        catalog.DEPT_ROLES_MANAGE,
        catalog.DATA_EXPORT,
        catalog.FINANCE_EDIT,
        catalog.PLATFORM_MANAGE,
        catalog.CLUBS_MANAGE,
        # dieselben Rechte als Bereiche (konzepte/berechtigungen.md)
        catalog.ROLES_EDIT,
        catalog.EXPORT_FULL,
        catalog.UNITS_EDIT,
        catalog.PLATFORM_EDIT,
        # Lesen aller Mitglieder, Protokoll und Postausgang (Gesamtaudit 05.11. F-02);
        # Rechte nur für eine Abteilung bleiben ohne Pflicht
        catalog.MEMBERS_VIEW,
        catalog.MEMBERS_EDIT,
        catalog.AUDIT_VIEW,
    }
)


def has_mfa(user) -> bool:
    if user is None:
        return False
    cached = getattr(user, "_has_mfa", None)
    if cached is None:
        from allauth.mfa.models import Authenticator

        cached = Authenticator.objects.filter(user_id=user.pk).exists()
        user._has_mfa = cached
    return cached


def deadline(user) -> datetime.datetime | None:
    """Bis wann das Konto die Zwei-Faktor-Anmeldung einrichten muss (None: keine Pflicht)."""
    return getattr(user, "mfa_required_by", None)


def gate(user, perms: set[str], *, platform: bool = False) -> set[str]:
    """Rechte nach der Übergangsfrist ohne zweiten Faktor abziehen."""
    needed = perms if platform else perms & MFA_PERMISSIONS
    if not needed or not getattr(user, "pk", None) or has_mfa(user):
        return perms
    if platform and not getattr(settings, "MFA_PLATFORM_GRACE", False):
        return set()
    now = timezone.now()
    due = user.mfa_required_by
    if due is None:
        from changes.tracking import suppress

        from .models import User

        due = now + datetime.timedelta(days=GRACE_DAYS)
        # Nur setzen, wenn noch leer (zwei Anfragen gleichzeitig: die erste gewinnt). Kein
        # Teil des Änderungspakets der Anfrage (sonst wäre „Rückgängig“ gesperrt).
        with suppress():
            User.objects.filter(pk=user.pk, mfa_required_by__isnull=True).update(
                mfa_required_by=due
            )
        user.mfa_required_by = (
            User.objects.filter(pk=user.pk).values_list("mfa_required_by", flat=True).first() or due
        )
        due = user.mfa_required_by
    if now <= due:
        return perms
    return set() if platform else perms - MFA_PERMISSIONS


def status(user) -> dict:
    """Für die Oberfläche: Pflicht offen? (nur Konten ohne zweiten Faktor)."""
    if has_mfa(user):
        return {}
    result: dict = {}
    from access.permissions import platform_rights_waiting

    if platform_rights_waiting(user):
        result["mfa_platform"] = True
    due = deadline(user)
    if due is not None:
        result.update(mfa_required_by=due.isoformat(), mfa_overdue=timezone.now() > due)
    return result
