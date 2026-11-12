"""Pflicht zur Zwei-Faktor-Anmeldung für jedes Verwaltungsrecht (Gesamtaudit 11.11., Frage 1).

Wer in einer Einheit irgendein Recht hat (Vorstand, Kasse, Schriftführung, Abteilungsrolle …),
braucht eine eingerichtete Zwei-Faktor-Anmeldung. Nur der eigene Mitgliederbereich kommt ohne
aus. Ab dem ersten Mal, dass ein Konto solche Rechte hat, bleiben ``GRACE_DAYS`` Tage zum
Einrichten. Schon in dieser Frist ruhen die folgenreichsten Rechte (Rundschreiben, Exporte,
Buchen in der Kasse, ``IMMEDIATE_PERMISSIONS``); danach ruhen alle Rechte, bis die
Zwei-Faktor-Anmeldung eingerichtet ist. „Mein Konto“ geht weiter.

Für die Plattform-Verwaltung gibt es keine Frist (Gesamtaudit 10.11., Frage 1): Ohne
zweiten Faktor ruhen ihre Rechte sofort. Heikle Einzelaktionen verlangen zusätzlich eine
frische Bestätigung (``accounts/step_up.py``).
"""

from __future__ import annotations

import datetime

from django.conf import settings
from django.utils import timezone

from access import catalog

GRACE_DAYS = 3

# Rechte, die schon in der Frist ruhen: Ein Rundschreiben im Namen des Vereins, ein Export
# aller Daten oder eine Buchung sind für Betrüger am wertvollsten.
IMMEDIATE_PERMISSIONS = frozenset(
    {
        catalog.CIRCULARS_SEND,
        catalog.CIRCULARS_EDIT,
        catalog.DEPT_CIRCULARS_SEND,
        catalog.DATA_EXPORT,
        catalog.EXPORT_FULL,
        catalog.EXPORT_RUN,
        catalog.EXPORT_LISTS,
        catalog.DEPT_EXPORT,
        catalog.FINANCE_EDIT,
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
    """Rechte ohne zweiten Faktor abziehen: in der Frist die folgenreichsten, danach alle."""
    if not perms or not getattr(user, "pk", None) or has_mfa(user):
        return perms
    if platform and not getattr(settings, "MFA_PLATFORM_GRACE", False):
        return set()
    now = timezone.now()
    due = user.mfa_required_by
    if due is None:
        from changes.tracking import suppress

        from .models import User

        # Tests mit verstellter Uhr setzen MFA_GRACE_DAYS hoch (tests/conftest.py)
        due = now + datetime.timedelta(days=getattr(settings, "MFA_GRACE_DAYS", GRACE_DAYS))
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
    if now > due:
        return set()
    if getattr(settings, "MFA_IMMEDIATE", True):
        return perms - IMMEDIATE_PERMISSIONS
    return perms


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
