"""Wer die App verbinden darf: Zugang zum Mitgliederbereich oder etwas zu verwalten.

Konten mit Rolle, aber ohne Mitgliederbereich (z. B. Kassierer in einer Einheit, die nur das
Kassenbuch nutzt, oder ein Geschäftsführer ohne Mitgliedschaft) verbinden die App für die
Verwaltung. Reine Plattformkonten ohne Rolle in einer Einheit haben in der App nichts zu tun.
"""

from __future__ import annotations

from django.utils.translation import gettext_noop

from core.tenancy import user_view

# Übersetzt wird beim Melden (gettext(NOTHING_FOR_APP))
NOTHING_FOR_APP = gettext_noop(
    "Für dieses Konto gibt es in der App nichts: Es hat weder Zugang zum Mitgliederbereich "
    "noch etwas zu verwalten."
)


def manages_in_app(user) -> bool:
    """Hat das Konto in der App etwas zu verwalten (Einheit oder Untereinheit)?"""
    from .admin_api import admin_departments, admin_units

    if user is None or not user.is_active:
        return False
    # Immer in der Sicht genau dieses Kontos: beim Verbinden ist noch niemand angemeldet,
    # und beim Abmelden von Geräten ist der Aufrufer ein anderer (Gesamtaudit 31.10.b)
    with user_view(user.pk):
        return bool(admin_units(user)) or bool(admin_departments(user))


def may_connect(user) -> bool:
    from portal import services as portal_services

    return bool(portal_services.portal_accesses(user)) or manages_in_app(user)
