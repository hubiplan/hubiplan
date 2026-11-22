"""Benachrichtigungen (Webhooks) der API für andere Programme (docs/api.md, Stufe 2).

Ändert sich ein Mitglied oder ein Termin, bekommt die Adresse des Zugangs eine schlanke
Nachricht: Art des Ereignisses und Kennung, nie Inhalte. Das angebundene Programm holt den
Stand danach über die API ab; dort gelten Bereiche und Rechtsgrundlage wie immer.

Jede Nachricht ist unterschrieben: ``X-HUBIplan-Signature: t=<Unixzeit>,v1=<HMAC-SHA256>``
über ``<Unixzeit>.<Nachricht>`` mit dem Geheimnis ``hpw_…`` des Zugangs. Zugestellt wird
mindestens einmal, bei Fehlern mit wachsendem Abstand bis zu drei Tage lang.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import logging
import urllib.parse
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext, gettext_noop

from changes import tracking
from core.tenancy import rls_bypass

from . import refs
from . import scopes as sc
from .models import HOOK_KEEP, HOOK_PAUSE_AFTER, ApiAccess, WebhookDelivery

logger = logging.getLogger(__name__)

MEMBER_CREATED = "member.created"
MEMBER_CHANGED = "member.changed"
MEMBER_LEFT = "member.left"
MEMBER_DELETED = "member.deleted"
EVENT_CREATED = "event.created"
EVENT_CHANGED = "event.changed"
EVENT_CANCELLED = "event.cancelled"
EVENT_DELETED = "event.deleted"
PING = "ping"


@dataclass(frozen=True)
class HookEvent:
    code: str
    label: str
    # Bereich, den der Zugang dafür braucht
    scope: str


EVENTS: tuple[HookEvent, ...] = (
    HookEvent(MEMBER_CREATED, gettext_noop("Mitglied aufgenommen"), sc.MEMBERS_READ),
    HookEvent(MEMBER_CHANGED, gettext_noop("Mitglied geändert"), sc.MEMBERS_READ),
    HookEvent(MEMBER_LEFT, gettext_noop("Austritt eingetragen"), sc.MEMBERS_READ),
    HookEvent(MEMBER_DELETED, gettext_noop("Mitglied gelöscht"), sc.MEMBERS_READ),
    HookEvent(EVENT_CREATED, gettext_noop("Termin angelegt"), sc.EVENTS_READ),
    HookEvent(EVENT_CHANGED, gettext_noop("Termin geändert"), sc.EVENTS_READ),
    HookEvent(EVENT_CANCELLED, gettext_noop("Termin abgesagt"), sc.EVENTS_READ),
    HookEvent(EVENT_DELETED, gettext_noop("Termin gelöscht"), sc.EVENTS_READ),
)
EVENT_BY_CODE = {e.code: e for e in EVENTS}

# Abstand bis zum nächsten Versuch nach dem 1., 2., 3. Fehler; danach stündlich
BACKOFF = (
    datetime.timedelta(minutes=1),
    datetime.timedelta(minutes=5),
    datetime.timedelta(minutes=30),
)
BACKOFF_LATER = datetime.timedelta(hours=1)
TIMEOUT = 10
BATCH = 200
FLAG_TTL = 300
ANY_KEY = "partnerapi:hooks:any"
RUN_KEY = "partnerapi:hooks:run"
MAX_URL = 500


def clean_events(codes, scopes) -> list[str]:
    """Gewählte Ereignisse, soweit der Zugang den Bereich dazu hat."""
    granted = set(scopes or [])
    chosen = set(codes or [])
    return [e.code for e in EVENTS if e.code in chosen and e.scope in granted]


def clean_url(value: str) -> str:
    """Adresse prüfen; ``ValueError`` bei allem außer einer einfachen https-Adresse."""
    url = (value or "").strip()
    if not url:
        return ""
    parts = urllib.parse.urlsplit(url)
    if (
        len(url) > MAX_URL
        or parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.fragment
    ):
        raise ValueError("keine https-Adresse")
    return url


# --- Gibt es überhaupt Empfänger? (billige Prüfung für jedes Speichern) ---


def forget_flags(org_id: int | None = None) -> None:
    cache.delete(ANY_KEY)
    if org_id is not None:
        cache.delete(f"partnerapi:hooks:{org_id}")


def _hooked() -> object:
    return ApiAccess.objects.exclude(webhook_url="").filter(webhook_paused_at__isnull=True)


def any_hooks() -> bool:
    if not settings.PARTNER_API_ENABLED:
        return False
    value = cache.get(ANY_KEY)
    if value is None:
        with rls_bypass():
            value = _hooked().exists()
        cache.set(ANY_KEY, value, FLAG_TTL)
    return bool(value)


def has_hooks(org_id: int) -> bool:
    if not any_hooks():
        return False
    key = f"partnerapi:hooks:{org_id}"
    value = cache.get(key)
    if value is None:
        with rls_bypass():
            value = _hooked().filter(organization_id=org_id).exists()
        cache.set(key, value, FLAG_TTL)
    return bool(value)


# --- Einreihen ---


def emit(
    org_id: int,
    event: str,
    kind: str,
    object_id: int,
    *,
    visibility: str = "",
    department_id: int | None = None,
) -> None:
    """Für alle passenden Zugänge einreihen. Aufrufer: nach dem Abschluss der Änderung
    (``partnerapi/signals.py``)."""
    if not has_hooks(org_id):
        return
    _enqueue(org_id, event, kind, object_id, visibility, department_id, timezone.now())


def _enqueue(org_id, event, kind, object_id, visibility, department_id, occurred) -> None:
    from .auth import enabled_for

    try:
        with rls_bypass(), tracking.suppress():
            accesses = list(
                _hooked()
                .filter(organization_id=org_id)
                .select_related("organization", "unit", "partner")
            )
            for access in accesses:
                if event not in (access.webhook_events or []):
                    continue
                if not access.is_active or not enabled_for(access.organization):
                    continue
                ref = _object_ref(access, event, kind, object_id, visibility, department_id)
                if not ref:
                    continue
                _add(access, event, ref, occurred)
    except Exception:  # noqa: BLE001 (eine Benachrichtigung darf keine Änderung stören)
        logger.exception("API-Benachrichtigung konnte nicht eingereiht werden")


def _object_ref(access, event, kind, object_id, visibility, department_id) -> str:
    """Kennung für die Nachricht; leer, wenn der Zugang den Datensatz nicht sehen darf."""
    from organizations.tree import subtree_ids

    granted = set(sc.clean(access.scopes or [], access.organization, access.unit))
    if EVENT_BY_CODE[event].scope not in granted:
        return ""
    if kind == refs.MEMBER:
        # Ein auf eine Untereinheit begrenzter Zugang erfährt nur beim Abruf, wer dazugehört
        if not access.personal_ok or access.unit_id:
            return ""
        if event == MEMBER_DELETED:
            known = refs.existing(access.organization, refs.MEMBER, object_id)
            return str(known) if known else ""
        return str(refs.public_ids(access.organization, refs.MEMBER, [object_id])[object_id])
    if visibility == "board":
        return ""
    if visibility == "members" and sc.EVENTS_MEMBERS not in granted:
        return ""
    if access.unit_id and department_id not in subtree_ids(access.unit):
        return ""
    return str(object_id)


def _add(access, event: str, ref: str, occurred) -> None:
    pending = WebhookDelivery.objects.filter(
        access=access, object_ref=ref, delivered_at__isnull=True, dropped_at__isnull=True
    )
    waiting = set(pending.values_list("event", flat=True))
    created, changed = {MEMBER_CREATED, EVENT_CREATED}, {MEMBER_CHANGED, EVENT_CHANGED}
    # Schon dasselbe unterwegs, oder „geändert“ rund um „angelegt“: eine Nachricht genügt
    if event in waiting or (event in changed and waiting & created):
        return
    if event in created:
        pending.filter(event__in=changed).delete()
    WebhookDelivery.objects.create(
        organization=access.organization,
        access=access,
        event=event,
        object_ref=ref,
        occurred_at=occurred,
        next_try_at=occurred,
    )


# --- Zustellen ---


def payload(access: ApiAccess, delivery_id, event: str, ref: str, occurred) -> bytes:
    kind = event.split(".", 1)[0]
    body = {
        "id": str(delivery_id),
        "type": event,
        "occurred_at": occurred.isoformat(),
        "unit": str(access.scope_unit.uuid),
    }
    if event != PING:
        body["object"] = {"type": kind, "id": ref}
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()


def sign(secret: str, timestamp: int, body: bytes) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


def send(access: ApiAccess, delivery_id, event: str, body: bytes) -> str:
    """Eine Nachricht senden; leer bei Erfolg, sonst ein kurzer Fehlertext."""
    from core import safehttp

    timestamp = int(timezone.now().timestamp())
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "HUBIplan-Webhook/1",
        "X-HUBIplan-Event": event,
        "X-HUBIplan-Delivery": str(delivery_id),
        "X-HUBIplan-Signature": sign(access.webhook_secret, timestamp, body),
    }
    try:
        response = safehttp.request(
            "POST",
            access.webhook_url,
            headers=headers,
            body=body,
            timeout=TIMEOUT,
            max_body=4096,
            deadline=2 * TIMEOUT,
        )
    except safehttp.SafeHTTPError as exc:
        return str(exc)[:200] or "nicht erreichbar"
    except Exception as exc:  # noqa: BLE001 (fremder Server: jede Störung ist ein Fehlversuch)
        return type(exc).__name__[:200]
    if 200 <= response.status < 300:
        return ""
    return f"HTTP {response.status}"


def _next_try(attempts: int, now):
    step = BACKOFF[attempts - 1] if attempts <= len(BACKOFF) else BACKOFF_LATER
    return now + step


def deliver_due() -> int:
    """Fällige Nachrichten zustellen (jede Minute). Liefert die Zahl der Erfolge."""
    from .auth import enabled_for

    if not settings.PARTNER_API_ENABLED or not cache.add(RUN_KEY, 1, 55):
        return 0
    sent = 0
    try:
        now = timezone.now()
        with rls_bypass():
            due = list(
                WebhookDelivery.objects.filter(
                    delivered_at__isnull=True, dropped_at__isnull=True, next_try_at__lte=now
                )
                .select_related("access", "access__organization", "access__unit")
                .order_by("pk")[:BATCH]
            )
        failed: set[int] = set()
        for delivery in due:
            access = delivery.access
            if access.pk in failed:
                continue
            gone = (
                not access.webhook_url
                or access.webhook_paused_at is not None
                or not access.is_active
                or not enabled_for(access.organization)
                or delivery.event not in (access.webhook_events or [])
            )
            if gone or delivery.occurred_at < now - HOOK_KEEP:
                _update(delivery, dropped_at=now)
                continue
            body = payload(
                access,
                delivery.delivery_id,
                delivery.event,
                delivery.object_ref,
                delivery.occurred_at,
            )
            error = send(access, delivery.delivery_id, delivery.event, body)
            now = timezone.now()
            if not error:
                sent += 1
                _update(delivery, delivered_at=now, attempts=delivery.attempts + 1, last_error="")
                _state(
                    access,
                    webhook_failing_since=None,
                    webhook_last_ok_at=now,
                    webhook_last_error="",
                )
                continue
            failed.add(access.pk)
            attempts = delivery.attempts + 1
            _update(
                delivery, attempts=attempts, last_error=error, next_try_at=_next_try(attempts, now)
            )
            since = access.webhook_failing_since or now
            changes = {"webhook_failing_since": since, "webhook_last_error": error}
            if since <= now - HOOK_PAUSE_AFTER:
                changes["webhook_paused_at"] = now
            _state(access, **changes)
            if "webhook_paused_at" in changes:
                from . import notify

                forget_flags(access.organization_id)
                notify.webhook_paused(access)
    finally:
        cache.delete(RUN_KEY)
    return sent


def _update(delivery: WebhookDelivery, **values) -> None:
    with rls_bypass(), tracking.suppress():
        WebhookDelivery.objects.filter(pk=delivery.pk).update(**values)


def _state(access: ApiAccess, **values) -> None:
    for name, value in values.items():
        setattr(access, name, value)
    with rls_bypass(), tracking.suppress():
        ApiAccess.objects.filter(pk=access.pk).update(**values)


def test(access: ApiAccess) -> str:
    """Probenachricht „ping“ sofort senden; leer bei Erfolg, sonst der Fehler."""
    import uuid

    if not access.webhook_url:
        return gettext("Es ist keine Adresse eingetragen.")
    delivery_id = uuid.uuid4()
    body = payload(access, delivery_id, PING, "", timezone.now())
    return send(access, delivery_id, PING, body)
