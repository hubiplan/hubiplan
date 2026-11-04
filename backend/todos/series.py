"""Konkrete Ausgabenfolgen: Serien vor Aufgaben sperren, Kalenderanker erhalten."""

import calendar
import datetime
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext

from changes.tracking import suppress
from core.tenancy import rls_bypass

from .models import Todo, TodoAttachment, TodoReminderConfig, TodoSeries, TodoShare
from .reminders import deadline, sync


def lock_task(user, scope, pk, *, deleted=False):
    from django.shortcuts import get_object_or_404

    from .access import visible

    qs = visible(user, scope, deleted=deleted)
    metadata = get_object_or_404(qs.only("pk", "series_id"), pk=pk)
    if metadata.series_id:
        with rls_bypass():
            TodoSeries.objects.select_for_update().values("pk").get(pk=metadata.series_id)
    return get_object_or_404(qs.select_for_update(), pk=pk)


def require_series_edit(todo, user, scope):
    from rest_framework.exceptions import PermissionDenied

    from .access import local_task, role_ids

    if not todo.series_id:
        return
    with rls_bypass():
        owner = (
            TodoSeries.objects.filter(pk=todo.series_id).values_list("owner_id", flat=True).first()
        )
        future = TodoSeries.objects.only("shares").get(pk=todo.series_id).shares
    if owner == user.pk and local_task(todo, scope):
        return
    roles = role_ids(user, scope)
    permitted = any(
        row.get("target_org_id") == scope.org.pk
        and row.get("target_department_id") == scope.department_id
        and row.get("level") == "edit"
        and (row.get("user_id") == user.pk or row.get("role_id") in roles)
        for row in future
    )
    if not permitted:
        raise PermissionDenied(
            gettext("Für die aktuelle Serienausgabe fehlt dir die Berechtigung.")
        )


def calendar_date(anchor, repeat, interval, n, last_day=False):
    if repeat in {"daily", "weekly"}:
        return anchor + datetime.timedelta(days=n * interval * (7 if repeat == "weekly" else 1))
    months = n * interval * (12 if repeat == "yearly" else 1)
    absolute = anchor.year * 12 + anchor.month - 1 + months
    year, month0 = divmod(absolute, 12)
    last = calendar.monthrange(year, month0 + 1)[1]
    return datetime.date(year, month0 + 1, last if last_day else min(anchor.day, last))


