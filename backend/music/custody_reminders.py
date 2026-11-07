"""Personal opt-in subscriptions create ordinary private tasks, never another inbox."""

import datetime

from celery import shared_task
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from access.permissions import permissions_in
from audit.log import record
from core.api_base import OrgScopedMixin
from core.i18n import language_of
from core.tenancy import rls_bypass, tenant_context
from todos.models import Todo

from .models import Equipment, EquipmentLoan, MusicReminderPreference, MusicReminderTask, ScoreLoan


class PreferenceInput(serializers.ModelSerializer):
    days_ahead = serializers.IntegerField(min_value=0, max_value=30)

    class Meta:
        model = MusicReminderPreference
        fields = ["enabled", "days_ahead", "scores", "equipment"]


def task_link(todo, scope):
    """Task links follow the active scope, including restricted role previews."""
    if (
        scope.org.pk != todo.organization_id
        or scope.department_id
        or "music.view" not in scope.permissions
        or "music" not in scope.org.enabled_modules
    ):
        return ""
    link = MusicReminderTask.objects.filter(organization=scope.org, todo=todo).first()
    if not link:
        return ""
    if link.kind == "score":
        return (
            f"/musik/proben?notenausgabe={link.source}"
            if ScoreLoan.objects.filter(organization=scope.org, pk=link.source).exists()
            else ""
        )
    if "material.view" not in scope.permissions or "material" not in scope.org.enabled_modules:
        return ""
    if link.kind == "equipment":
        exists = EquipmentLoan.objects.filter(
            organization=scope.org,
            pk=link.source,
            equipment__item__department=None,
            equipment__item__deleted_at=None,
        ).exists()
        return f"/musik/ausstattung?ausleihe={link.source}" if exists else ""
    if link.kind == "maintenance":
        exists = Equipment.objects.filter(
            organization=scope.org, pk=link.source, item__department=None, item__deleted_at=None
        ).exists()
        return f"/musik/ausstattung?wartung={link.source}" if exists else ""
    return ""


def sources(pref, permissions):
    if pref.scores:
        for row in ScoreLoan.objects.filter(
            organization=pref.organization, returned__lt=F("quantity")
        ):
            yield (
                "score",
                row.pk,
                row.due_on,
                gettext("Notenrückgabe prüfen"),
                f"/musik/proben?notenausgabe={row.pk}",
            )
    if (
        pref.equipment
        and "material.view" in permissions
        and "material" in pref.organization.enabled_modules
    ):
        for row in EquipmentLoan.objects.filter(
            organization=pref.organization,
            returned_at=None,
            equipment__item__department=None,
            equipment__item__deleted_at=None,
        ):
            yield (
                "equipment",
                row.pk,
                row.due_date,
                gettext("Ausstattungsrückgabe prüfen"),
                f"/musik/ausstattung?ausleihe={row.pk}",
            )
        for row in Equipment.objects.filter(
            organization=pref.organization,
            item__department=None,
            item__deleted_at=None,
            maintenance_due__isnull=False,
        ):
            yield (
                "maintenance",
                row.pk,
                row.maintenance_due,
                gettext("Wartung der Ausstattung prüfen"),
                f"/musik/ausstattung?wartung={row.pk}",
            )


def untouched(todo, link, pref, status="open"):
    return (
        todo
        and todo.version == link.managed_version
        and todo.status == status
        and todo.deleted_at is None
        and not todo.withdrawn
        and not todo.shared
        and todo.owner_id == pref.user_id
        and todo.created_by_id == pref.user_id
    )


