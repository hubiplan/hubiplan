"""Explicit platform-only erasure of one local data area."""

from django.apps import apps
from django.db import models, transaction
from django.db.models.deletion import Collector
from django.utils.translation import gettext
from rest_framework import serializers

from core.files import delete_on_commit
from core.tenancy import rls_bypass
from finance import gobd

from .models import Organization


class ErasureCollector(Collector):
    """Allow protected references only between rows being explicitly erased."""

    def __init__(self, roots):
        super().__init__(using="default")
        self.roots = roots

    def can_fast_delete(self, objs, from_field=None):
        # Visit file fields and deletion signals on every row.
        return False

    def related_objects(self, related_model, related_fields, objs):
        related = super().related_objects(related_model, related_fields, objs)
        if any(field.remote_field.on_delete is models.PROTECT for field in related_fields):
            owned = self.roots.get(related_model)
            if owned is not None:
                # These rows are collected separately. Other tenants' protected
                # references still abort the entire transaction.
                related = related.exclude(pk__in=owned.values("pk"))
        return related


@transaction.atomic
def erase_organization(org, actor):
    with rls_bypass():
        org = Organization.objects.select_for_update().get(pk=org.pk)
        if org.type == Organization.Type.PLATFORM or org.is_remote:
            raise serializers.ValidationError(gettext("Diese Einheit kann nicht gelöscht werden."))
        if Organization.objects.filter(parent=org).exists():
            raise serializers.ValidationError(
                gettext("Bitte zuerst alle untergeordneten Einheiten löschen oder umhängen.")
            )
        roots = {Organization: Organization.objects.filter(pk=org.pk)}
        owners = {}
        for model in apps.get_models():
            if model is Organization or model._meta.proxy or not model._meta.managed:
                continue
            fields = {
                field.name: field
                for field in model._meta.fields
                if field.related_model is Organization
            }
            if "organization" in fields:
                owned = models.Q(organization=org)
                if "scope" in fields and fields["organization"].null:
                    owned |= models.Q(organization__isnull=True, scope=org)
            elif "scope" in fields:
                owned = models.Q(scope=org)
            else:
                continue
            roots[model] = model._base_manager.filter(owned)
            owners[model] = set(roots[model].values_list("pk", flat=True))
        collector = ErasureCollector(roots)
        try:
            for rows in roots.values():
                collector.collect(rows, fail_on_restricted=False)
            for model, instances in collector.data.items():
                if model in owners and any(
                    instance.pk not in owners[model] for instance in instances
                ):
                    raise serializers.ValidationError(
                        gettext(
                            "Andere Einheiten verweisen auf diese Daten. Löschen nicht möglich."
                        )
                    )
            # RESTRICT checks are deferred until every owned row is collected.
            for model, instances in collector.data.items():
                collector.clear_restricted_objects_from_set(model, instances)
            for qs in collector.fast_deletes:
                collector.clear_restricted_objects_from_queryset(qs.model, qs)
            if any(
                objs for fields in collector.restricted_objects.values() for objs in fields.values()
            ):
                raise serializers.ValidationError(
                    gettext("Andere Einheiten verweisen auf diese Daten. Löschen nicht möglich.")
                )
            for model, instances in collector.data.items():
                fields = [f for f in model._meta.fields if isinstance(f, models.FileField)]
                for instance in instances:
                    delete_on_commit(*(getattr(instance, f.name) for f in fields))
            name, pk = org.name, org.pk
            gobd.release_unit(org.pk)
            collector.delete()
        except (models.ProtectedError, models.RestrictedError) as exc:
            raise serializers.ValidationError(
                gettext("Andere Einheiten verweisen auf diese Daten. Löschen nicht möglich.")
            ) from exc
        from audit.log import record

        org.pk = pk
        record(Organization.platform(), actor, "delete", org, {"Einheit": [f"{name} ({pk})", None]})
