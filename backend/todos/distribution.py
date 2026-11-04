"""Eigene Zielbestände; zurück zur Quelle fließen ausschließlich Fortschrittsfelder."""

from collections import defaultdict

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework.exceptions import ValidationError

from changes.tracking import suppress
from core.encfields import update_encrypted
from core.tenancy import rls_bypass, tenant_context
from organizations.models import Organization

from .access import Scope
from .models import Todo, TodoProgress, TodoSeries, TodoShare
from .sharing import participants

CENTRAL = {"title", "description", "due_date", "due_time", "timezone"}
RULE = (
    "anchor_date",
    "repeat",
    "interval",
    "basis",
    "last_day",
    "ends_on",
    "count",
    "due_time",
    "timezone",
)


def set_mode(todo, scope, requested, shares):
    from .targets import target_scope

    foreign = any(
        (target_scope(scope, row).org.pk, target_scope(scope, row).department_id)
        != (scope.org.pk, scope.department_id)
        for row in (shares or [])
    )
    mode = todo.per_unit if requested is None else requested
    with rls_bypass():
        published = todo.pk and todo.progress.exists()
        previously_foreign = bool(
            todo.pk
            and todo.shares.exclude(
                target_org_id=todo.organization_id, target_department_id=todo.department_id
            ).exists()
        )
    if requested is None and foreign and not previously_foreign:
        mode = True
    if (published or previously_foreign) and mode != todo.per_unit:
        raise ValidationError(
            gettext("Die Verteilart einer bereits verteilten Aufgabe kann nicht geändert werden.")
        )
    if mode and foreign and todo.status != "open":
        raise ValidationError(gettext("Bitte eine offene Aufgabe verteilen."))
    todo.per_unit = mode


def attachment_ids(source, *, future=False):
    rows = source.attachments.filter(deleted_at__isnull=True)
    if future and source.series_id:
        rows = rows.filter(Q(kind="file") | Q(document_id__in=source.series.documents))
    return list(rows.order_by("pk").values_list("pk", flat=True))


def publish(todo):
    if not todo.distributed or not todo.origin_id or todo.withdrawn:
        return
    with rls_bypass(), suppress():
        source_org = (
            Todo.objects.filter(pk=todo.origin_id).values_list("organization_id", flat=True).first()
        )
        if source_org is None:
            return
        ended = bool(
            todo.series_id
            and not TodoSeries.objects.filter(
                pk=todo.series_id, active=True, deleted_at__isnull=True
            ).exists()
        )
        TodoProgress.objects.update_or_create(
            copy=todo,
            defaults={
                "organization_id": source_org,
                "source_id": todo.origin_id,
                "target_org_id": todo.organization_id,
                "target_department_id": todo.department_id,
                "sequence_no": todo.sequence_no or 1,
                "due_date": todo.due_date,
                "status": todo.status,
                "done_at": todo.done_at,
                "done_by_id": todo.done_by_id,
                "ended": ended,
                "deleted": bool(todo.deleted_at),
            },
        )


def stop_targets(source):
    with rls_bypass(), suppress():
        ids = list(
            Todo.objects.filter(origin=source, series__isnull=False).values_list(
                "series_id", flat=True
            )
        )
        TodoSeries.objects.filter(pk__in=ids).update(active=False)
        TodoProgress.objects.filter(source=source).update(ended=True)


def _target_series(source, org, dept_id, owner_id, shares):
    if not source.series_id:
        return None
    template = source.series
    return TodoSeries.objects.create(
        organization=org,
        department_id=dept_id,
        owner_id=owner_id,
        source_series=template,
        title=template.title,
        description=template.description,
        shares=shares,
        active=template.active,
        **{key: getattr(template, key) for key in RULE},
    )


