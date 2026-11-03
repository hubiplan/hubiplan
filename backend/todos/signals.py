"""Kontolöschung entfernt private Inhalte einschließlich ihrer Rückgängig-Daten."""

from django.db.models.signals import post_save, pre_delete


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

    post_save.connect(plan_reminders, sender=Todo, dispatch_uid="todos_plan_reminders")


def plan_reminders(sender, instance, raw=False, **kwargs):
    if not raw:
        from .reminders import sync

        sync(instance)
