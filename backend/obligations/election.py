"""Nach einer Vorstandswahl: Aufgabe „Vorstandsänderung beim Registergericht anmelden“.

Aufgerufen bei der Freigabe eines Protokolls (``meetings.minutes.release``). Die Aufgabe
entsteht, wenn in der Versammlung der Einheit selbst jemand in ein Amt gewählt wurde, dessen
Rolle „vertritt die Einheit (§ 26 BGB)“ trägt, und die Pflicht im Fristenkalender aktiv ist.
Ohne eigenen Eintrag gilt sie für Einheiten, die laut Impressum im Register stehen.
"""

from __future__ import annotations

import datetime

from django.utils import timezone
from django.utils.translation import gettext as _

from access.modules import module_on
from core.i18n import date_text, language_of_org

from .access import MODULE
from .catalog import BY_KEY, ELECTION_KEY
from .models import Obligation


def _norm(text: str) -> str:
    return " ".join((text or "").casefold().split())


def board_offices(org) -> set[str]:
    """Namen der Ämter, die den Verein vertreten (§ 26 BGB).

    Hat die Einheit das Kennzeichen an keiner Rolle gesetzt, zählen alle Vorstandsrollen:
    lieber eine Aufgabe zu viel als eine versäumte Anmeldung.
    """
    from access.models import Role

    roles = Role.objects.filter(organization=org, department__isnull=True)
    names = roles.filter(represents=True).values_list("name", flat=True)
    if not names:
        names = roles.filter(is_board=True).values_list("name", flat=True)
    return {_norm(name) for name in names}


def rule(org) -> Obligation | None:
    """Aktive Pflicht mit Auslöser „Wahl“; ohne Eintrag die Vorgabe für eingetragene Vereine."""
    from organizations.models import Imprint

    rows = list(Obligation.objects.filter(organization=org, trigger=Obligation.Trigger.ELECTION))
    if rows:
        return next((o for o in rows if o.active), None)
    if not Imprint.objects.filter(organization=org, registered=True).exists():
        return None
    suggestion = BY_KEY[ELECTION_KEY]
    return Obligation(
        organization=org,
        key=ELECTION_KEY,
        title=_(suggestion.title),
        note=_(suggestion.note),
        trigger=Obligation.Trigger.ELECTION,
    )


def after_release(meeting, user):
    """Aufgabe anlegen, wenn das freigegebene Protokoll eine Vorstandswahl enthält."""
    from meetings.models import Resolution

    org = meeting.organization
    if meeting.department_id is not None or not module_on(org, MODULE):
        return None
    offices = board_offices(org)
    if not offices:
        return None
    elections = [
        r
        for r in meeting.resolutions.filter(
            kind=Resolution.Kind.ELECTION, result=Resolution.Result.ACCEPTED
        ).select_related("elected__person")
        if _norm(r.office) in offices
    ]
    if not elections:
        return None
    with language_of_org(org):
        duty = rule(org)
        if duty is None:
            return None
        day = timezone.localtime(meeting.event.starts_at).date()
        due = day + datetime.timedelta(days=duty.days_after)
        lines = [
            _("Gewählt in „{meeting}“ am {day}:").format(
                meeting=meeting.event.title, day=date_text(day)
            )
        ]
        for r in elections:
            name = r.elected_name
            lines.append(f"– {r.office}: {name}" if name else f"– {r.office}")
        if duty.note:
            lines += ["", duty.note]
        description = "\n".join(lines)
        if module_on(org, "todos"):
            return _todo(org, user, duty, due, description, elections)
        return Obligation.objects.create(
            organization=org,
            title=duty.title[:200],
            note=description,
            due_date=due,
            interval_months=None,
            remind_days=duty.days_after,
            role_id=duty.role_id,
        )


def _todo(org, user, duty, due, description, elections):
    from todos.models import Todo, TodoShare

    todo = Todo.objects.create(
        organization=org,
        created_by=user,
        owner=user,
        title=duty.title[:200],
        description=description,
        due_date=due,
        shared=bool(duty.role_id),
    )
    if duty.role_id:
        TodoShare.objects.create(
            organization=org,
            todo=todo,
            role_id=duty.role_id,
            target_org=org,
            level="edit",
            responsible=True,
        )
    for r in elections:
        if r.todo_id is None:
            r.todo = todo
            r.save(update_fields=["todo"])
    return todo
