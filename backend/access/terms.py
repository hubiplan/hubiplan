"""Amtszeiten in Untereinheiten: Vorgänger beim Besetzen beenden (Rollen-Vorschlag R3)."""

from __future__ import annotations

import datetime

from audit.log import diff, record, snapshot

from .models import RoleAssignment


def end_unit_predecessors(holder: RoleAssignment, org, user, keep=None) -> list[str]:
    """Laufende Amtszeiten anderer Mitglieder in derselben Rolle zum Vortag beenden.

    ``keep``: Mitgliedschaft, deren Amtszeit nicht beendet werden darf (die eigene
    Rollenverwaltung im Zug-Arbeitsbereich). Gibt die Namen der Beendeten zurück.
    """
    until = holder.valid_from - datetime.timedelta(days=1)
    others = (
        RoleAssignment.all_objects.filter(role=holder.role_id, membership__isnull=False)
        .active(holder.valid_from)
        .exclude(pk=holder.pk)
        .exclude(membership_id=holder.membership_id)
        .select_related("membership__person")
    )
    if keep is not None:
        others = others.exclude(membership_id=keep)
    ended = []
    for other in others:
        before = snapshot(other)
        other.valid_until = max(other.valid_from, until)
        other.save(update_fields=["valid_until"])
        person = other.membership.person
        record(org, user, "update", other, diff(before, snapshot(other)), person=person)
        ended.append(f"{person.first_name} {person.last_name}".strip())
    return ended
