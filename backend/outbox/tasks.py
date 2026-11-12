"""Hintergrund-Jobs des Postausgangs."""

import logging

from celery import shared_task

from .purge import purge_sent

logger = logging.getLogger(__name__)


@shared_task
def purge_sent_mails() -> int:
    """Täglich: Text und Anhänge zugestellter Mails nach Ablauf der Frist leeren."""
    count = purge_sent()
    logger.info("Postausgang: %s Mails geleert", count)
    return count


def _message_data(message) -> dict:
    return {
        "subject": message.subject,
        "body": message.body,
        "from_email": message.from_email,
        "to": list(message.to),
        "cc": list(message.cc),
        "bcc": list(message.bcc),
        "reply_to": list(message.reply_to),
        "headers": dict(message.extra_headers),
        "alternatives": [
            [content, mimetype] for content, mimetype in getattr(message, "alternatives", [])
        ],
    }


@shared_task
def send_message(data: dict) -> int:
    """Eine vorbereitete Mail (ohne Anhänge) senden, siehe ``deliver``."""
    from django.core.mail import EmailMultiAlternatives

    message = EmailMultiAlternatives(
        subject=data["subject"],
        body=data["body"],
        from_email=data["from_email"],
        to=data["to"],
        cc=data["cc"],
        bcc=data["bcc"],
        reply_to=data["reply_to"],
        headers=data["headers"],
    )
    for content, mimetype in data["alternatives"]:
        message.attach_alternative(content, mimetype)
    return message.send()


def deliver(message) -> None:
    """Mail im Hintergrund senden, wenn ``MAIL_IN_BACKGROUND`` gilt (Gesamtaudit 11.11., H-09).

    Für Mails, deren Versanddauer nicht verraten soll, ob es ein Konto gibt (Anmeldelink,
    „Passwort vergessen“). Ohne Hintergrund (Tests, Entwicklung) sofort."""
    from django.conf import settings
    from django.db import transaction

    if not getattr(settings, "MAIL_IN_BACKGROUND", False) or message.attachments:
        message.send()
        return
    data = _message_data(message)
    transaction.on_commit(lambda: send_message.delay(data), robust=True)
