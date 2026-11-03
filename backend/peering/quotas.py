"""Persistent conservative reception budgets, including existing retained files.

Reservations account for accepted traffic, not just current disk usage: replacements
do not refund capacity. All receivers serialize their check/reservation in the outer
receive transaction. Financial retention is never weakened to recover quota.
"""

import datetime
import json

from django.conf import settings
from django.db import connection, models
from django.db.models import Count
from django.utils import timezone
from django.utils.translation import gettext

from core.tenancy import rls_bypass

from .models import (
    Coupling,
    Message,
    RemoteCircular,
    RemoteInvoice,
    RemoteMember,
    RemoteState,
    RemoteTransfer,
)

DEFAULTS = {
    "INSTANCE_BYTES": 10 * 1024**3,
    "INSTANCE_MESSAGES": 200000,
    "UNIT_BYTES": 2 * 1024**3,
    "UNIT_MESSAGES": 50000,
    "PEER_BYTES": 1024**3,
    "PEER_MESSAGES": 25000,
    "PEER_DAILY_MESSAGES": 1000,
}


def limit(key):
    value = int(getattr(settings, "PEERING_RECEPTION_" + key, DEFAULTS[key]))
    if value <= 0:
        raise ValueError("Peering reception limits must be positive")
    return value


def _size(obj):
    total = 1024
    for field in obj._meta.concrete_fields:
        value = getattr(obj, field.attname)
        if isinstance(field, models.FileField) and value:
            # Missing/inaccessible files must not silently erase the reservation.
            total += value.size
        elif isinstance(field, (models.JSONField, models.TextField, models.CharField)):
            total += len(json.dumps(value, ensure_ascii=False, default=str).encode())
    return total


def _legacy(coupling):
    count = Message.objects.filter(coupling=coupling, direction=Message.Direction.IN).count()
    size = count * 1024 + _size(coupling.remote_unit)
    for cls in (
        RemoteState,
        RemoteInvoice,
        RemoteCircular,
        RemoteMember,
        RemoteTransfer,
    ):
        for obj in cls.objects.filter(coupling=coupling).iterator():
            size += _size(obj)
            if isinstance(obj, RemoteCircular) and obj.circular_id:
                size += _size(obj.circular)
                for attachment in obj.circular.attachments.all():
                    size += _size(attachment)
    # Other inbound tables are bounded per packet; historical message records have
    # no payload sizes. Reserve the full minimum packet charge for them as well.
    return max(size, count * 65536), count


def lock_reception():
    """Always before locking a Coupling row: initialization may update other rows."""
    if not connection.in_atomic_block:
        raise RuntimeError("Reception reservations require a transaction")
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [0x48505154, 1])


def reserve(coupling, data):
    """Call after lock_reception and the coupling row lock, before persistence."""
    from .services import Refused

    lock_reception()
    charge = max(65536, 2 * len(json.dumps(data, ensure_ascii=False).encode()))
    with rls_bypass():
        rows = list(Coupling.objects.all())
        counts = dict(
            Message.objects.filter(direction=Message.Direction.IN)
            .values("coupling_id")
            .annotate(n=Count("pk"))
            .values_list("coupling_id", "n")
        )
        usages = []
        for row in rows:
            try:
                used, count = (
                    (row.received_bytes, row.received_count)
                    if row.usage_initialized and row.received_count >= counts.get(row.pk, 0)
                    else _legacy(row)
                )
                # A temporarily rolled-back old receiver cannot make historical
                # reservations disappear when the new code is started again.
                used, count = max(used, row.received_bytes), max(count, row.received_count)
            except OSError as exc:
                raise Refused(
                    507,
                    gettext(
                        "Der vorhandene Partnerspeicher muss vor weiterem Empfang geprüft werden."
                    ),
                ) from exc
            if (
                not row.usage_initialized
                or used != row.received_bytes
                or count != row.received_count
            ):
                Coupling.objects.filter(pk=row.pk).update(
                    received_bytes=used, received_count=count, usage_initialized=True
                )
            usages.append((row, used, count))
        scopes = {
            "INSTANCE": usages,
            "UNIT": [r for r in usages if r[0].local_unit_id == coupling.local_unit_id],
            "PEER": [r for r in usages if r[0].peer_id == coupling.peer_id],
        }
        for scope, selected in scopes.items():
            if sum(r[1] for r in selected) + charge > limit(scope + "_BYTES") or sum(
                r[2] for r in selected
            ) + 1 > limit(scope + "_MESSAGES"):
                raise Refused(
                    507,
                    gettext(
                        "Das Empfangs-/Kapazitätsbudget ist ausgeschöpft. "
                        "Die Administration muss die Kapazität prüfen und freigeben."
                    ),
                )
        daily = Message.objects.filter(
            direction=Message.Direction.IN,
            coupling__peer_id=coupling.peer_id,
            created_at__gte=timezone.now() - datetime.timedelta(days=1),
        ).count()
        if daily >= limit("PEER_DAILY_MESSAGES"):
            raise Refused(
                429, gettext("Das tägliche Empfangsbudget des Partners ist ausgeschöpft.")
            )
        current = next(r for r in usages if r[0].pk == coupling.pk)
        coupling.received_bytes = current[1] + charge
        coupling.received_count = current[2] + 1
        coupling.usage_initialized = True
        coupling.save(update_fields=["received_bytes", "received_count", "usage_initialized"])