def next_date(series, todo, now=None):
    now = now or timezone.now()
    local_day = now.astimezone(ZoneInfo(series.timezone)).date()
    anchor = local_day if series.basis == "done" else series.anchor_date
    lower = max(todo.due_date, local_day) if series.basis == "due" else local_day
    if series.repeat in {"daily", "weekly"}:
        span = series.interval * (7 if series.repeat == "weekly" else 1)
        n = max(1, (lower - anchor).days // span)
    else:
        months = (lower.year - anchor.year) * 12 + lower.month - anchor.month
        n = max(1, months // (series.interval * (12 if series.repeat == "yearly" else 1)))
    while True:
        try:
            day = calendar_date(anchor, series.repeat, series.interval, n, series.last_day)
        except (ValueError, OverflowError):
            return None
        if series.ends_on and day > series.ends_on:
            return None
        candidate = Todo(due_date=day, due_time=series.due_time, timezone=series.timezone)
        if (series.basis == "done" or day > todo.due_date) and deadline(candidate) > now:
            return day
        n += 1


def reopen_problem(todo):
    with rls_bypass():
        candidates = Todo.objects.filter(
            series_id=todo.series_id, sequence_no__gt=todo.sequence_no, withdrawn=False
        )
        later = list(
            candidates.order_by("sequence_no").values("pk", "status", "version", "deleted_at")
        )
        if not later:
            return None
        changed = candidates.exclude(local_note="").exists()
        changed |= TodoAttachment.objects.filter(
            todo_id__in=candidates.values("pk"), kind="file"
        ).exists()
        changed |= TodoReminderConfig.objects.filter(
            todo_id__in=candidates.values("pk"), customized=True
        ).exists()
    if (
        len(later) != 1
        or later[0]["status"] != "open"
        or later[0]["version"] != 1
        or later[0]["deleted_at"]
        or changed
    ):
        return gettext(
            "Die Folgeausgabe wurde bereits bearbeitet. "
            "Diese Ausgabe kann nicht wieder geöffnet werden."
        )
    return None


def before_save(todo, previous, series):
    if todo.due_date is None:
        raise ValidationError(gettext("Wiederholungen brauchen eine offene Aufgabe mit Frist."))
    if todo.status != "open" or todo.deleted_at or todo.withdrawn:
        return
    if previous and previous.status == "done":
        problem = reopen_problem(todo)
        if problem:
            raise ValidationError(problem)
        with suppress(), rls_bypass():
            successor_ids = Todo.objects.filter(
                series=series, sequence_no__gt=todo.sequence_no, withdrawn=False
            ).values("pk")
            TodoReminderConfig.objects.filter(todo_id__in=successor_ids).update(active=False)
            from .models import TodoReminder

            TodoReminder.objects.filter(todo_id__in=successor_ids, result="pending").update(
                result="cancelled"
            )
            Todo.objects.filter(pk__in=successor_ids).update(
                withdrawn=True, deleted_at=timezone.now(), version=F("version") + 1
            )
            from .models import TodoProgress

            TodoProgress.objects.filter(
                copy_id__in=Todo.objects.filter(
                    series=series, sequence_no__gt=todo.sequence_no, withdrawn=True
                ).values("pk")
            ).delete()
    if (
        Todo.objects.filter(series=series, status="open", deleted_at__isnull=True)
        .exclude(pk=todo.pk)
        .exists()
    ):
        raise ValidationError(gettext("In dieser Serie gibt es bereits eine offene Ausgabe."))


def after_save(todo, previous, series):
    if (
        not previous
        or previous.status != "open"
        or todo.status != "done"
        or todo.deleted_at
        or todo.withdrawn
        or not series.active
        or series.deleted_at
        or series.kind != "sequence"
    ):
        return
    with rls_bypass():
        numbers = list(
            series.occurrences.filter(withdrawn=False).values_list("sequence_no", flat=True)
        )
    if series.count and len(numbers) >= series.count:
        return
    day = next_date(series, todo, todo.done_at or timezone.now())
    if day is None:
        return
    number = max(numbers, default=0) + 1
    with suppress(), rls_bypass():
        if not todo.owner_id and not series.shares:
            TodoSeries.objects.filter(pk=series.pk).update(active=False)
            return
        central_ids = todo.central_attachment_ids
        if todo.remote_origin_id:
            from .remote import usable

            mapping = todo.remote_origin
            if (
                todo.remote_mode != "copy"
                or not mapping.active
                or not usable(mapping.coupling)
                or not mapping.payload.get("following")
                or not (mapping.payload.get("series") or {}).get("active")
            ):
                return
        elif todo.distributed:
            source = (
                Todo.objects.filter(pk=todo.origin_id, deleted_at__isnull=True)
                .defer("local_note")
                .first()
            )
            if (
                source is None
                or not source.shares.filter(
                    target_org_id=todo.organization_id, target_department_id=todo.department_id
                ).exists()
            ):
                return
            if source.series_id and (not source.series.active or source.series.deleted_at):
                return
            from .distribution import attachment_ids

            central_ids = attachment_ids(source, future=True)
        successor = Todo.objects.create(
            organization=series.organization,
            department_id=series.department_id,
            created_by=todo.created_by,
            owner=todo.owner,
            series=series,
            sequence_no=number,
            title=series.title,
            description=series.description,
            due_date=day,
            due_time=series.due_time,
            timezone=series.timezone,
            shared=bool(series.shares),
            origin_id=todo.origin_id,
            distributed=todo.distributed,
            remote_origin_id=todo.remote_origin_id,
            remote_mode=todo.remote_mode,
            central_attachment_ids=central_ids,
        )
        TodoShare.objects.bulk_create(
            [
                TodoShare(organization=successor.organization, todo=successor, **values)
                for values in series.shares
            ]
        )
        TodoAttachment.objects.bulk_create(
            [
                TodoAttachment(
                    organization=successor.organization,
                    department_id=successor.department_id,
                    todo=successor,
                    kind="document",
                    document_id=pk,
                )
                for pk in series.documents
            ]
        )
        for config in todo.reminder_configs.all():
            current, _ = TodoReminderConfig.objects.get_or_create(
                organization=successor.organization,
                todo=successor,
                user_id=config.user_id,
            )
            for key in ("days", "enabled", "mail", "push"):
                setattr(current, key, getattr(config, key))
            current.revision += 1
            current.save()
        sync(successor)


def snapshot_template(todo, series):
    if not todo.distributed:
        for key in ("title", "description", "due_time", "timezone"):
            setattr(series, key, getattr(todo, key))
    with rls_bypass():
        series.shares = list(
            todo.shares.order_by("pk").values(
                "user_id",
                "role_id",
                "target_org_id",
                "target_department_id",
                "level",
                "responsible",
            )
        )
        series.documents = list(
            todo.attachments.filter(
                kind="document", deleted_at__isnull=True, document__isnull=False
            ).values_list("document_id", flat=True)
        )


@transaction.atomic
def update_template(todo, *, reset_anchor=False, fields=(), shares=False, documents=False):
    if not todo.series_id:
        return
    with rls_bypass():
        series = TodoSeries.objects.select_for_update().get(pk=todo.series_id)
        if not todo.distributed:
            for key in set(fields) & {"title", "description", "due_time", "timezone"}:
                setattr(series, key, getattr(todo, key))
        if shares:
            series.shares = list(
                todo.shares.order_by("pk").values(
                    "user_id",
                    "role_id",
                    "target_org_id",
                    "target_department_id",
                    "level",
                    "responsible",
                )
            )
        if documents:
            series.documents = list(
                todo.attachments.filter(
                    kind="document", deleted_at__isnull=True, document__isnull=False
                ).values_list("document_id", flat=True)
            )
        if reset_anchor:
            series.anchor_date = todo.due_date
        series.owner = todo.owner
        series.version += 1
        series.save()


def undo_problem(todo, rec):
    if not todo.series_id:
        return None
    if rec.operation != "update":
        return gettext("Bitte diese Serie über ihren Serien-Papierkorb verwalten.")
    if (rec.before or {}).get("status") == "open" and todo.status == "done":
        return reopen_problem(todo)
    return None
