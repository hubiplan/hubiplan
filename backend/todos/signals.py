"""Kontolöschung entfernt private Inhalte einschließlich ihrer Rückgängig-Daten."""

from django.db.models.signals import post_save, pre_delete, pre_save


def erase_private(sender, instance, **kwargs):
    from changes.models import ChangeSet
    from changes.tracking import suppress
    from core.tenancy import rls_bypass

    from .models import Todo, TodoSeries

    with suppress(), rls_bypass():
        ids = list(
            Todo.objects.filter(created_by=instance, shared=False).values_list("pk", flat=True)
        )
        sets = ChangeSet.objects.filter(
            records__model="todos.todo", records__object_id__in=[str(pk) for pk in ids]
        )
        sets.delete()
        Todo.objects.filter(pk__in=ids).delete()
        TodoSeries.objects.filter(owner=instance, occurrences__isnull=True).delete()


def connect():
    from accounts.models import User

    pre_delete.connect(erase_private, sender=User, dispatch_uid="todos_erase_private")
    from .models import Todo, TodoAttachment, TodoSeries

    pre_save.connect(check_reminder_changes, sender=Todo, dispatch_uid="todos_reminder_changes")
    post_save.connect(plan_reminders, sender=Todo, dispatch_uid="todos_plan_reminders")
    post_save.connect(publish_progress, sender=Todo, dispatch_uid="todos_publish_progress")
    post_save.connect(series_progress, sender=TodoSeries, dispatch_uid="todos_series_progress")
    pre_delete.connect(stop_distribution, sender=Todo, dispatch_uid="todos_stop_distribution")
    pre_delete.connect(
        stop_target_series, sender=TodoSeries, dispatch_uid="todos_stop_target_series"
    )
    from django.db.models.signals import post_delete

    post_delete.connect(
        delete_attachment, sender=TodoAttachment, dispatch_uid="todos_delete_attachment"
    )


def delete_attachment(sender, instance, **kwargs):
    from core.files import delete_on_commit

    delete_on_commit(instance.file)


def publish_progress(sender, instance, raw=False, **kwargs):
    if not raw:
        from .distribution import publish

        publish(instance)


def series_progress(sender, instance, raw=False, **kwargs):
    if not raw:
        from core.tenancy import rls_bypass

        from .models import TodoProgress, TodoSeries

        with rls_bypass():
            TodoProgress.objects.filter(copy__series=instance).update(
                ended=not instance.active or bool(instance.deleted_at)
            )
            if not instance.active or instance.deleted_at:
                TodoSeries.objects.filter(source_series=instance).update(active=False)
                TodoProgress.objects.filter(copy__series__source_series=instance).update(ended=True)


def stop_distribution(sender, instance, **kwargs):
    if instance.per_unit and not instance.distributed:
        from .distribution import stop_targets

        stop_targets(instance)


def stop_target_series(sender, instance, **kwargs):
    from core.tenancy import rls_bypass

    from .models import TodoSeries

    with rls_bypass():
        TodoSeries.objects.filter(source_series=instance).update(active=False)


def check_reminder_changes(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw or getattr(instance, "_refresh_reminders", False):
        return
    fields = ("due_date", "due_time", "timezone", "status", "deleted_at", "owner_id", "shared")
    if update_fields is not None and not (set(fields) | {"owner"}) & set(update_fields):
        instance._refresh_reminders = False
        return
    before = (
        sender._base_manager.filter(pk=instance.pk).values(*fields).first() if instance.pk else None
    )
    instance._refresh_reminders = before is None or any(
        before[field] != getattr(instance, field) for field in fields
    )


def plan_reminders(sender, instance, raw=False, **kwargs):
    if not raw and instance.__dict__.pop("_refresh_reminders", True):
        from .reminders import sync

        sync(instance)