@transaction.atomic
def reconcile(source, *, changed=(), attachments=False):
    if not source.per_unit or source.distributed:
        return
    if source.deleted_at:
        stop_targets(source)
        return
    from .notify import schedule_shared
    from .reminders import sync
    from .sharing import all_participants

    with rls_bypass(), suppress():
        groups = defaultdict(list)
        for share in source.shares.order_by("pk"):
            unit = (share.target_org_id, share.target_department_id)
            if unit != (source.organization_id, source.department_id):
                groups[unit].append(
                    {
                        key: getattr(share, key)
                        for key in (
                            "user_id",
                            "role_id",
                            "target_org_id",
                            "target_department_id",
                            "level",
                            "responsible",
                        )
                    }
                )
        if source.series_id:
            TodoSeries.objects.filter(pk=source.series_id).update(kind="template")
        current_ids = attachment_ids(source)
        for (org_id, dept_id), shares in sorted(
            groups.items(), key=lambda item: (item[0][0], item[0][1] or 0)
        ):
            org = Organization.objects.get(pk=org_id)
            metadata = (
                source.progress.filter(target_org_id=org_id, target_department_id=dept_id)
                .order_by("sequence_no")
                .values("copy_id")
                .first()
            )
            if metadata is None:
                with tenant_context(org_id):
                    people = participants(source, Scope(org, dept_id, set()))
                owner = next((uid for uid, person in people.items() if person["edit"]), None)
                series = _target_series(source, org, dept_id, owner, shares)
                copy = Todo.objects.create(
                    organization=org,
                    department_id=dept_id,
                    created_by_id=owner,
                    owner_id=owner,
                    title=source.title,
                    description=source.description,
                    due_date=source.due_date,
                    due_time=source.due_time,
                    timezone=source.timezone,
                    shared=True,
                    origin=source,
                    distributed=True,
                    central_attachment_ids=current_ids,
                    series=series,
                    sequence_no=1 if series else None,
                )
                TodoShare.objects.bulk_create(
                    [TodoShare(organization=org, todo=copy, **row) for row in shares]
                )
                publish(copy)
                sync(copy)
                schedule_shared(copy, set(all_participants(copy)), include_creator=True)
                continue
            copies = Todo.objects.filter(
                origin=source, organization=org, department_id=dept_id, withdrawn=False
            )
            series_ids = list(
                copies.exclude(series__isnull=True).values_list("series_id", flat=True).distinct()
            )
            if source.series_id and not series_ids:
                first = copies.order_by("pk").values("pk", "owner_id").first()
                if first:
                    series = _target_series(source, org, dept_id, first["owner_id"], shares)
                    Todo.objects.filter(pk=first["pk"]).update(series=series, sequence_no=1)
                    series_ids = [series.pk]
            # Einheitliche Reihenfolge: Zielserien vor ihren Ausgaben sperren.
            for target in (
                TodoSeries.objects.filter(pk__in=series_ids).select_for_update().order_by("pk")
            ):
                if source.series_id:
                    template = source.series
                    for key in (*RULE, "title", "description"):
                        setattr(target, key, getattr(template, key))
                    target.active = (
                        template.active and not target.locally_stopped and not target.deleted_at
                    )
                    target.version += 1
                    target.save()
            open_copies = copies.filter(status="open", deleted_at__isnull=True)
            ids = list(open_copies.select_for_update().order_by("pk").values_list("pk", flat=True))
            updates = {key: getattr(source, key) for key in set(changed) & CENTRAL}
            if attachments:
                updates["central_attachment_ids"] = current_ids
            if updates and ids:
                if set(updates) & {"due_date", "due_time", "timezone"}:
                    updates["due_revision"] = F("due_revision") + 1
                update_encrypted(
                    Todo.objects.filter(pk__in=ids),
                    **updates,
                    version=F("version") + 1,
                    updated_at=timezone.now(),
                )
                for item in Todo.objects.filter(pk__in=ids).defer("local_note"):
                    publish(item)
                    sync(item)
        # Rücknahme einer Zieleinheit beendet weitere Ausgaben; lokaler Bestand bleibt dort.
        for row in source.progress.values("copy_id", "target_org_id", "target_department_id"):
            if (row["target_org_id"], row["target_department_id"]) not in groups:
                series_id = (
                    Todo.objects.filter(pk=row["copy_id"])
                    .values_list("series_id", flat=True)
                    .first()
                )
                if series_id:
                    TodoSeries.objects.filter(pk=series_id).update(active=False)
                TodoProgress.objects.filter(copy_id=row["copy_id"]).update(ended=True)


def current_source(copy):
    """Aufrufer hat die Kopie bereits mit visible() geprüft; keine fremden lokalen Daten."""
    from core.tenancy import task_source

    if not copy.distributed or not copy.origin_id:
        return None
    with rls_bypass():
        still_distributed = TodoShare.objects.filter(
            todo_id=copy.origin_id,
            target_org_id=copy.organization_id,
            target_department_id=copy.department_id,
        ).exists()
    if not still_distributed:
        return None
    with task_source(copy.origin_id):
        return (
            Todo.objects.filter(pk=copy.origin_id, deleted_at__isnull=True, per_unit=True)
            .defer("local_note")
            .first()
        )


def reconcile_series(series):
    with rls_bypass():
        sources = list(
            Todo.objects.filter(series=series, per_unit=True, distributed=False).defer("local_note")
        )
        for source in sources:
            reconcile(source)
