"""Aufgaben im Browser und über dieselbe Fachlogik in der App."""

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import user_view

from .access import can_delete, can_edit, can_take_over, scope_for, visible
from .models import Todo, TodoPreference
from .sharing import eligible_users, log_change, replace_shares, transfer_owner


class ShareInput(serializers.Serializer):
    user = serializers.IntegerField(required=False, min_value=1)
    role = serializers.IntegerField(required=False, min_value=1)
    level = serializers.ChoiceField(choices=["view", "edit"], default="view")
    responsible = serializers.BooleanField(default=False)


class TodoInput(serializers.Serializer):
    shares = ShareInput(many=True, required=False)
    owner = serializers.IntegerField(required=False, min_value=1)
    title = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(allow_blank=True, required=False, max_length=50000)
    due_date = serializers.DateField(allow_null=True, required=False)
    due_time = serializers.TimeField(allow_null=True, required=False)
    timezone = serializers.CharField(required=False, max_length=64)
    version = serializers.IntegerField(required=False, min_value=1)
    status = serializers.ChoiceField(choices=["open", "done"], required=False)
    deleted = serializers.BooleanField(required=False)

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise serializers.ValidationError(gettext("Ungültige Zeitzone.")) from exc
        return value


def data_for(todo, user, scope):
    from .reminders import highlight
    from .sharing import participants

    return {
        "id": todo.pk,
        **highlight(todo, user),
        "title": todo.title,
        "description": todo.description,
        "due_date": todo.due_date,
        "due_time": todo.due_time,
        "timezone": todo.timezone,
        "status": todo.status,
        "done_at": todo.done_at,
        "done_by": todo.done_by_id,
        "created_by": todo.created_by_id,
        "owner": todo.owner_id,
        "shared": todo.shared,
        "version": todo.version,
        "created_at": todo.created_at,
        "updated_at": todo.updated_at,
        "deleted_at": todo.deleted_at,
        "can_edit": can_edit(todo, user, scope),
        "can_delete": can_delete(todo, user, scope),
        "can_take_over": can_take_over(todo, user, scope),
        "can_share": can_delete(todo, user, scope) and "todos.edit" in scope.permissions,
        "shares": list(todo.shares.order_by("pk").values("user", "role", "level", "responsible"))
        if todo.shared
        else [],
        "owners": [
            {"id": p["user"].pk, "name": p["user"].get_full_name() or p["user"].email}
            for p in participants(todo, scope).values()
            if p["edit"]
        ]
        if todo.shared and can_delete(todo, user, scope)
        else [],
    }


class TodoScopeMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.scope = scope_for(request.user, kwargs.get("org_id"), kwargs.get("dept_id"))
        self.org = self.scope.org


class TodoListView(TodoScopeMixin, APIView):
    def get(self, request, **kwargs):
        qs = visible(request.user, self.scope, deleted=request.query_params.get("trash") == "1")
        items = [data_for(t, request.user, self.scope) for t in qs.order_by("-created_at")]
        items.sort(
            key=lambda t: (
                not t["highlight"],
                t["due_date"] is None,
                t["due_date"] or timezone.localdate(),
                t["due_time"] or datetime.time.max,
            )
        )
        return Response({"items": items})

    @transaction.atomic
    def post(self, request, **kwargs):
        serializer = TodoInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        shares = values.pop("shares", None)
        values.pop("owner", None)
        if not values.get("title"):
            raise serializers.ValidationError({"title": gettext("Bitte einen Titel eingeben.")})
        if values.get("due_time") and not values.get("due_date"):
            raise serializers.ValidationError(
                {"due_time": gettext("Eine Uhrzeit braucht ein Datum.")}
            )
        for field in ("version", "status", "deleted"):
            values.pop(field, None)
        todo = Todo.objects.create(
            organization=self.org,
            department_id=self.scope.department_id,
            created_by=request.user,
            owner=request.user,
            **values,
        )
        if shares:
            added = replace_shares(todo, request.user, self.scope, shares)
            todo.save()
            from .notify import schedule_shared

            schedule_shared(todo, added)
        log_change(todo, request.user, "create")
        return Response(data_for(todo, request.user, self.scope), status=201)


