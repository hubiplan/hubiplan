from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from changes.tracking import active
from core.tenancy import rls_bypass
from peering import services
from peering.models import Coupling

from .access import can_delete, visible
from .attachments import Conflict
from .models import TodoRemoteShare, TodoRemoteTask
from .remote import LIMIT, SnapshotInput, _serialize, adopt, call, receive_one, remote_file
from .series import lock_task
from .views import TodoScopeMixin, data_for


class RemoteScope(TodoScopeMixin):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class ShareInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    coupling = serializers.IntegerField(min_value=1)
    active = serializers.BooleanField(default=True)
    mode = serializers.ChoiceField(choices=["copy", "common"])
    can_complete = serializers.BooleanField(default=True)
    following = serializers.BooleanField(default=False)


class RemoteSharesView(RemoteScope, APIView):
    def task(self, request, pk):
        todo = get_object_or_404(visible(request.user, self.scope), pk=pk)
        if (
            not can_delete(todo, request.user, self.scope)
            or "todos.edit" not in self.scope.permissions
            or todo.distributed
        ):
            raise PermissionDenied()
        return todo

    def get(self, request, pk, **kwargs):
        todo = self.task(request, pk)
        return Response(
            {
                "version": todo.version,
                "couplings": [
                    {
                        "id": c.pk,
                        "name": c.remote_unit.display_name,
                        "enabled": c.level("todos") == "on",
                    }
                    for c in Coupling.objects.filter(
                        local_unit=self.org, state=Coupling.State.ACTIVE
                    ).select_related("remote_unit")
                ],
                "shares": [
                    {
                        "coupling": s.coupling_id,
                        "mode": s.mode,
                        "active": s.active,
                        "can_complete": s.can_complete,
                        "following": s.following,
                        "progress": s.progress,
                    }
                    for s in todo.remote_shares.all()
                ],
            }
        )

    @transaction.atomic
    def put(self, request, pk, **kwargs):
        self.task(request, pk)
        todo = lock_task(request.user, self.scope, pk)
        ser = ShareInput(data=request.data)
        ser.is_valid(raise_exception=True)
        values = ser.validated_data
        if values.pop("version") != todo.version:
            raise Conflict(gettext("Die Aufgabe wurde inzwischen geändert. Bitte neu laden."))
        coupling = get_object_or_404(
            Coupling.objects.select_for_update(),
            pk=values.pop("coupling"),
            local_unit=self.org,
            state=Coupling.State.ACTIVE,
        )
        if values["active"] and coupling.level("todos") != "on":
            raise PermissionDenied(gettext("Bitte Aufgaben zuerst in der Kopplung freigeben."))
        if todo.per_unit and values["mode"] != "copy" or values["following"] and not todo.series_id:
            raise PermissionDenied()
        previous = TodoRemoteShare.objects.filter(todo=todo, coupling=coupling).first()
        if (
            not previous
            and TodoRemoteShare.objects.filter(coupling=coupling, active=True).count() >= LIMIT
        ):
            raise serializers.ValidationError(
                gettext("Je Kopplung können höchstens 100 Aufgaben gleichzeitig geteilt werden.")
            )
        if previous and previous.mode != values["mode"]:
            raise Conflict(
                gettext(
                    "Die Verteilart einer bereits verteilten Aufgabe kann nicht geändert werden."
                )
            )
        share, _ = TodoRemoteShare.objects.update_or_create(
            todo=todo, coupling=coupling, defaults={"organization": self.org, **values}
        )
        share.revision += 1
        share.save(update_fields=["revision"])
        if share.active:
            todo.shared = True
        todo.version += 1
        todo.save(update_fields=["shared", "version", "updated_at"])
        ctx = active()
        if ctx:
            ctx.block(gettext("Freigaben lassen sich nicht rückgängig machen."))
        services.sync(coupling)
        return self.get(request, pk, **kwargs)


class RemoteInboxView(RemoteScope, APIView):
    def get(self, request, **kwargs):
        if "todos.edit" not in self.scope.permissions or self.scope.department_id:
            raise PermissionDenied()
        from .remote import fresh_offers

        rows = fresh_offers(
            TodoRemoteTask.objects.filter(
                organization=self.org,
                active=True,
                todo__isnull=True,
                coupling__state=Coupling.State.ACTIVE,
            ).select_related("coupling__remote_unit", "coupling__peer", "coupling__local_unit")
        )
        # Übernommene Inhalte folgen ausschließlich ihrer lokalen Aufgaben-ACL.
        return Response(
            {
                "items": [
                    {
                        "id": r.pk,
                        "from": r.coupling.remote_unit.display_name,
                        "mode": r.mode,
                        "title": r.payload.get("title", ""),
                        "description": r.payload.get("description", ""),
                        "due_date": r.payload.get("due_date"),
                        "adopted": bool(r.todo_id),
                    }
                    for r in rows
                    if not r.todo_id
                ]
            }
        )


class RemoteAdoptView(RemoteScope, APIView):
    @transaction.atomic
    def post(self, request, remote_id, **kwargs):
        if "todos.edit" not in self.scope.permissions or self.scope.department_id:
            raise PermissionDenied()
        mapping = get_object_or_404(
            TodoRemoteTask.objects.select_for_update().select_related(
                "coupling__peer", "coupling__local_unit"
            ),
            organization=self.org,
            pk=remote_id,
            active=True,
            todo__isnull=True,
        )
        answer = call(mapping, "todo.read")
        if not answer.get("available"):
            raise PermissionDenied()
        check = SnapshotInput(data=answer["task"])
        check.is_valid(raise_exception=True)
        if check.validated_data["uid"] != mapping.uid:
            raise PermissionDenied()
        with rls_bypass():
            mapping = receive_one(mapping.coupling, _serialize(check.validated_data))
        todo = adopt(mapping, request.user, self.scope)
        return Response(data_for(todo, request.user, self.scope), status=201)


class RemoteFileView(RemoteScope, APIView):
    def get(self, request, pk, att_id, **kwargs):
        todo = get_object_or_404(visible(request.user, self.scope), pk=pk)
        if not todo.remote_origin_id:
            raise PermissionDenied()
        return remote_file(todo, att_id)
