"""Hinweis-Mails zu API-Zugängen (docs/api.md): neuer Zugang, neuer Schlüssel, Ablauf naht.

Ein API-Zugang gibt Daten der Einheit an ein fremdes Programm. Damit ein erschlichener oder
vergessener Zugang auffällt, erfahren es alle, die API-Zugänge verwalten dürfen. Eine Mail
verhindert die Änderung nie.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext, gettext_noop

from core.i18n import date_text, user_language

logger = logging.getLogger(__name__)

KIND = "sicherheit"
LINK = "/einstellungen/api"

CREATED = (
    gettext_noop("Neuer API-Zugang für „{unit}“"),
    gettext_noop(
        "Hallo,\n\n"
        "{actor} hat in HUBIplan den API-Zugang „{name}“ für „{unit}“ angelegt. Ein fremdes "
        "Programm kann damit diese Bereiche nutzen: {scopes}.\n\n"
        "Gültig bis: {until}\n\n"
        "Ist das so gewollt, ist nichts zu tun. Sonst den Zugang unter Einstellungen › "
        "API-Zugänge löschen: {link}\n"
    ),
)
ROTATED = (
    gettext_noop("Neuer Schlüssel für den API-Zugang „{name}“"),
    gettext_noop(
        "Hallo,\n\n"
        "{actor} hat für den API-Zugang „{name}“ von „{unit}“ einen neuen Schlüssel erzeugt. "
        "Der bisherige Schlüssel gilt noch sieben Tage.\n\n"
        "Ist das so gewollt, ist nichts zu tun. Sonst den Zugang unter Einstellungen › "
        "API-Zugänge löschen: {link}\n"
    ),
)
EXPIRING = (
    gettext_noop("API-Zugang „{name}“ läuft bald ab"),
    gettext_noop(
        "Hallo,\n\n"
        "der API-Zugang „{name}“ von „{unit}“ gilt nur noch bis {until}. Danach bekommt das "
        "angebundene Programm keine Daten mehr.\n\n"
        "Wird der Zugang weiter gebraucht, unter Einstellungen › API-Zugänge verlängern: "
        "{link}\n"
        "Wird er nicht mehr gebraucht, ist nichts zu tun.\n"
    ),
)
PERSONAL = (
    gettext_noop("API-Zugang „{name}“ gibt jetzt Personendaten heraus"),
    gettext_noop(
        "Hallo,\n\n"
        "{actor} hat am API-Zugang „{name}“ von „{unit}“ Bereiche mit Personendaten "
        "eingeschaltet: {scopes}.\n\n"
        "Empfänger: {partner}\n"
        "Rechtsgrundlage: {basis}\n\n"
        "Ist das so gewollt, ist nichts zu tun. Sonst den Zugang unter Einstellungen › "
        "API-Zugänge ändern oder löschen: {link}\n"
    ),
)
WRITES = (
    gettext_noop("API-Zugang „{name}“ darf jetzt schreiben"),
    gettext_noop(
        "Hallo,\n\n"
        "{actor} hat am API-Zugang „{name}“ von „{unit}“ Bereiche eingeschaltet, mit denen ein "
        "fremdes Programm Daten anlegen oder ändern kann: {scopes}.\n\n"
        "Was das Programm schreibt, steht im Änderungsprotokoll unter „API-Zugang {name}“.\n\n"
        "Ist das so gewollt, ist nichts zu tun. Sonst den Zugang unter Einstellungen › "
        "API-Zugänge ändern oder löschen: {link}\n"
    ),
)
WEBHOOK_PAUSED = (
    gettext_noop("Benachrichtigungen des API-Zugangs „{name}“ ruhen"),
    gettext_noop(
        "Hallo,\n\n"
        "die Adresse für Benachrichtigungen des API-Zugangs „{name}“ von „{unit}“ war sieben "
        "Tage lang nicht erreichbar. HUBIplan sendet dorthin vorerst nichts mehr; der Zugang "
        "selbst gilt weiter.\n\n"
        "Letzter Fehler: {error}\n\n"
        "Ist die Adresse wieder erreichbar, die Benachrichtigungen unter Einstellungen › "
        "API-Zugänge wieder einschalten: {link}\n"
    ),
)


def managers(org) -> list:
    """Konten, die in der Einheit API-Zugänge verwalten dürfen."""
    from access.catalog import API_MANAGE, effective
    from access.models import RoleAssignment
    from core.tenancy import rls_bypass

    users = {}
    with rls_bypass():
        for a in (
            RoleAssignment.objects.active().filter(organization=org).select_related("role", "user")
        ):
            if a.user_id and a.user.is_active and API_MANAGE in effective(a.role.permissions):
                users[a.user_id] = a.user
    return list(users.values())


def _send(org, message: tuple[str, str], /, **values) -> None:
    from django.utils import translation

    from outbox.mail import send

    subject, body = message
    by_language: dict[str, list[str]] = {}
    for user in managers(org):
        if user.email:
            by_language.setdefault(user_language(user), []).append(user.email)
    for language, emails in by_language.items():
        with translation.override(language):
            filled = {k: v() if callable(v) else v for k, v in values.items()}
            filled["link"] = f"{settings.FRONTEND_URL}{LINK}"
            try:
                send(
                    sorted(emails),
                    gettext(subject).format(**filled),
                    gettext(body).format(**filled),
                    organization=org,
                    kind=KIND,
                    fail_silently=True,
                    language=language,
                )
            except Exception:  # noqa: BLE001
                logger.exception("Hinweis-Mail zum API-Zugang konnte nicht gesendet werden")


def _values(access, actor=None) -> dict:
    from . import scopes

    codes = list(access.scopes or [])
    until = access.expires_at
    return {
        "name": access.name,
        "unit": access.scope_unit.name,
        "actor": (actor.get_full_name() or actor.email) if actor is not None else "",
        "scopes": lambda: ", ".join(s["label"] for s in scopes.describe(codes)) or "–",
        "until": lambda: date_text(until),
    }


def created(access, actor) -> None:
    org, values = access.organization, _values(access, actor)
    transaction.on_commit(lambda: _send(org, CREATED, **values))


def rotated(access, actor) -> None:
    org, values = access.organization, _values(access, actor)
    transaction.on_commit(lambda: _send(org, ROTATED, **values))


def expiring(access) -> None:
    _send(access.organization, EXPIRING, **_values(access))


def personal(access, actor) -> None:
    """Der Zugang gibt neu Personendaten heraus (oder an einen anderen Empfänger)."""
    org, values = access.organization, _values(access, actor)
    values["partner"] = access.partner.name if access.partner_id else "–"
    values["basis"] = lambda: str(access.get_legal_basis_display()) or "–"
    transaction.on_commit(lambda: _send(org, PERSONAL, **values))


def writes(access, actor) -> None:
    """Der Zugang darf neu schreiben (oder mehr als bisher)."""
    from . import scopes

    org, values = access.organization, _values(access, actor)
    codes = [c for c in (access.scopes or []) if scopes.SCOPE_BY_CODE[c].write]
    values["scopes"] = lambda: ", ".join(s["label"] for s in scopes.describe(codes)) or "–"
    transaction.on_commit(lambda: _send(org, WRITES, **values))


def webhook_paused(access) -> None:
    values = _values(access)
    values["error"] = access.webhook_last_error or "–"
    _send(access.organization, WEBHOOK_PAUSED, **values)
