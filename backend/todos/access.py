"""Eine zentrale Aufgabenprüfung für API, Dateien, Rückgängig und Export."""

from dataclasses import dataclass

from django.db.models import Q
from rest_framework.exceptions import NotFound, PermissionDenied

from access import preview
from access.permissions import permissions_in
from core.tenancy import scope_of, set_rls
from organizations.models import Organization

from .models import Todo, TodoShare


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
    shares = shares_for(user, scope)
    if preview.current() is not None:
        return qs.filter(shared=True, pk__in=shares.values("todo_id"))
    return qs.filter(
        Q(created_by=user) | Q(owner=user) | Q(shared=True, pk__in=shares.values("todo_id"))
    )


def role_ids(user, scope):
    from access.models import RoleAssignment

    selected = preview.current()
    if selected is not None:
        if selected.user_id != user.pk or selected.org_id != scope.org.pk:
            return set()
        return {selected.role_id}
    assignments = RoleAssignment.all_objects.active().filter(organization=scope.org)
    if scope.department_id is None:
        assignments = assignments.filter(user=user, role__department__isnull=True)
    else:
        from organizations.models import Department
        from portal.services import department_contexts

        ctx = department_contexts(user).get(scope.department_id)
        if ctx is None:
            return set()
        dept = Department.objects.get(pk=scope.department_id)
        units = [node.pk for node in dept.ancestors() if node.type == "unit"]
        assignments = assignments.filter(
            membership_id=ctx.membership_id, role__department_id__in=units
        )
    return set(assignments.values_list("role_id", flat=True))


def shares_for(user, scope):
    qs = TodoShare.objects.filter(target_org=scope.org, target_department_id=scope.department_id)
    roles = role_ids(user, scope)
    if preview.current() is not None:
        return qs.filter(role_id__in=roles)
    return qs.filter(Q(user=user) | Q(role_id__in=roles))


def can_edit(todo, user, scope):
    if preview.current() is not None or "todos.view" not in scope.permissions:
        return False
    return todo.owner_id == user.pk or (
        todo.shared and shares_for(user, scope).filter(todo=todo, level="edit").exists()
    )


def can_delete(todo, user, scope):
    return can_edit(todo, user, scope) and todo.owner_id == user.pk


def owner_available(todo):
    if not todo.owner_id:
        return False
    from core.tenancy import tenant_context

    with tenant_context(todo.organization_id, todo.owner_id):
        try:
            scope_for(todo.owner, todo.organization_id, todo.department_id)
        except (NotFound, PermissionDenied):
            return False
    return todo.owner.is_active


def can_take_over(todo, user, scope):
    return bool(
        todo.shared
        and preview.current() is None
        and {"todos.edit", "roles.edit"} <= scope.permissions
        and not owner_available(todo)
    )


def undo_problem(change_set, user):
    """Keine Bereichsrechte als Ersatz für die heutige Aufgabenberechtigung."""
    records = list(change_set.records.all())
    if not records or any(r.model != "todos.todo" for r in records):
        return "Diese Änderung kann hier nicht zurückgenommen werden."
    for rec in records:
        todo = Todo.objects.filter(pk=rec.object_id).first()
        if todo is None:
            if rec.operation != "delete" or not rec.before:
                return "Die Aufgabe ist nicht mehr vorhanden."
            from changes.undo import _build

            todo = _build(Todo, rec.before)
        try:
            scope = scope_for(user, org_id=todo.organization_id, dept_id=todo.department_id)
        except (NotFound, PermissionDenied):
            return "Für diese Aufgabe fehlt dir die Berechtigung."
        if not can_edit(todo, user, scope):
            return "Für diese Aufgabe fehlt dir die Berechtigung."
        if rec.operation == "create" and not can_delete(todo, user, scope):
            return "Nur das verantwortliche Konto darf die Aufgabe löschen."
    return None
