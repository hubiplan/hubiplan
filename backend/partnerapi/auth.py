"""Schlüssel ``hpk_…`` prüfen, nur für ``/api/partner/v1/`` (docs/api.md).

Bei jeder Anfrage gilt live: Zugang nicht abgelaufen und nicht ruhend, Einheit aktiv, Modul
„API für andere Programme“ eingeschaltet, Adresse des Aufrufers erlaubt.
"""

from __future__ import annotations

from django.conf import settings
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from changes import tracking
from core.ratelimit import from_proxy
from core.tenancy import rls_bypass

from .models import KEY_PREFIX, ApiAccess, hash_key

MODULE = "api"


class Problem(Exception):
    """Fehlerantwort als ``application/problem+json`` (RFC 9457)."""

    def __init__(self, status: int, code: str, title: str, detail: str = "", **extra):
        super().__init__(title)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.extra = extra


def bearer(request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return value.strip()


def caller_ip(request) -> str:
    """Wirkliche Adresse des Aufrufers (ohne Zusammenfassen zu Netzen): Vor dem Backend steht
    genau ein Proxy, der ``X-Forwarded-For`` neu setzt (wie ``core.ratelimit.client_ip``)."""
    remote = request.META.get("REMOTE_ADDR", "")
    if not from_proxy(request):
        return remote
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    parts = [p.strip() for p in forwarded.split(",") if p.strip()]
    return parts[-1] if parts else remote


def enabled_for(org) -> bool:
    from access.modules import module_on

    return bool(settings.PARTNER_API_ENABLED) and module_on(org, MODULE)


def find_access(key: str, ip: str) -> ApiAccess:
    unauthorized = Problem(
        401,
        "invalid_key",
        _("API-Schlüssel fehlt oder ist ungültig"),
        _("Kopfzeile „Authorization: Bearer hpk_…“ mit einem gültigen Schlüssel senden."),
    )
    if not key.startswith(KEY_PREFIX):
        raise unauthorized
    digest = hash_key(key)
    now = timezone.now()
    with rls_bypass():
        access = (
            ApiAccess.objects.select_related("organization", "unit")
            .filter(Q(key_hash=digest) | Q(previous_key_hash=digest, previous_until__gt=now))
            .first()
        )
    if access is None:
        raise unauthorized
    org = access.organization
    unit_gone = access.unit_id is not None and not access.unit.is_active
    if not org.is_active or unit_gone or not enabled_for(org):
        raise unauthorized
    state = access.state
    if state == "expired":
        raise Problem(
            401,
            "access_expired",
            _("Der API-Zugang ist abgelaufen"),
            _("Die Einheit kann ihn in HUBIplan unter Einstellungen › API-Zugänge verlängern."),
        )
    if state == "idle":
        raise Problem(
            401,
            "access_idle",
            _("Der API-Zugang ruht, weil er lange nicht benutzt wurde"),
            _(
                "Die Einheit kann ihn in HUBIplan unter Einstellungen › API-Zugänge wieder "
                "einschalten."
            ),
        )
    if not access.allows_ip(ip):
        raise Problem(
            403,
            "ip_not_allowed",
            _("Von dieser Adresse aus ist der API-Zugang nicht erlaubt"),
        )
    return access


def note_use(access: ApiAccess, ip: str) -> None:
    with tracking.suppress(), rls_bypass():
        ApiAccess.objects.filter(pk=access.pk).update(
            last_used_at=timezone.now(),
            last_used_ip=ip[:45],
            request_count=F("request_count") + 1,
        )
