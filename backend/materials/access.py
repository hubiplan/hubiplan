from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, PermissionDenied

from access.permissions import permissions_in
from core.tenancy import scope_of, set_rls
from organizations.models import Organization
from todos.access import Scope


def scope_for(user, org_id=None, dept_id=None, *, write=False):
    if dept_id is not None:
        from portal.services import department_contexts

        ctx = department_contexts(user).get(int(dept_id))
        if ctx is None:
            raise NotFound()
        scope = Scope(ctx.club, ctx.department.pk, ctx.permissions)
    else:
        org = get_object_or_404(Organization, pk=org_id, type__in=["club", "federation"])
        scope = Scope(org, None, permissions_in(user, org))
    if "material" not in (scope.org.enabled_modules or []):
        raise NotFound()
    if ("material.edit" if write else "material.view") not in scope.permissions:
        raise PermissionDenied()
    set_rls(
        scope.org.pk,
        user.pk,
        scope_id=scope_of(scope.org.pk),
        todo_department_id=scope.department_id,
    )
    if "todos.view" in scope.permissions:
        # Auch die eingeschränkte „Ansicht als Rolle“ für private Aufgaben übernehmen.
        from todos.access import scope_for as todo_scope

        todo_scope(user, org_id, dept_id)
    return scope


def items(scope, *, trash=False):
    from .models import MaterialItem

    return MaterialItem.objects.filter(
        organization=scope.org,
        department_id=scope.department_id,
        deleted_at__isnull=not trash,
    )


def members(scope):
    from members.models import Membership, today

    qs = Membership.objects.filter(organization=scope.org, purged_at__isnull=True)
    if "members.view" not in scope.permissions:
        return qs.none()
    if scope.department_id:
        from members.models import DepartmentMembership

        ids = DepartmentMembership.objects.filter(
            organization=scope.org,
            department_id=scope.department_id,
            valid_from__lte=today(),
        ).exclude(valid_until__lt=today())
        qs = qs.filter(pk__in=ids.values("membership_id"))
    return qs.select_related("person")


def events(user, scope):
    from events.models import Event
    from todos.event_links import viewer_for

    viewer = viewer_for(user, scope)
    return viewer.events().filter(organization=scope.org) if viewer else Event.objects.none()


def documents(scope):
    from todos.attachments import documents_for

    return documents_for(scope).filter(organization=scope.org)


def todos(user, scope):
    from todos.access import visible
    from todos.models import Todo
    from todos.remote import fresh_rows

    if "todos.view" not in scope.permissions:
        return Todo.objects.none()
    qs = visible(user, scope).filter(organization=scope.org)
    if not hasattr(scope, "_material_common_ids"):
        common = qs.filter(remote_mode="common").select_related("remote_origin__coupling")
        # Wie in der Aufgabenansicht: nur aktuell bestätigte gemeinsame Inhalte zeigen.
        # Der Scope lebt nur für diese Anfrage; mehrere Verweise teilen die Prüfung.
        scope._material_common_ids = [todo.pk for todo in fresh_rows(common)]
    return qs.exclude(remote_mode="common") | qs.filter(pk__in=scope._material_common_ids)
