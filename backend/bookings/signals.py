"""Verknüpfte Buchungen folgen ihrem Termin oder Wettbewerb."""

from django.db.models import F

from core.tenancy import rls_bypass


def _follow(bookings, apply, cancelled):
    from .models import Booking
    from .services import rebuild

    for booking in bookings.filter(
        status__in=[Booking.Status.REQUESTED, Booking.Status.CONFIRMED]
    ).select_related("item"):
        if cancelled:
            booking.status = Booking.Status.CANCELLED
        else:
            apply(booking)
        booking.version = F("version") + 1
        booking.save()
        booking.refresh_from_db()
        rebuild(booking, strict=False)


def event_saved(sender, instance, created=False, raw=False, **kwargs):
    if created or raw:
        return
    from .services import copy_times

    with rls_bypass():
        _follow(instance.bookings.all(), lambda b: copy_times(b, instance), instance.is_cancelled)


def competition_saved(sender, instance, created=False, raw=False, **kwargs):
    if created or raw:
        return
    from .services import competition_times

    with rls_bypass():
        _follow(instance.bookings.all(), lambda b: competition_times(b, instance), cancelled=False)
