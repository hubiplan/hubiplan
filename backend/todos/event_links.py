"""Terminverknüpfung gewährt niemals zusätzliche Kalender- oder Aufgabenrechte."""

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from events import services


def viewer_for(user, scope):
    if "events.view" not in scope.permissions or not services.module_on(scope.org):
        return None
    if scope.department_id:
        from portal.services import department_contexts

        ctx = department_contexts(user).get(scope.department_id)
        return services.department_viewer(ctx) if ctx else None
    return services.org_viewer(user, scope.org, scope.permissions)


def validate_event(user, scope, value):
    if value is None:
        return None
    viewer = viewer_for(user, scope)
    if viewer is None:
        raise PermissionDenied()
    # Nur der eigene Kalender; geteilte fremde Termine bleiben unverändert fremd.
    return get_object_or_404(
        viewer.events(), pk=value, organization=scope.org, department_id=scope.department_id
    )


def event_data(todo, user, scope):
    if todo.event_id is None:
        return None
    viewer = viewer_for(user, scope)
    event = viewer.events().filter(pk=todo.event_id).first() if viewer else None
    if event is None:
        return {"available": False}
    return {
        "available": True,
        "id": event.pk,
        "title": event.title,
        "starts_at": event.starts_at,
        "cancelled": event.is_cancelled,
    }


class EventChoicesView(APIView):
    def get(self, request, org_id=None, dept_id=None):
        from .access import scope_for

        scope = scope_for(request.user, org_id, dept_id)
        viewer = viewer_for(request.user, scope)
        items = []
        if viewer:
            items = list(
                viewer.events()
                .filter(organization=scope.org, department_id=scope.department_id)
                .order_by("-starts_at", "pk")
                .values("id", "title", "starts_at", "is_cancelled")[:2000]
            )
        return Response({"items": items})


def detach_deleted_event(sender, instance, **kwargs):
    from django.db.models import F

    from core.tenancy import rls_bypass

    from .models import Todo

    # Nur Beziehungsmetadaten, keine privaten Inhalte. Eine private Verknüpfung
    # darf weder das Löschen eines Termins verhindern noch dabei sichtbar werden.
    with rls_bypass():
        Todo.objects.filter(event=instance).update(event=None, version=F("version") + 1)
