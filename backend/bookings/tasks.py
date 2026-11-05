from celery import shared_task
from django.db import transaction
from django.utils import timezone

from core.tenancy import rls_bypass


@shared_task
def extend_series():
    """Serienbuchungen täglich bis zum Horizont (zwei Jahre) weiter ausrechnen."""
    from .models import Booking
    from .services import rebuild

    with rls_bypass():
        for booking in (
            Booking.objects.exclude(repeat="none")
            .filter(status__in=[Booking.Status.REQUESTED, Booking.Status.CONFIRMED])
            .exclude(repeat_until__lt=timezone.localdate())
        ):
            with transaction.atomic():
                rebuild(booking, strict=False)
