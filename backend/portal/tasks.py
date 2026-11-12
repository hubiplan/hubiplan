"""Regelmäßige Aufgaben des Mitgliederbereichs."""

from __future__ import annotations

import datetime

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from core.tenancy import rls_bypass

# Benutzte oder abgelaufene Anmeldelinks bleiben so lange zur Nachverfolgung stehen
KEEP_DAYS = 30
# 3 Links je Empfänger und Stunde (Gesamtaudit 11.11., Fachfrage 3)
RECIPIENT_RATE = (3, 60 * 60)


@shared_task
def send_requested_link(email: str) -> bool:
    """Selbst angeforderten Anmeldelink erzeugen und senden (Gesamtaudit 11.11., H-09).

    Läuft im Hintergrund, damit die Antwort der Anfrage für jede Adresse gleich lange dauert.
    Sendet nur an Konten mit Mitgliederzugang, die sich per Link anmelden dürfen."""
    from django.utils.translation import gettext

    from accounts.models import User
    from core.i18n import language_of, user_language
    from core.ratelimit import too_many
    from core.tenancy import set_rls
    from organizations.platform_public import instance_name
    from outbox import mail

    from . import services

    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        return False
    set_rls(None, user.pk)
    try:
        if not (
            services.portal_accesses(user)
            and services.link_login_allowed(user)
            # höchstens 3 Links je Empfänger und Stunde
            and not too_many(f"login-link:to:{user.pk}", *RECIPIENT_RATE)
        ):
            return False
        url = services.create_login_link(user)
        with language_of(user):
            subject = gettext("Ihr Anmeldelink für {instanz}").format(instanz=instance_name())
            body = (
                gettext("Guten Tag,")
                + "\n\n"
                + gettext(
                    "mit diesem Link melden Sie sich im Mitgliederbereich an "
                    "(gültig eine Stunde, einmal nutzbar; ältere Links gelten nicht mehr):"
                )
                + f"\n\n{url}\n\n"
                + gettext(
                    "Falls Sie den Link nicht angefordert haben, können Sie diese Mail ignorieren."
                )
                + "\n"
            )
        return mail.send(
            user.email,
            subject,
            body,
            kind="anmeldelink",
            fail_silently=True,
            language=user_language(user),
        )
    finally:
        set_rls(None, None)


@shared_task
def purge_login_links() -> int:
    """Alte Anmeldelinks löschen (Gesamtaudit 11.11., H-07).

    Offene Links bleiben; benutzte und abgelaufene verschwinden nach 30 Tagen.
    """
    from .models import LoginLink

    cutoff = timezone.now() - datetime.timedelta(days=KEEP_DAYS)
    with rls_bypass():
        deleted, _ = LoginLink.objects.filter(
            Q(used_at__lt=cutoff) | Q(expires_at__lt=cutoff)
        ).delete()
    return deleted
