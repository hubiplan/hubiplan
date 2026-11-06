from django.apps import AppConfig


class MeetingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "meetings"
    verbose_name = "Versammlungen"

    def ready(self):
        from django.db.models.signals import post_save

        from .signals import circular_saved

        post_save.connect(
            circular_saved, sender="circulars.Circular", dispatch_uid="meeting_invitation_sent"
        )
