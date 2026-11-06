"""E-Mail an die anfragende Person, wenn die Verwaltung entscheidet (über den Postausgang)."""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

SUBJECTS = {
    "confirmed": "Buchung bestätigt: {title}",
    "rejected": "Buchung abgelehnt: {title}",
    "cancelled": "Buchung storniert: {title}",
}


def decision(booking, actor) -> None:
    """Nach dem Speichern: Hinweis an den Buchenden, wenn jemand anderes entschieden hat."""
    user = booking.booked_by
    if user is None or user.pk == actor.pk or booking.status not in SUBJECTS or not user.email:
        return
    item_title, title, starts = booking.item.title, booking.title, booking.starts_at
    org, status = booking.organization, booking.status

    def send():
        from core.i18n import language_of, user_language
        from outbox import mail

        with language_of(user):
            subject = _(SUBJECTS[status]).format(title=title)
            when = timezone.localtime(starts).strftime("%d.%m.%Y %H:%M")
            body = "\n".join(
                [
                    subject,
                    f"{item_title} · {when}",
                    f"{settings.FRONTEND_URL}/mein-bereich/belegung",
                ]
            )
            mail.send(
                user.email,
                subject,
                body,
                organization=org,
                kind="buchung",
                language=user_language(user),
                fail_silently=True,
            )

    transaction.on_commit(send)
