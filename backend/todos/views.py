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

from .access import can_delete, can_edit, can_take_over, local_task, scope_for, visible
from .models import Todo, TodoPreference
from .sharing import eligible_users, log_change, replace_shares, transfer_owner


class ShareInput(serializers.Serializer):
    target_org = serializers.IntegerField(required=False, min_value=1)
    target_department = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    user = serializers.IntegerField(required=False, min_value=1)
    role = serializers.IntegerField(required=False, min_value=1)
    level = serializers.ChoiceField(choices=["view", "edit"], default="view")
    responsible = serializers.BooleanField(default=False)


class TodoInput(serializers.Serializer):
    event = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    per_unit = serializers.BooleanField(required=False)
    local_note = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    following = serializers.BooleanField(required=False)
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
    from .event_links import event_data
    from .reminders import highlight
    from .remote import completion_allowed
    from .series_views import series_data
    from .sharing import participants

    return {
        "remote_mode": todo.remote_mode,
        "event": event_data(todo, user, scope),
        "id": todo.pk,
        "organization": todo.organization_id,
        "department": todo.department_id,
        "series": series_data(todo),
        "distributed": todo.distributed,
        "per_unit": todo.per_unit,
        "local_note": todo.local_note if todo.distributed else "",
        "central_readonly": todo.distributed,
        "can_complete": can_edit(todo, user, scope)
        and not todo.per_unit
        and completion_allowed(todo),
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
        "shares": list(
            todo.shares.order_by("pk").values(
                "user", "role", "target_org", "target_department", "level", "responsible"
            )
        )
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
        from .remote import fresh_rows

        items = [
            data_for(t, request.user, self.scope) for t in fresh_rows(qs.order_by("-created_at"))
        ]
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
        requested_mode = values.pop("per_unit", None)
        values.pop("local_note", None)
        values.pop("owner", None)
        if "event" in values:
            from .event_links import validate_event

            values["event"] = validate_event(request.user, self.scope, values["event"])
        if not values.get("title"):
            raise serializers.ValidationError({"title": gettext("Bitte einen Titel eingeben.")})
        if values.get("due_time") and not values.get("due_date"):
            raise serializers.ValidationError(
                {"due_time": gettext("Eine Uhrzeit braucht ein Datum.")}
            )
        for field in ("version", "status", "deleted", "following"):
            values.pop(field, None)
        todo = Todo.objects.create(
            organization=self.org,
            department_id=self.scope.department_id,
            created_by=request.user,
            owner=request.user,
            **values,
        )
        if shares:
            from .distribution import reconcile, set_mode

            set_mode(todo, self.scope, requested_mode, shares)
            added = replace_shares(todo, request.user, self.scope, shares)
            todo.save()
            reconcile(todo, attachments=True)
            from .notify import schedule_shared

            schedule_shared(todo, added)
        log_change(todo, request.user, "create")
        return Response(data_for(todo, request.user, self.scope), status=201)


class TodoDetailView(TodoScopeMixin, APIView):
    def get(self, request, pk, **kwargs):
        todo = get_object_or_404(visible(request.user, self.scope), pk=pk)
        from .remote import refresh_common

        return Response(data_for(refresh_common(todo), request.user, self.scope))

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        deleted = bool(request.data.get("deleted") is False)
        from .series import lock_task

        todo = lock_task(request.user, self.scope, pk, deleted=deleted)
        taking_over = request.data.get("owner") == request.user.pk and can_take_over(
            todo, request.user, self.scope
        )
        if not can_edit(todo, request.user, self.scope) and not taking_over:
            raise PermissionDenied()
        serializer = TodoInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        following = values.pop("following", False)
        if values.pop("version", None) != todo.version:
            return Response(
                {"detail": gettext("Die Aufgabe wurde inzwischen geändert. Bitte neu laden.")},
                status=409,
            )
        from .remote import complete_common, completion_allowed

        if "status" in values and not completion_allowed(todo):
            raise PermissionDenied()
        if todo.remote_mode == "common" and "status" in values:
            if set(values) != {"status"} or following:
                raise serializers.ValidationError(
                    gettext("Status bitte getrennt von anderen Änderungen speichern.")
                )
            todo = complete_common(todo, request.user, values["status"])
            from changes.tracking import active

            ctx = active()
            if ctx:
                ctx.block(gettext("Diese Änderung kann hier nicht zurückgenommen werden."))
            return Response(data_for(todo, request.user, self.scope))
        ownership_only = "owner" in values
        if ownership_only and set(values) != {"owner"}:
            raise serializers.ValidationError(
                gettext("Verantwortung bitte getrennt von anderen Änderungen übertragen.")
            )
        shares = values.pop("shares", None)
        requested_mode = values.pop("per_unit", None)
        from .distribution import CENTRAL, reconcile, set_mode

        if "event" in values:
            from .event_links import validate_event

            if not can_delete(todo, request.user, self.scope):
                raise PermissionDenied()
            values["event"] = validate_event(request.user, self.scope, values["event"])

        if todo.distributed and (set(values) & CENTRAL or requested_mode is not None):
            raise PermissionDenied(gettext("Diese Felder werden von der Quelle vorgegeben."))
        if not todo.distributed and "local_note" in values:
            raise serializers.ValidationError(gettext("Lokale Notizen gehören zu einer Zielkopie."))
        set_mode(todo, self.scope, requested_mode, shares)
        if todo.per_unit and "status" in values:
            raise serializers.ValidationError(
                gettext("Diese Aufgabe wird je Zieleinheit erledigt.")
            )
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
        if todo.series_id and not todo.due_date:
            raise serializers.ValidationError(
                gettext("Wiederholungen brauchen eine offene Aufgabe mit Frist.")
            )
        todo.version += 1
        if following and todo.series_id:
            from .series import require_series_edit, update_template

            require_series_edit(todo, request.user, self.scope)

            update_template(
                todo,
                reset_anchor="due_date" in values,
                fields=set(values),
                shares=shares is not None,
            )
        if ownership_only:
            from core.tenancy import rls_bypass

            # Nur die zuvor am gesperrten Datensatz geprüfte Verantwortungsübergabe.
            with rls_bypass():
                todo.save(update_fields=["owner", "version", "updated_at"])
        else:
            from django.core.exceptions import ValidationError as ModelValidationError

            try:
                todo.save()
            except ModelValidationError as exc:
                raise serializers.ValidationError(exc.messages) from exc
        log_change(todo, request.user, "update")
        reconcile(todo, changed=set(values) & CENTRAL, attachments=shares is not None)
        from .notify import schedule_shared

        schedule_shared(todo, added)
        response = Response(data_for(todo, request.user, self.scope))
        if not local_task(todo, self.scope):
            response["X-Change-Task"] = str(todo.pk)
        return response


class TodoChoicesView(TodoScopeMixin, APIView):
    def get(self, request, **kwargs):
        if "todos.edit" not in self.scope.permissions:
            raise PermissionDenied()
        from access.catalog import effective
        from access.models import Role
        from core.tenancy import tenant_context

        from .targets import allowed_scopes, key, label

        units = []
        for target in allowed_scopes(self.scope).values():
            with tenant_context(target.org.pk):
                units.append(
                    {
                        "key": key(target),
                        "organization": target.org.pk,
                        "department": target.department_id,
                        "name": label(target),
                        "users": [
                            {"id": u.pk, "name": u.get_full_name() or u.email}
                            for u in eligible_users(target)
                        ],
                        "roles": [
                            {
                                "id": r.pk,
                                "name": r.name,
                                "has_task_access": "todos.view"
                                in effective(r.permissions, dept=bool(target.department_id)),
                            }
                            for r in Role.all_objects.filter(
                                organization=target.org, department_id=target.department_id
                            )
                        ],
                    }
                )

        return Response(
            {
                "units": units,
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
        from core.tenancy import rls_bypass, tenant_context

        from .models import TodoSeries

        with user_view(request.user.pk):
            metadata = get_object_or_404(
                Todo.objects.only("organization_id", "series_id"),
                pk=pk,
                created_by=request.user,
                shared=False,
            )
        # Kontoeigene private Daten bleiben nach Rollenverlust löschbar. Nach der
        # Lesefreigabe werden ausschließlich diese Nummern gesperrt und erneut geprüft.
        with tenant_context(metadata.organization_id, request.user.pk), suppress(), rls_bypass():
            if metadata.series_id:
                TodoSeries.objects.select_for_update().values("pk").get(pk=metadata.series_id)
            todo = get_object_or_404(
                Todo.objects.select_for_update(), pk=pk, created_by=request.user, shared=False
            )
            if todo.series_id != metadata.series_id:
                from .attachments import Conflict

                raise Conflict(gettext("Die Aufgabe wurde inzwischen geändert. Bitte neu laden."))
            ChangeSet.objects.filter(
                records__model="todos.todo", records__object_id=str(todo.pk)
            ).delete()
            series_id = todo.series_id
            todo.delete()
            if series_id:
                TodoSeries.objects.filter(
                    pk=series_id, owner=request.user, occurrences__isnull=True
                ).delete()
        return Response(status=204)
