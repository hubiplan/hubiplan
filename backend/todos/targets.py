"""Erlaubte Nachbarebenen derselben Instanz; Auswahl erweitert keine Aufgabenrechte."""

from django.utils.translation import gettext
from rest_framework.exceptions import ValidationError

from organizations.models import Department, Organization

from .access import Scope


def allowed_scopes(source):
    result = {(source.org.pk, source.department_id): source}
    if source.department_id:
        result[(source.org.pk, None)] = Scope(source.org, None, set())
    elif source.org.type == "platform":
        for org in Organization.objects.filter(type__in=["federation", "club"], is_active=True):
            result[(org.pk, None)] = Scope(org, None, set())
    elif source.org.type == "federation":
        for org in Organization.objects.filter(type="club", parent=source.org, is_active=True):
            result[(org.pk, None)] = Scope(org, None, set())
    elif source.org.type == "club":
        if (
            source.org.parent_id
            and source.org.parent.type == "federation"
            and source.org.parent.is_active
        ):
            result[(source.org.parent_id, None)] = Scope(source.org.parent, None, set())
        for dept in Department.objects.filter(organization=source.org, is_active=True):
            result[(source.org.pk, dept.pk)] = Scope(source.org, dept.pk, set())
    return result


def target_scope(source, value):
    org_id = value.get("target_org", source.org.pk)
    dept_id = value.get(
        "target_department", None if "target_org" in value else source.department_id
    )
    target = allowed_scopes(source).get((org_id, dept_id))
    if target is None:
        raise ValidationError(gettext("Diese Zieleinheit ist für Aufgaben nicht erlaubt."))
    return target


def label(scope):
    return (
        Department.objects.get(pk=scope.department_id).display_name
        if scope.department_id
        else scope.org.name
    )


def key(scope):
    return f"{scope.org.pk}:{scope.department_id or 0}"
