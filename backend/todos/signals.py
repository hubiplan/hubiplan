"""Kontolöschung entfernt private Inhalte einschließlich ihrer Rückgängig-Daten."""

from django.db.models.signals import post_save, pre_delete, pre_save


def erase_private(sender, instance, **kwargs):
    from changes.models import ChangeSet
    from changes.tracking import suppress
    from core.tenancy import rls_bypass

    from .models import Todo

    with suppress(), rls_bypass():
        ids = list(
            Todo.objects.filter(created_by=instance, shared=False).values_list("pk", flat=True)
        )
        sets = ChangeSet.objects.filter(
            records__model="todos.todo", records__object_id__in=[str(pk) for pk in ids]
        )
        sets.delete()
        Todo.objects.filter(pk__in=ids).delete()


def connect():
    from accounts.models import User

    pre_delete.connect(erase_private, sender=User, dispatch_uid="todos_erase_private")
    from .models import Todo

    pre_save.connect(check_reminder_changes, sender=Todo, dispatch_uid="todos_reminder_changes")
    post_save.connect(plan_reminders, sender=Todo, dispatch_uid="todos_plan_reminders")


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
