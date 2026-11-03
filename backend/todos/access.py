"""Eine zentrale Aufgabenprüfung für API, Dateien, Rückgängig und Export."""

from dataclasses import dataclass

from django.db.models import Q
from rest_framework.exceptions import NotFound, PermissionDenied

from access import preview
from access.permissions import permissions_in
from core.tenancy import scope_of, set_rls
from organizations.models import Organization

from .models import Todo


@dataclass
class Scope:
    org: Organization
    department_id: int | None
    permissions: set[str]


def scope_for(user, org_id=None, dept_id=None):
    if dept_id is not None:
        from portal.services import department_contexts

        ctx = department_contexts(user).get(int(dept_id))
        if ctx is None:
            raise NotFound()
        result = Scope(ctx.club, ctx.department.pk, ctx.permissions)
    else:
        org = Organization.objects.filter(pk=org_id).first()
        if org is None:
            raise NotFound()
        result = Scope(org, None, permissions_in(user, org))
    if "todos.view" not in result.permissions:
        raise PermissionDenied()
    set_rls(result.org.pk, user.pk, scope_id=scope_of(result.org.pk))
    return result


def visible(user, scope, *, deleted=False):
    qs = Todo.objects.filter(
        organization=scope.org,
        department_id=scope.department_id,
        deleted_at__isnull=not deleted,
    )
    if preview.current() is not None:
        return qs.none()
    return qs.filter(Q(created_by=user) | Q(owner=user))


def can_edit(todo, user, scope):
    return (
        preview.current() is None and "todos.view" in scope.permissions and todo.owner_id == user.pk
    )


def can_delete(todo, user, scope):
    return can_edit(todo, user, scope) and todo.owner_id == user.pk


def undo_problem(change_set, user):
    """Keine Bereichsrechte als Ersatz für die heutige Aufgabenberechtigung."""
    records = list(change_set.records.all())
    if not records or any(r.model != "todos.todo" for r in records):
        return "Diese Änderung kann hier nicht zurückgenommen werden."
    for rec in records:
        todo = Todo.objects.filter(pk=rec.object_id).first()
        if todo is None:
            return "Die Aufgabe ist nicht mehr vorhanden."
        try:
            scope = scope_for(user, org_id=todo.organization_id, dept_id=todo.department_id)
        except (NotFound, PermissionDenied):
            return "Für diese Aufgabe fehlt dir die Berechtigung."
        if not can_edit(todo, user, scope):
            return "Für diese Aufgabe fehlt dir die Berechtigung."
        if rec.operation == "create" and not can_delete(todo, user, scope):
            return "Nur das verantwortliche Konto darf die Aufgabe löschen."
    return None
