"""Hinweis-Mail bei jeder neuen Verbindung eines KI-Assistenten (docs/mcp.md, Stufe 1a).

Wer eine Zustimmung erschleicht, hat bis zu 30 Tage Zugang. Damit das auffällt, bekommt
das Konto bei jeder neuen Verbindung eine Mail. Eine Mail verhindert die Verbindung nie.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from core.i18n import datetime_text, language_of, user_language

logger = logging.getLogger(__name__)

KIND = "sicherheit"


def _send(user, client_name: str, unit_name: str) -> None:
    if not user.email:
        return
    from outbox.mail import send

    with language_of(user):
        subject = _("KI-Assistent mit deinem Zugang verbunden")
        body = _(
            "Hallo {name},\n\n"
            "der KI-Assistent „{client}“ wurde mit deinem HUBIplan-Zugang für „{unit}“ "
            "verbunden. Er darf dort nur, was du darfst, und ändert die Webseite nur als "
            "Entwurf.\n\n"
            "Zeit: {when} Uhr\n\n"
            "Warst du das, ist nichts zu tun. Sonst bitte sofort im Browser unter Mein Konto › "
            "App & andere Instanzen die Verbindung trennen und dein Passwort ändern: {link}\n"
        ).format(
            name=user.get_full_name() or user.email,
            client=client_name,
            unit=unit_name,
            when=datetime_text(timezone.localtime()),
            link=f"{settings.FRONTEND_URL}/mein-konto/app",
        )
    try:
        send(
            [user.email],
            subject,
            body,
            kind=KIND,
            fail_silently=True,
            language=user_language(user),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Hinweis-Mail zum KI-Assistenten konnte nicht gesendet werden")


def connected(grant) -> None:
    user, client, unit = grant.user, grant.client.name, grant.organization.name
    transaction.on_commit(lambda: _send(user, client, unit))
