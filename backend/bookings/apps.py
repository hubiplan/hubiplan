from django.apps import AppConfig


class BookingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bookings"
    verbose_name = "Buchungen"

    def ready(self):
        from django.db.models.signals import post_save

        from .signals import competition_saved, event_saved

        post_save.connect(event_saved, sender="events.Event", dispatch_uid="booking_event_sync")
        post_save.connect(
            competition_saved,
            sender="competitions.Competition",
            dispatch_uid="booking_competition_sync",
        )
