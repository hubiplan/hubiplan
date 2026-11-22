"""Feste Kennungen für die API: Nach außen geht nie die interne Nummer eines Datensatzes.

Die Kennung entsteht beim ersten Abruf und bleibt danach gleich. Aufrufer stehen im
Datenbereich der Einheit (``org_context``).
"""

from __future__ import annotations

import uuid

from changes import tracking

from .models import RecordRef

MEMBER = "member"
HONOR = "honor"
QUALIFICATION = "qualification"


def public_ids(org, kind: str, ids) -> dict[int, uuid.UUID]:
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return {}
    query = RecordRef.objects.filter(organization=org, kind=kind)
    known = dict(query.filter(object_id__in=wanted).values_list("object_id", "public_id"))
    missing = [i for i in wanted if i not in known]
    if missing:
        with tracking.suppress():
            RecordRef.objects.bulk_create(
                [RecordRef(organization=org, kind=kind, object_id=i) for i in missing],
                ignore_conflicts=True,
            )
        known.update(query.filter(object_id__in=missing).values_list("object_id", "public_id"))
    return known


def existing(org, kind: str, object_id: int) -> uuid.UUID | None:
    """Kennung, falls der Datensatz schon einmal nach außen ging."""
    return (
        RecordRef.objects.filter(organization=org, kind=kind, object_id=object_id)
        .values_list("public_id", flat=True)
        .first()
    )


def resolve(org, kind: str, public_id) -> int | None:
    try:
        value = uuid.UUID(str(public_id))
    except ValueError:
        return None
    return (
        RecordRef.objects.filter(organization=org, kind=kind, public_id=value)
        .values_list("object_id", flat=True)
        .first()
    )
