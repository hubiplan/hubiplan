import datetime

from django.utils.translation import gettext

from .access import can_edit, scope_for, visible
from .reminders import highlight


def todo_tasks(user, org, perms, department_id=None):
    if "todos.view" not in perms:
        return []
    scope = scope_for(user, org.pk, department_id)
    from .remote import fresh_rows

    rows = [
        t
        for t in fresh_rows(
            visible(user, scope).filter(status="open").order_by("due_date", "-created_at")
        )
        if t.status == "open"
    ]
    dated = [t for t in rows if t.due_date]
    undated = [t for t in rows if not t.due_date][:5]
    dated.sort(
        key=lambda t: (
            not highlight(t, user)["highlight"],
            t.due_date,
            t.due_time or datetime.time.max,
        )
    )
    return [
        {
            "kind": "todo",
            "kind_label": gettext("Aufgabe"),
            "title": t.title,
            "detail": str(t.due_date) if t.due_date else gettext("ohne Frist"),
            "created_at": t.created_at,
            "ref": t.pk,
            "link": f"/aufgaben?aufgabe={t.pk}",
            "version": t.version,
            "can_edit": can_edit(t, user, scope) and not t.per_unit,
            **highlight(t, user),
        }
        for t in dated + undated
    ]
