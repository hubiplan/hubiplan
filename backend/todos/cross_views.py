from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from changes.models import ChangeRecord, ChangeSet
from changes.tracking import active
from changes.undo import UndoProblem, undo
from core.tenancy import rls_bypass, task_undo
from organizations.models import Organization

from .access import local_task, undo_problem, visible
from .series import lock_task
from .views import TodoScopeMixin


class ProgressView(TodoScopeMixin, APIView):
    def get(self, request, pk, **kwargs):
        todo = get_object_or_404(visible(request.user, self.scope), pk=pk)
        if not todo.per_unit or todo.distributed or not local_task(todo, self.scope):
            raise NotFound()
        rows = list(
            todo.progress.order_by("sequence_no", "target_org_id", "target_department_id").values(
                "target_org_id",
                "target_department_id",
                "sequence_no",
                "due_date",
                "status",
                "done_at",
                "done_by_id",
                "ended",
                "deleted",
            )
        )
        ids = {row["target_department_id"] or row["target_org_id"] for row in rows}
        names = dict(Organization.objects.filter(pk__in=ids).values_list("pk", "name"))
        for row in rows:
            row["unit"] = names.get(row["target_department_id"] or row["target_org_id"], "")
        return Response({"items": rows})


class TaskUndoView(TodoScopeMixin, APIView):
    @transaction.atomic
    def post(self, request, pk, set_id, **kwargs):
        todo = lock_task(request.user, self.scope, pk, deleted=bool(request.data.get("trash")))
        # Vor dem Öffnen der Rohwerte nur Akteur und betroffene Modell-/Objektnummern lesen.
        with rls_bypass():
            found = ChangeSet.objects.filter(
                pk=set_id, user=request.user, organization_id=todo.organization_id
            ).exists()
            metadata = (
                list(
                    ChangeRecord.objects.filter(change_set_id=set_id).values_list(
                        "model", "object_id"
                    )
                )
                if found
                else []
            )
        if (
            not found
            or not metadata
            or any(
                model != "todos.todo" or object_id != str(todo.pk) for model, object_id in metadata
            )
        ):
            raise NotFound()
        with task_undo(set_id):
            change_set = get_object_or_404(ChangeSet, pk=set_id)
            problem = undo_problem(change_set, request.user, self.scope)
            if problem:
                raise PermissionDenied(problem)
            try:
                undo(
                    change_set,
                    todo.organization,
                    request.user,
                    force=bool(request.data.get("force")),
                )
            except UndoProblem as exc:
                return Response(
                    {
                        "detail": gettext("Das lässt sich nicht ohne Weiteres rückgängig machen."),
                        "problems": exc.messages,
                        "can_force": exc.can_force,
                    },
                    status=409,
                )
        ctx = active()
        return Response({"change_set": str(ctx.set_id) if ctx else None})