@transaction.atomic
def synchronize(pk):
    pref = (
        MusicReminderPreference.objects.select_for_update(of=("self",))
        .select_related("organization", "user")
        .get(pk=pk)
    )
    perms = permissions_in(pref.user, pref.organization) if pref.user.is_active else set()
    enabled = (
        pref.enabled
        and "music" in (pref.organization.enabled_modules or [])
        and {"music.view", "todos.view", "todos.edit"} <= perms
    )
    with language_of(pref.organization):
        rows = list(sources(pref, perms)) if enabled else []
        active = {(kind, source, deadline) for kind, source, deadline, *_ in rows}
        for link in pref.tasks.select_related("todo"):
            todo = Todo.objects.select_for_update().filter(pk=link.todo_id).first()
            if (link.kind, link.source, link.deadline) in active and link.auto_closed:
                if untouched(todo, link, pref, status="done"):
                    todo.status, todo.done_at, todo.done_by = "open", None, None
                    todo.version += 1
                    todo.save(
                        update_fields=["status", "done_at", "done_by", "version", "updated_at"]
                    )
                    link.managed_version, link.auto_closed = todo.version, False
                    link.save(update_fields=["managed_version", "auto_closed"])
                    record(
                        pref.organization,
                        pref.user,
                        "update",
                        todo,
                        {"Musikerinnerung reaktiviert": [False, True]},
                    )
            elif (link.kind, link.source, link.deadline) not in active:
                if untouched(todo, link, pref):
                    todo.status, todo.done_at, todo.done_by = "done", timezone.now(), pref.user
                    todo.version += 1
                    todo.save(
                        update_fields=["status", "done_at", "done_by", "version", "updated_at"]
                    )
                    link.managed_version, link.auto_closed = todo.version, True
                    link.save(update_fields=["managed_version", "auto_closed"])
                    record(
                        pref.organization,
                        pref.user,
                        "update",
                        todo,
                        {"Musikerinnerung erledigt": [False, True]},
                    )
        cutoff = timezone.localdate() + datetime.timedelta(days=pref.days_ahead)
        created = 0
        for kind, source, deadline, title, url in rows:
            if deadline > cutoff:
                continue
            link, new = MusicReminderTask.objects.get_or_create(
                organization=pref.organization,
                preference=pref,
                kind=kind,
                source=source,
                deadline=deadline,
            )
            if not new:
                continue
            todo = Todo.objects.create(
                organization=pref.organization,
                owner=pref.user,
                created_by=pref.user,
                title=title,
                description=gettext("Im Musikbereich prüfen: {link}\nVorgang: {number}").format(
                    link=url, number=source
                ),
                due_date=deadline,
            )
            link.todo = todo
            link.managed_version = todo.version
            link.save(update_fields=["todo", "managed_version"])
            record(pref.organization, pref.user, "create", todo, {"Musikerinnerung": [None, kind]})
            created += 1
    return created


class CustodyReminderView(OrgScopedMixin, APIView):
    allowed_org_types = ("club", "federation")
    read_permission = "music.view"
    write_permission = "todos.edit"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if "music" not in (self.org.enabled_modules or []):
            raise NotFound()
        if not {"music.view", "todos.view"} <= self.org_permissions:
            raise PermissionDenied()

    def get(self, request, org_id):
        pref = MusicReminderPreference.objects.filter(
            organization=self.org, user=request.user
        ).first()
        return Response(
            PreferenceInput(pref).data
            if pref
            else {"enabled": False, "days_ahead": 7, "scores": True, "equipment": True}
        )

    @transaction.atomic
    def post(self, request, org_id):
        form = PreferenceInput(data=request.data)
        form.is_valid(raise_exception=True)
        pref, _ = MusicReminderPreference.objects.get_or_create(
            organization=self.org, user=request.user
        )
        MusicReminderPreference.objects.select_for_update().get(pk=pref.pk)
        for name, value in form.validated_data.items():
            setattr(pref, name, value)
        pref.save()
        synchronize(pref.pk)
        return Response(PreferenceInput(pref).data)


@shared_task
def custody_reminders():
    with rls_bypass():
        entries = list(
            MusicReminderPreference.objects.values_list("pk", "organization_id", "user_id")
        )
    created = 0
    for pk, org, user in entries:
        with tenant_context(org, user):
            try:
                created += synchronize(pk)
            except MusicReminderPreference.DoesNotExist:
                # The user or subscription may have been removed after enumeration.
                continue
    return created
