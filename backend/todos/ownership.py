"""Begrenzte Verwaltung verwaister geteilter Aufgaben, ohne private Inhalte zu lesen."""

from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied

from changes.tracking import suppress
from core.tenancy import rls_bypass

from .access import can_take_over
from .models import Todo, TodoSeries
from .sharing import log_change


def candidates(user, scope):
    if not {"todos.edit", "roles.edit"} <= scope.permissions:
        raise PermissionDenied()
    # Eng begrenzte Verwaltungsprüfung: nur Besitzdaten geteilter Aufgaben der
    # eigenen Einheit. Inhalt wird erst nach der ausdrücklichen Übernahme zugänglich.
    with rls_bypass():
        rows = list(
            Todo.objects.filter(
                organization=scope.org,
                department_id=scope.department_id,
                shared=True,
                deleted_at__isnull=True,
            ).only("id", "organization_id", "department_id", "owner_id", "shared", "version")
        )
    return [row for row in rows if can_take_over(row, user, scope)]


@transaction.atomic
def take_over(user, scope, pk):
    if not {"todos.edit", "roles.edit"} <= scope.permissions:
        raise PermissionDenied()
    with rls_bypass(), suppress():
        series_id = (
            Todo.objects.filter(pk=pk, organization=scope.org, shared=True)
            .values_list("series_id", flat=True)
            .first()
        )
        if series_id:
            TodoSeries.objects.select_for_update().get(pk=series_id)
        todo = (
            Todo.objects.select_for_update()
            .filter(
                pk=pk,
                organization=scope.org,
                department_id=scope.department_id,
                shared=True,
                deleted_at__isnull=True,
            )
            .only("id", "organization_id", "department_id", "owner_id", "shared", "version")
            .first()
        )
        if todo is None or not can_take_over(todo, user, scope):
            raise NotFound()
        from .sharing import assign_series_owner

        assign_series_owner(todo, user.pk)
        todo.owner = user
        todo.version += 1
        todo.save(update_fields=["owner", "version", "updated_at"])
        log_change(todo, user, "update")
    return todo.pk
