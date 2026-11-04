from django.apps import AppConfig


class MaterialsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "materials"

    def ready(self):
        from django.db.models.signals import post_delete, post_save, pre_delete

        from .signals import member_removed, photo_deleted

        post_delete.connect(
            photo_deleted, sender="materials.MaterialPhoto", dispatch_uid="material_photo_delete"
        )

        post_save.connect(
            member_removed, sender="members.Membership", dispatch_uid="material_member_purge"
        )
        pre_delete.connect(
            member_removed, sender="members.Membership", dispatch_uid="material_member_delete"
        )
