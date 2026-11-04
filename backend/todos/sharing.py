"""Empfängerauswahl, Freigaben und verantwortliche Konten."""

from django.db.models import F
from django.utils.translation import gettext
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from access.models import Role, RoleAssignment
from accounts.models import User
from audit.log import record
from changes.tracking import active, suppress
from core.tenancy import rls_bypass, tenant_context

from .access import can_take_over, local_task, scope_for, shares_for
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
        if entries or (local_task(todo, scope) and user.pk in {todo.owner_id, todo.created_by_id}):
            result[user.pk] = {
                "user": user,
                "edit": user.pk == todo.owner_id or any(s.level == "edit" for s in entries),
                "responsible": any(s.responsible for s in entries),
            }
    return result


def replace_shares(todo, user, scope, values):
    if (
        not local_task(todo, scope)
        or todo.owner_id != user.pk
        or "todos.edit" not in scope.permissions
    ):
        raise PermissionDenied()
    todo._refresh_reminders = True
    from .targets import target_scope

    targets = {}
    rows = []
    seen = set()
    for value in values:
        target = target_scope(scope, value)
        if todo.distributed and (target.org.pk, target.department_id) != (
            scope.org.pk,
            scope.department_id,
        ):
            raise ValidationError(
                gettext("Kopien können nur innerhalb ihrer eigenen Einheit geteilt werden.")
            )
        unit = (target.org.pk, target.department_id)
        if unit not in targets:
            with tenant_context(target.org.pk):
                targets[unit] = (
                    {u.pk for u in eligible_users(target)},
                    set(
                        Role.all_objects.filter(
                            organization=target.org, department_id=target.department_id
                        ).values_list("pk", flat=True)
                    ),
                )
        allowed_users, roles = targets[unit]
        user_id, role_id = value.get("user"), value.get("role")
        if bool(user_id) == bool(role_id) or value.get("level", "view") not in {"view", "edit"}:
            raise ValidationError(gettext("Ungültige Aufgabenfreigabe."))
        if user_id and user_id not in allowed_users or role_id and role_id not in roles:
            raise ValidationError(gettext("Dieser Empfänger hat keinen passenden Zugang."))
        key = (user_id, role_id, *unit)
        if key in seen:
            raise ValidationError(gettext("Dieser Empfänger ist bereits ausgewählt."))
        seen.add(key)
        rows.append(
            TodoShare(
                organization=todo.organization,
                todo=todo,
                user_id=user_id,
                role_id=role_id,
                target_org=target.org,
                target_department_id=target.department_id,
                level=value.get("level", "view"),
                responsible=value.get("responsible", False),
            )
        )
    previous = set(all_participants(todo))
    # Freigaben werden nicht durch allgemeines Rückgängig wiederhergestellt.
    with suppress():
        todo.shares.all().delete()
        TodoShare.objects.bulk_create(rows)
    if todo.shared and not rows:
        record(todo.organization, user, "update", todo)
    from .models import TodoPortalPublication

    todo.shared = (
        bool(rows)
        or TodoPortalPublication.objects.filter(todo=todo, active=True).exists()
        or todo.remote_shares.filter(active=True).exists()
    )
    if not rows and todo.owner_id != todo.created_by_id:
        raise ValidationError(gettext("Eine übertragene Aufgabe muss geteilt bleiben."))
    ctx = active()
    if ctx:
        ctx.block(gettext("Freigaben lassen sich nicht rückgängig machen."))
    return set(all_participants(todo)) - previous


def all_participants(todo):
    from organizations.models import Organization

    from .access import Scope

    with rls_bypass():
        units = set(todo.shares.values_list("target_org_id", "target_department_id"))
    units.add((todo.organization_id, todo.department_id))
    result = {}
    for org_id, dept_id in units:
        with tenant_context(org_id):
            scope = Scope(Organization.objects.get(pk=org_id), dept_id, set())
            for uid, entry in participants(todo, scope).items():
                current = result.setdefault(uid, {**entry, "scope": scope})
                current["edit"] |= entry["edit"]
                current["responsible"] |= entry["responsible"]
    return result


def transfer_owner(todo, user, scope, owner_id):
    if not local_task(todo, scope):
        raise PermissionDenied()
    if todo.owner_id != user.pk and not can_take_over(todo, user, scope):
        raise PermissionDenied()
    ctx = active()
    if ctx:
        ctx.block(gettext("Verantwortung lässt sich nicht rückgängig übertragen."))
    if owner_id == user.pk and can_take_over(todo, user, scope):
        assign_series_owner(todo, owner_id)
        todo.owner = user
        return
    available = participants(todo, scope)
    if owner_id not in available or not available[owner_id]["edit"]:
        raise ValidationError(
            "Das verantwortliche Konto muss beteiligt sein und bearbeiten dürfen."
        )
    todo.owner_id = owner_id
    assign_series_owner(todo, owner_id)


def assign_series_owner(todo, owner_id):
    if not todo.series_id:
        return
    from .models import Todo, TodoSeries

    # Keine privaten früheren Ausgaben durch eine Übertragung offenlegen.
    with rls_bypass(), suppress():
        rows = Todo.objects.filter(series_id=todo.series_id, withdrawn=False)
        if rows.filter(shared=False).exists():
            raise ValidationError(
                gettext(
                    "Die Serie enthält private Ausgaben. "
                    "Bitte deren Freigaben zuerst ausdrücklich prüfen."
                )
            )
        rows.exclude(pk=todo.pk).update(owner_id=owner_id, version=F("version") + 1)
        series = TodoSeries.objects.select_for_update().get(pk=todo.series_id)
        series.owner_id = owner_id
        series.shares = list(
            todo.shares.order_by("pk").values(
                "user_id",
                "role_id",
                "target_org_id",
                "target_department_id",
                "level",
                "responsible",
            )
        )
        series.version += 1
        series.save()


def log_change(todo, user, action):
    if todo.shared:
        with tenant_context(todo.organization_id, user.pk):
            record(todo.organization, user, action, todo)
