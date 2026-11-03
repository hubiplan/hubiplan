import datetime

from celery import shared_task
from django.utils import timezone

from changes.tracking import suppress
from core.tenancy import rls_bypass

from .models import Todo


@shared_task
def purge_deleted():
    cutoff = timezone.now() - datetime.timedelta(days=30)
    with suppress(), rls_bypass():
        rows = Todo.objects.filter(deleted_at__lt=cutoff)
        count = rows.count()
        rows.delete()
    return count
