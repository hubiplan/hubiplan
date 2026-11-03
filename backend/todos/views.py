"""Aufgaben im Browser und über dieselbe Fachlogik in der App."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import user_view

from .access import can_delete, can_edit, scope_for, visible
from .models import Todo


class TodoInput(serializers.Serializer):
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
    return {
        "id": todo.pk,
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
        items.sort(key=lambda t: (t["due_date"] is None, t["due_date"] or timezone.localdate()))
        return Response({"items": items})

    @transaction.atomic
    def post(self, request, **kwargs):
        serializer = TodoInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
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
        if not can_edit(todo, request.user, self.scope):
            raise PermissionDenied()
        serializer = TodoInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if values.pop("version", None) != todo.version:
            return Response(
                {"detail": gettext("Die Aufgabe wurde inzwischen geändert. Bitte neu laden.")},
                status=409,
            )
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
        todo.save()
        return Response(data_for(todo, request.user, self.scope))


class PersonalExportView(APIView):
    def get(self, request):
        with user_view(request.user.pk):
            rows = list(
                Todo.objects.filter(created_by=request.user, shared=False).values(
                    "id",
                    "title",
                    "description",
                    "due_date",
                    "due_time",
                    "status",
                    "deleted_at",
                )
            )
        response = JsonResponse({"tasks": rows})
        response["Content-Disposition"] = 'attachment; filename="aufgaben.json"'
        return response
