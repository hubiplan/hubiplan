from django.apps import AppConfig


class PinboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pinboard"
    verbose_name = "Pinnwand"

    def ready(self):
        from django.db.models.signals import post_delete

        from .services import photo_deleted

        post_delete.connect(
            photo_deleted, sender="pinboard.NoticePhoto", dispatch_uid="pinboard_photo_delete"
        )
