from rest_framework.exceptions import NotFound, PermissionDenied

from core.tenancy import tenant_context, user_view
from todos.exports import _actor

from . import access


def rows(model, org, department=None):
    user = _actor.get()
    if user is None or not user.is_active or org.type not in ("club", "federation"):
        return model.objects.none()
    from portal.services import department_contexts

    with user_view(user.pk):
        units = (
            [department.pk]
            if department
            else [None]
            + [c.department.pk for c in department_contexts(user).values() if c.club.pk == org.pk]
        )
    result = set()
    for dept_id, kind in [(d, k) for d in units for k in access.AREAS]:
        with tenant_context(org.pk, user.pk):
            try:
                scope = access.scope_for(user, org.pk, dept_id, kind=kind)
            except (NotFound, PermissionDenied):
                continue
            qs = model.objects.filter(organization=org, department_id=dept_id)
            name = model._meta.model_name
            qs = qs.filter(kind=kind) if name == "materialitem" else qs.filter(item__kind=kind)
            if name == "materialtodolink":
                qs = qs.filter(todo__in=access.todos(user, scope).filter(shared=True))
            elif name == "materialdocumentlink":
                qs = qs.filter(document__in=access.documents(scope))
            elif name == "materialeventlink":
                qs = qs.filter(event__in=access.events(user, scope))
            result.update(qs.values_list("pk", flat=True))
    return model.objects.filter(pk__in=result)


def redact_member(row, obj):
    user = _actor.get()
    with tenant_context(obj.organization_id, user.pk):
        scope = access.scope_for(user, obj.organization_id, obj.department_id, kind=obj.kind)
        if obj.member_id and not access.members(scope).filter(pk=obj.member_id).exists():
            row["member"] = None
            row["location_kind"] = "unknown"
