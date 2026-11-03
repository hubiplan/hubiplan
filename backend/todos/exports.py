from contextlib import contextmanager
from contextvars import ContextVar

from rest_framework.exceptions import NotFound, PermissionDenied

from core.tenancy import tenant_context

from .access import scope_for, visible

_actor = ContextVar("todo_export_actor", default=None)


@contextmanager
def for_actor(user):
    token = _actor.set(user)
    try:
        yield
    finally:
        _actor.reset(token)


def shared_rows(org, department=None):
    from .models import Todo

    user = _actor.get()
    if user is None or not user.is_active:
        return Todo.objects.none()
    # IDs unter der heutigen Aufgabenprüfung bestimmen, erst danach exportieren.
    with tenant_context(org.pk, user.pk):
        try:
            scope = scope_for(user, org.pk, department.pk if department else None)
        except (NotFound, PermissionDenied):
            return Todo.objects.none()
        ids = list(visible(user, scope).filter(shared=True).values_list("pk", flat=True))
    return Todo.objects.filter(organization=org, shared=True, pk__in=ids)
