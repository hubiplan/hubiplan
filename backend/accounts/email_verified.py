"""Anmelde-E-Mail als bestätigt vermerken, sobald ein Link an sie genutzt wurde (#599).

HUBIplan verschickt keine eigene Bestätigungsmail (``ACCOUNT_EMAIL_VERIFICATION = "none"``),
allauth verweigert die Zwei-Faktor-Einrichtung aber, solange das Konto eine unbestätigte
Adresszeile (``EmailAddress``) hat. Wer einen Einladungs-, Passwort- oder Anmeldelink an
die Anmelde-E-Mail nutzt, hat Zugriff auf das Postfach; damit gilt die Adresse als bestätigt.
"""

from __future__ import annotations


def mark_email_verified(user) -> None:
    from allauth.account.models import EmailAddress

    if user is None or user.pk is None or not user.email:
        return
    EmailAddress.objects.filter(user_id=user.pk, email__iexact=user.email, verified=False).update(
        verified=True
    )


def _on_password_reset(sender, request=None, user=None, **kwargs) -> None:
    mark_email_verified(user)


def connect() -> None:
    from allauth.account.signals import password_reset

    password_reset.connect(_on_password_reset, dispatch_uid="accounts.email_verified")
