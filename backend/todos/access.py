"""Eine zentrale Aufgabenprüfung für API, Dateien, Rückgängig und Export."""

from dataclasses import dataclass

from django.db.models import Q
from django.utils.translation import gettext
from rest_framework.exceptions import NotFound, PermissionDenied

from access import preview
from access.permissions import own_permissions_in, permissions_in
from core.tenancy import scope_of, set_rls
from organizations.models import Organization

from .models import Todo, TodoShare


@dataclass
class Scope:
    org: Organization
    department_id: int | None
    permissions: set[str]
    portal_access_id: int | None = None


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
    selected = preview.current()
    role_id = None
    if (
        selected is not None
        and selected.org_id == result.org.pk
        and selected.user_id == user.pk
        and "roles.preview" in own_permissions_in(user, result.org)
    ):
        role_id = selected.role_id
    set_rls(
        result.org.pk,
        user.pk,
        scope_id=scope_of(result.org.pk),
        todo_role_id=role_id,
        todo_department_id=result.department_id,
    )
    return result


def visible(user, scope, *, deleted=False):
    if scope.portal_access_id:
        from .portal import portal_visible

        return Todo.objects.none() if deleted else portal_visible(user, scope)
    qs = Todo.objects.filter(
        withdrawn=False,
        deleted_at__isnull=not deleted,
    )
    shares = shares_for(user, scope)
    if active_preview(user, scope) is not None:
        return qs.filter(shared=True, pk__in=shares.values("todo_id"))
    local = Q(organization=scope.org, department_id=scope.department_id)
    shared = Q(shared=True, pk__in=shares.values("todo_id")) & (Q(per_unit=False) | local)
    return qs.filter((local & (Q(created_by=user) | Q(owner=user))) | shared)


def current_scope(user, scope):
    if scope.portal_access_id:
        from .portal import portal_scope

        return portal_scope(user, scope.portal_access_id)[1]
    return scope_for(user, scope.org.pk, scope.department_id)


def local_task(todo, scope):
    return todo.organization_id == scope.org.pk and todo.department_id == scope.department_id


def active_preview(user, scope):
    selected = preview.current()
    if selected is not None and selected.user_id == user.pk and selected.org_id == scope.org.pk:
        if "roles.preview" in own_permissions_in(user, scope.org):
            return selected
    return None


def role_ids(user, scope):
    from access.models import RoleAssignment

    selected = active_preview(user, scope)
    if selected is not None:
        if (
            selected.user_id != user.pk
            or selected.org_id != scope.org.pk
            or "roles.preview" not in own_permissions_in(user, scope.org)
        ):
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
    if active_preview(user, scope) is not None:
        return qs.filter(role_id__in=roles)
    return qs.filter(Q(user=user) | Q(role_id__in=roles))


def can_edit(todo, user, scope):
    if preview.current() is not None or "todos.view" not in scope.permissions:
        return False
    return (local_task(todo, scope) and todo.owner_id == user.pk) or (
        todo.shared and shares_for(user, scope).filter(todo=todo, level="edit").exists()
    )


def can_delete(todo, user, scope):
    return local_task(todo, scope) and can_edit(todo, user, scope) and todo.owner_id == user.pk


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
        and local_task(todo, scope)
        and preview.current() is None
        and {"todos.edit", "roles.edit"} <= scope.permissions
        and not owner_available(todo)
    )


def undo_problem(change_set, user, task_scope=None):
    """Keine Bereichsrechte als Ersatz für die heutige Aufgabenberechtigung."""
    records = list(change_set.records.all())
    if change_set.user_id != user.pk:
        return gettext("Hier lassen sich nur eigene Aufgabenänderungen zurücknehmen.")
    if not records or any(r.model != "todos.todo" for r in records):
        return gettext("Diese Änderung kann hier nicht zurückgenommen werden.")
    for rec in records:
        todo = Todo.objects.filter(pk=rec.object_id).first()
        missing = todo is None
        if todo is None:
            if rec.operation != "delete" or not rec.before:
                return gettext("Die Aufgabe ist nicht mehr vorhanden.")
            from changes.undo import _build

            todo = _build(Todo, rec.before)
        if todo.remote_mode == "common":
            return gettext("Diese Änderung kann hier nicht zurückgenommen werden.")
        if todo.per_unit and rec.operation == "create":
            return gettext("Verteilte Aufgaben bitte über ihren Papierkorb löschen.")
        from .series import undo_problem as series_undo_problem

        problem = series_undo_problem(todo, rec)
        if problem:
            return problem
        try:
            scope = task_scope or scope_for(
                user, org_id=todo.organization_id, dept_id=todo.department_id
            )
        except (NotFound, PermissionDenied):
            return gettext("Für diese Aufgabe fehlt dir die Berechtigung.")
        if not can_edit(todo, user, scope):
            return gettext("Für diese Aufgabe fehlt dir die Berechtigung.")
        if (
            not missing
            and not visible(user, scope, deleted=bool(todo.deleted_at)).filter(pk=todo.pk).exists()
        ):
            return gettext("Für diese Aufgabe fehlt dir die Berechtigung.")
        fields = set(rec.before or {}) | set(rec.after or {})
        if (
            rec.operation == "update"
            and fields & {"deleted_at", "shared", "owner_id"}
            and not can_delete(todo, user, scope)
        ):
            return gettext("Nur das verantwortliche Konto darf die Aufgabe löschen.")
        if rec.operation == "create" and not can_delete(todo, user, scope):
            return gettext("Nur das verantwortliche Konto darf die Aufgabe löschen.")
    return None
