"""Empfängerauswahl, Freigaben und verantwortliche Konten."""

from django.utils.translation import gettext
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from access.models import Role, RoleAssignment
from accounts.models import User
from audit.log import record
from changes.tracking import active, suppress
from core.tenancy import tenant_context

from .access import can_take_over, scope_for, shares_for
from .models import TodoShare


def eligible_users(scope):
    assignments = RoleAssignment.all_objects.active().filter(
        organization=scope.org,
        role__department_id=scope.department_id,
    )
    ids = set(assignments.filter(user__isnull=False).values_list("user_id", flat=True))
    if scope.department_id:
        from portal.models import PortalAccess

        memberships = assignments.filter(membership__isnull=False).values("membership_id")
        ids.update(
            PortalAccess.objects.filter(membership_id__in=memberships).values_list(
                "user_id", flat=True
            )
        )
    users = []
    for user in User.objects.filter(pk__in=ids, is_active=True).order_by("email"):
        with tenant_context(scope.org.pk, user.pk):
            try:
                scope_for(user, scope.org.pk, scope.department_id)
            except (NotFound, PermissionDenied):
                continue
        users.append(user)
    return users


def participants(todo, scope):
    result = {}
    for user in eligible_users(scope):
        with tenant_context(scope.org.pk, user.pk):
            entries = list(shares_for(user, scope).filter(todo=todo))
        if entries or user.pk in {todo.owner_id, todo.created_by_id}:
            result[user.pk] = {
                "user": user,
                "edit": user.pk == todo.owner_id or any(s.level == "edit" for s in entries),
                "responsible": any(s.responsible for s in entries),
            }
    return result


def replace_shares(todo, user, scope, values):
    if todo.owner_id != user.pk or "todos.edit" not in scope.permissions:
        raise PermissionDenied()
    allowed_users = {u.pk for u in eligible_users(scope)}
    roles = set(
        Role.all_objects.filter(
            organization=scope.org, department_id=scope.department_id
        ).values_list("pk", flat=True)
    )
    rows = []
    seen = set()
    for value in values:
        user_id, role_id = value.get("user"), value.get("role")
        if bool(user_id) == bool(role_id) or value.get("level", "view") not in {"view", "edit"}:
            raise ValidationError(gettext("Ungültige Aufgabenfreigabe."))
        if user_id and user_id not in allowed_users or role_id and role_id not in roles:
            raise ValidationError(gettext("Dieser Empfänger hat keinen passenden Zugang."))
        key = (user_id, role_id)
        if key in seen:
            raise ValidationError(gettext("Dieser Empfänger ist bereits ausgewählt."))
        seen.add(key)
        rows.append(
            TodoShare(
                organization=scope.org,
                todo=todo,
                user_id=user_id,
                role_id=role_id,
                target_org=scope.org,
                target_department_id=scope.department_id,
                level=value.get("level", "view"),
                responsible=value.get("responsible", False),
            )
        )
    previous = set(participants(todo, scope))
    # Freigaben werden nicht durch allgemeines Rückgängig wiederhergestellt.
    with suppress():
        todo.shares.all().delete()
        TodoShare.objects.bulk_create(rows)
    if todo.shared and not rows:
        record(todo.organization, user, "update", todo)
    todo.shared = bool(rows)
    if not rows and todo.owner_id != todo.created_by_id:
        raise ValidationError(gettext("Eine übertragene Aufgabe muss geteilt bleiben."))
    ctx = active()
    if ctx:
        ctx.block(gettext("Freigaben lassen sich nicht rückgängig machen."))
    return set(participants(todo, scope)) - previous


def transfer_owner(todo, user, scope, owner_id):
    if todo.owner_id != user.pk and not can_take_over(todo, user, scope):
        raise PermissionDenied()
    ctx = active()
    if ctx:
        ctx.block(gettext("Verantwortung lässt sich nicht rückgängig übertragen."))
    if owner_id == user.pk and can_take_over(todo, user, scope):
        todo.owner = user
        return
    available = participants(todo, scope)
    if owner_id not in available or not available[owner_id]["edit"]:
        raise ValidationError(
            "Das verantwortliche Konto muss beteiligt sein und bearbeiten dürfen."
        )
    todo.owner_id = owner_id


def log_change(todo, user, action):
    if todo.shared:
        record(todo.organization, user, action, todo)
