from django.apps import AppConfig


class FeeproofsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "feeproofs"
    verbose_name = "Beitragsnachweise"

    def ready(self):
        from django.db.models.signals import post_delete

        from .models import ApplicationProof, FeeProof

        def drop(sender, instance, **kwargs):
            # Auch beim Löschen über Mitgliedschaft oder Antrag (CASCADE) die Datei entfernen
            if instance.file:
                from core.files import delete_on_commit

                delete_on_commit(instance.file)

        post_delete.connect(drop, sender=FeeProof, dispatch_uid="feeproof-file")
        post_delete.connect(drop, sender=ApplicationProof, dispatch_uid="application-proof-file")