class TodoDetailView(TodoScopeMixin, APIView):
    def get(self, request, pk, **kwargs):
        todo = get_object_or_404(visible(request.user, self.scope), pk=pk)
        return Response(data_for(todo, request.user, self.scope))

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        deleted = bool(request.data.get("deleted") is False)
        todo = get_object_or_404(
            visible(request.user, self.scope, deleted=deleted).select_for_update(), pk=pk
        )
        taking_over = request.data.get("owner") == request.user.pk and can_take_over(
            todo, request.user, self.scope
        )
        if not can_edit(todo, request.user, self.scope) and not taking_over:
            raise PermissionDenied()
        serializer = TodoInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if values.pop("version", None) != todo.version:
            return Response(
                {"detail": gettext("Die Aufgabe wurde inzwischen geändert. Bitte neu laden.")},
                status=409,
            )
        ownership_only = "owner" in values
        if ownership_only and set(values) != {"owner"}:
            raise serializers.ValidationError(
                gettext("Verantwortung bitte getrennt von anderen Änderungen übertragen.")
            )
        shares = values.pop("shares", None)
        added = (
            replace_shares(todo, request.user, self.scope, shares) if shares is not None else set()
        )
        if "owner" in values:
            transfer_owner(todo, request.user, self.scope, values.pop("owner"))
        if "deleted" in values:
            if not can_delete(todo, request.user, self.scope):
                raise PermissionDenied()
            todo.deleted_at = timezone.now() if values.pop("deleted") else None
        if "status" in values and values["status"] != todo.status:
            todo.done_at = timezone.now() if values["status"] == "done" else None
            todo.done_by = request.user if values["status"] == "done" else None
        old_due = (todo.due_date, todo.due_time, todo.timezone)
        for key, value in values.items():
            setattr(todo, key, value)
        if todo.due_time and not todo.due_date:
            raise serializers.ValidationError(
                {"due_time": gettext("Eine Uhrzeit braucht ein Datum.")}
            )
        if old_due != (todo.due_date, todo.due_time, todo.timezone):
            todo.due_revision += 1
        todo.version += 1
        if ownership_only:
            from core.tenancy import rls_bypass

            # Nur die zuvor am gesperrten Datensatz geprüfte Verantwortungsübergabe.
            with rls_bypass():
                todo.save(update_fields=["owner", "version", "updated_at"])
        else:
            todo.save()
        log_change(todo, request.user, "update")
        from .notify import schedule_shared

        schedule_shared(todo, added)
        return Response(data_for(todo, request.user, self.scope))


class TodoChoicesView(TodoScopeMixin, APIView):
    def get(self, request, **kwargs):
        if "todos.edit" not in self.scope.permissions:
            raise PermissionDenied()
        from access.catalog import effective
        from access.models import Role

        return Response(
            {
                "users": [
                    {"id": u.pk, "name": u.get_full_name() or u.email}
                    for u in eligible_users(self.scope)
                ],
                "roles": [
                    {
                        "id": r.pk,
                        "name": r.name,
                        "has_task_access": "todos.view"
                        in effective(r.permissions, dept=bool(r.department_id)),
                    }
                    for r in Role.all_objects.filter(
                        organization=self.org, department_id=self.scope.department_id
                    )
                ],
            }
        )


class OrphanTasksView(TodoScopeMixin, APIView):
    def get(self, request, **kwargs):
        from .ownership import candidates

        return Response({"items": [{"id": row.pk} for row in candidates(request.user, self.scope)]})


class TakeOverView(TodoScopeMixin, APIView):
    def post(self, request, pk, **kwargs):
        from .ownership import take_over

        return Response({"id": take_over(request.user, self.scope, pk)})


class PreferenceInput(serializers.ModelSerializer):
    class Meta:
        model = TodoPreference
        fields = [
            "share_mail",
            "share_push",
            "reminder_mail",
            "reminder_push",
            "push_title",
            "purge_done",
        ]


class TodoPreferencesView(APIView):
    def get(self, request):
        preferences, _ = TodoPreference.objects.get_or_create(user=request.user)
        return Response(PreferenceInput(preferences).data)

    def patch(self, request):
        preferences, _ = TodoPreference.objects.get_or_create(user=request.user)
        serializer = PreferenceInput(preferences, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PersonalExportView(APIView):
    def get(self, request):
        from .exports import personal_export

        return personal_export(request.user, request.query_params.get("files") == "1")


class PersonalTaskDeleteView(APIView):
    @transaction.atomic
    def delete(self, request, pk):
        from changes.models import ChangeSet
        from changes.tracking import suppress
        from core.tenancy import tenant_context

        with user_view(request.user.pk):
            todo = get_object_or_404(
                Todo.objects.select_for_update(), pk=pk, created_by=request.user, shared=False
            )
        with tenant_context(todo.organization_id, request.user.pk), suppress():
            ChangeSet.objects.filter(
                records__model="todos.todo", records__object_id=str(todo.pk)
            ).delete()
            todo.delete()
        return Response(status=204)
