import datetime

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from core.tenancy import rls_bypass

from .models import MaterialItem, MaterialPhoto, MaterialRevision
from .services import delete_photo_files


@shared_task
def purge_deleted():
    cutoff = timezone.now() - datetime.timedelta(days=30)
    with transaction.atomic(), rls_bypass():
        items = MaterialItem.objects.filter(deleted_at__lt=cutoff)
        from music.models import EquipmentLoan

        items = items.exclude(
            pk__in=EquipmentLoan.objects.filter(returned_at=None).values_list(
                "equipment__item_id", flat=True
            )
        )
        photos = MaterialPhoto.objects.filter(item__in=items) | MaterialPhoto.objects.filter(
            deleted_at__lt=cutoff
        )
        delete_photo_files(list(photos))
        photos.delete()
        items.delete()
        MaterialRevision.objects.filter(created_at__lt=cutoff).delete()
