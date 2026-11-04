import datetime

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from changes.tracking import suppress
from core.tenancy import rls_bypass

from .models import Todo, TodoAttachment, TodoSeries


@shared_task
@transaction.atomic
def purge_deleted():
    cutoff = timezone.now() - datetime.timedelta(days=30)
    with suppress(), rls_bypass():
        for series in (
            TodoSeries.objects.filter(deleted_at__lt=cutoff).select_for_update().order_by("pk")
        ):
            series.delete()
        rows = list(
            Todo.objects.filter(series__isnull=True, deleted_at__lt=cutoff).select_for_update()
        )
        count = len(rows)
        for row in rows:
            row.delete()
        for attachment in TodoAttachment.objects.filter(
            Q(todo__series__isnull=True) | Q(todo__deleted_at__isnull=True), deleted_at__lt=cutoff
        ).select_for_update():
            attachment.delete()
    return count


@shared_task
def send_due_reminders():
    from .reminders import run

    return run()


@shared_task
def purge_completed():
    from .cleanup import completed

    return completed()
