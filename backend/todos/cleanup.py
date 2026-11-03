from django.db import transaction
from django.utils import timezone

from changes.tracking import suppress
from core.tenancy import rls_bypass

from .models import Todo, TodoCleanupSetting, TodoPreference


@transaction.atomic
def completed(now=None):
    now = now or timezone.now()
    try:
        cutoff = now.replace(year=now.year - 1)
    except ValueError:
        cutoff = now.replace(year=now.year - 1, day=28)
    with rls_bypass(), suppress():
        eligible = Todo.objects.filter(status="done", done_at__lt=cutoff, deleted_at__isnull=True)
        if hasattr(Todo, "series"):
            eligible = eligible.filter(series__isnull=True)
        private_users = TodoPreference.objects.filter(purge_done=True).values("user_id")
        ids = set(
            eligible.filter(shared=False, owner_id__in=private_users).values_list("pk", flat=True)
        )
        for setting in TodoCleanupSetting.objects.filter(purge_done=True):
            ids.update(
                eligible.filter(
                    shared=True,
                    organization_id=setting.organization_id,
                    department_id=setting.department_id,
                ).values_list("pk", flat=True)
            )
        for todo in eligible.filter(pk__in=ids).select_for_update():
            todo.deleted_at = now
            todo.version += 1
            todo.save(update_fields=["deleted_at", "version", "updated_at"])
    return len(ids)
