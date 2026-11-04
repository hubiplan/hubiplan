from django.db.models import F

from core.tenancy import rls_bypass


def member_removed(sender, instance, **kwargs):
    """Nur Referenzen bereinigen, niemals gelöschte Personendaten im Verlauf behalten."""
    if kwargs.get("signal") is not None and not getattr(instance, "purged_at", None):
        from django.db.models.signals import pre_delete

        if kwargs["signal"] is not pre_delete:
            return
    from .models import MaterialItem, MaterialRevision

    with rls_bypass():
        affected = MaterialItem.objects.filter(member_id=instance.pk)
        MaterialRevision.objects.filter(item__in=affected).delete()
        affected.update(member=None, location_kind="unknown", version=F("version") + 1)


def photo_deleted(sender, instance, **kwargs):
    from .services import delete_photo_files

    delete_photo_files([instance])
