"""Anmeldung mit Passkey (WebAuthn), Stufe P1 aus konzepte/passkey-anmeldung.md.

Einrichten, Anmelden ohne Passwort, Passkey als zweiter Faktor und Bestätigen laufen über
allauth (``/_allauth/browser/v1/…/webauthn``). Hier liegt nur, was HUBIplan dazu braucht:

* Ein Passkey gilt immer für genau eine Adresse (WebAuthn „Relying Party ID“). Läuft die
  Instanz unter mehreren Adressen, hat jede ihre eigenen Passkeys. Für die Übersicht in
  „Mein Konto“ wird aus der gespeicherten Prüfsumme der Adresse wieder die Adresse.
* Der Name, den Handy und Passwortmanager zeigen, ist der der Einheit dieser Adresse.
* ``HUBIPLAN_PASSKEYS=0`` in der ``.env`` schaltet Passkeys ab.

Ein Passkey zählt als Zwei-Faktor-Anmeldung: allauth verlangt beim Anmelden ohne Passwort
die Geräte-Entsperrung (Fingerabdruck, Gesicht oder PIN) und vermerkt die Anmeldung als
``mfa`` (``amr`` enthält dann ``mfa``, siehe ``peering.sso.session_auth``).
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


def enabled() -> bool:
    return "webauthn" in getattr(settings, "MFA_SUPPORTED_TYPES", [])


def current_host(request) -> str:
    from organizations.addresses import normalize_host

    try:
        return normalize_host(request.get_host())
    except Exception:  # noqa: BLE001 – unerlaubter Host: keine Relying Party
        return ""


def rp_name(request) -> str:
    """Name für Handy und Passwortmanager: Einheit der Adresse, sonst Plattform."""
    from organizations.addresses import request_unit
    from organizations.models import Organization

    unit = request_unit(request) if request is not None else None
    if unit is None:
        unit = Organization.objects.filter(type=Organization.Type.PLATFORM).first()
    name = unit.display_name if unit is not None else ""
    return name or getattr(settings, "MFA_TOTP_ISSUER", "") or "HUBIplan"


def known_hosts(request=None) -> set[str]:
    """Adressen, unter denen diese Instanz läuft (für die Anzeige je Passkey)."""
    from urllib.parse import urlsplit

    from organizations.addresses import normalize_host
    from organizations.models import InstanceAddress

    hosts = {normalize_host(h) for h in getattr(settings, "FIXED_ALLOWED_HOSTS", [])}
    hosts |= {normalize_host(h) for h in InstanceAddress.objects.values_list("hostname", flat=True)}
    hosts.add(normalize_host(urlsplit(getattr(settings, "FRONTEND_URL", "")).hostname or ""))
    if request is not None:
        hosts.add(current_host(request))
    return {h for h in hosts if h and "*" not in h and not h.startswith(".")}


def _hash(host: str) -> bytes:
    return hashlib.sha256(host.encode()).digest()


def rp_hash(authenticator) -> bytes:
    try:
        return bytes(authenticator.wrap().authenticator_data.rp_id_hash)
    except Exception:  # noqa: BLE001 – beschädigter Eintrag: keiner Adresse zuordnen
        return b""


def passkeys(user):
    from allauth.mfa.models import Authenticator

    return Authenticator.objects.filter(user_id=user.pk, type=Authenticator.Type.WEBAUTHN)


def usable_here(user, request) -> bool:
    """Hat das Konto einen Passkey für die aufgerufene Adresse?"""
    if not enabled() or not getattr(user, "pk", None):
        return False
    host = current_host(request)
    if not host:
        return False
    wanted = _hash(host)
    return any(rp_hash(item) == wanted for item in passkeys(user))


class PasskeyListView(APIView):
    """GET: eigene Passkeys mit der Adresse, für die sie gelten.

    Einrichten, Umbenennen und Löschen laufen über allauth
    (``/_allauth/browser/v1/account/authenticators/webauthn``)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        here = current_host(request._request)
        by_hash = {_hash(host): host for host in known_hosts(request._request)}
        items = []
        for item in passkeys(request.user).order_by("created_at", "pk"):
            wrapped = item.wrap()
            digest = rp_hash(item)
            items.append(
                {
                    "id": item.pk,
                    "name": wrapped.name,
                    "host": by_hash.get(digest, ""),
                    "here": bool(here) and digest == _hash(here),
                    "passwordless": bool(wrapped.is_passwordless),
                    "created_at": item.created_at.isoformat(),
                    "last_used_at": item.last_used_at.isoformat() if item.last_used_at else None,
                }
            )
        return Response({"enabled": enabled(), "host": here, "passkeys": items})


# --- Hinweis-Mails (Art „Sicherheit“) ---


def _mail(user, subject: str, text: str, name: str, host: str) -> None:
    from django.db import transaction
    from django.utils import timezone
    from django.utils.translation import gettext as _

    from core.i18n import datetime_text, language_of, user_language

    if not getattr(user, "email", ""):
        return

    def send() -> None:
        import logging

        from outbox.mail import send as send_mail

        when = timezone.localtime()
        with language_of(user):
            body = _(
                "Hallo {name},\n\n{text}\n\nZeit: {when} Uhr\n\n"
                "Warst du das, ist nichts zu tun. Sonst bitte sofort im Browser unter "
                "Mein Konto › Anmeldung & Sicherheit die Passkeys prüfen und dein Passwort "
                "ändern: {link}\n"
            ).format(
                name=user.get_full_name() or user.email,
                text=_(text).format(name=name, host=host or "–"),
                when=datetime_text(when),
                link=f"{settings.FRONTEND_URL}/mein-konto/anmeldung",
            )
            title = _(subject)
        try:
            send_mail(
                [user.email],
                title,
                body,
                kind="sicherheit",
                fail_silently=True,
                language=user_language(user),
            )
        except Exception:  # noqa: BLE001 – eine Mail darf die Änderung nie verhindern
            logging.getLogger(__name__).exception("Passkey-Hinweis nicht gesendet")

    transaction.on_commit(send)


def _on_added(sender, request=None, user=None, authenticator=None, **kwargs):
    from allauth.mfa.models import Authenticator
    from django.utils.translation import gettext_noop

    if authenticator is None or authenticator.type != Authenticator.Type.WEBAUTHN:
        return
    _mail(
        user,
        gettext_noop("Neuer Passkey für dein Konto"),
        gettext_noop(
            "Für deinen HUBIplan-Zugang wurde der Passkey „{name}“ eingerichtet ({host})."
        ),
        authenticator.wrap().name,
        current_host(request) if request is not None else "",
    )


def _on_removed(sender, request=None, user=None, authenticator=None, **kwargs):
    from allauth.mfa.models import Authenticator
    from django.utils.translation import gettext_noop

    if authenticator is None or authenticator.type != Authenticator.Type.WEBAUTHN:
        return
    _mail(
        user,
        gettext_noop("Passkey entfernt"),
        gettext_noop("Der Passkey „{name}“ wurde aus deinem HUBIplan-Zugang entfernt."),
        authenticator.wrap().name,
        "",
    )


def connect() -> None:
    from allauth.mfa import signals

    signals.authenticator_added.connect(_on_added, dispatch_uid="passkey-added-mail")
    signals.authenticator_removed.connect(_on_removed, dispatch_uid="passkey-removed-mail")
