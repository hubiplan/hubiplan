from django.utils.translation import gettext

from .access import Scope, visible


def todo_tasks(user, org, perms, department_id=None):
    if "todos.view" not in perms:
        return []
    scope = Scope(org, department_id, perms)
    rows = list(visible(user, scope).filter(status="open").order_by("due_date", "-created_at"))
    dated = [t for t in rows if t.due_date]
    undated = [t for t in rows if not t.due_date][:5]
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
            "can_edit": t.owner_id == user.pk,
        }
        for t in dated + undated
    ]
