"""Zusatzfelder für Geschäftspartner.

Aufgebaut wie die Zusatzfelder der Mitglieder (``customfields``): Typen, Auswahllisten,
wiederholbare Felder mit Unterfeldern, Archivieren und Löschen samt Werten. Die Felder
gehören einer Einheit; Werte stehen verschlüsselt je Partner in ``PartnerFieldValue``.

- ``…/billing/partner-fields/``: Felder (lesen mit Geschäftspartner-Leserecht, ändern mit
  Bearbeitungsrecht)
- ``…/billing/partners/<pk>/fields/``: Werte eines Partners lesen (GET) und speichern (PUT)
"""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from customfields.models import TYPES, clean_value
from customfields.views import FieldDefinitionSerializer, FieldDefinitionViewSet

from .models import BusinessPartner, PartnerField, PartnerFieldValue
from .partners import PartnerAccess


class PartnerFieldSerializer(FieldDefinitionSerializer):
    class Meta:
        model = PartnerField
        fields = [
            "id",
            "label",
            "key",
            "field_type",
            "choices",
            "repeatable",
            "subfields",
            "federation_wide",
            "help_text",
            "sort_order",
            "is_archived",
            "inherited",
            "owner_name",
            "in_use",
        ]

    federation_wide = serializers.SerializerMethodField()
    field_type = serializers.ChoiceField(choices=TYPES, required=False)

    def get_federation_wide(self, obj) -> bool:
        return False

    def get_inherited(self, obj) -> bool:
        return False


class PartnerFieldViewSet(PartnerAccess, FieldDefinitionViewSet):
    serializer_class = PartnerFieldSerializer
    read_permission = PartnerAccess.read_permission
    write_permission = PartnerAccess.write_permission
    allowed_org_types = PartnerAccess.allowed_org_types

    def get_queryset(self):
        return PartnerField.objects.filter(organization=self.org).select_related("organization")


def active_fields(org) -> list[PartnerField]:
    return list(PartnerField.objects.filter(organization=org, is_archived=False))


def save_values(org, partner, incoming: dict, definitions: dict) -> tuple[dict, dict]:
    """Werte prüfen und speichern. Gibt Fehler je Feld und Änderungen fürs Protokoll zurück."""
    errors, changes = {}, {}
    current = {v.definition_id: v for v in PartnerFieldValue.objects.filter(partner=partner)}
    for def_id, raw in incoming.items():
        definition = definitions.get(str(def_id))
        if definition is None:
            errors[str(def_id)] = gettext("Unbekanntes Feld.")
            continue
        try:
            value = clean_value(definition, raw)
        except DjangoValidationError as exc:
            errors[str(def_id)] = " ".join(exc.messages)
            continue
        row = current.get(definition.pk)
        old = row.value if row else None
        if value in (None, []):
            if row:
                row.delete()
        elif row:
            if row.value != value:
                row.value = value
                row.save(update_fields=["value", "updated_at"])
        else:
            PartnerFieldValue.objects.create(
                organization=org, definition=definition, partner=partner, value=value
            )
        if old != value and not (old is None and value in (None, [])):
            changes[definition.label] = [old, value]
    return errors, changes


class PartnerFieldsView(PartnerAccess, APIView):
    """Abschnitt „Zusatzfelder“ in der Akte eines Geschäftspartners."""

    def partner(self) -> BusinessPartner:
        return get_object_or_404(BusinessPartner, organization=self.org, pk=self.kwargs["pk"])

    def payload(self, partner: BusinessPartner) -> list[dict]:
        definitions = active_fields(self.org)
        values = {
            v.definition_id: v.value for v in PartnerFieldValue.objects.filter(partner=partner)
        }
        ctx = {"org": self.org}
        return [
            {
                "definition": PartnerFieldSerializer(d, context=ctx).data,
                "value": values.get(d.pk, [] if d.repeatable else None),
            }
            for d in definitions
        ]

    def get(self, request, org_id: int, pk: int):
        return Response(self.payload(self.partner()))

    @transaction.atomic
    def put(self, request, org_id: int, pk: int):
        partner = self.partner()
        incoming = request.data.get("values", {})
        if not isinstance(incoming, dict):
            raise serializers.ValidationError({"values": gettext("Ungültige Daten.")})
        definitions = {str(d.pk): d for d in active_fields(self.org)}
        errors, changes = save_values(self.org, partner, incoming, definitions)
        if errors:
            raise serializers.ValidationError(errors)
        if changes:
            record(self.org, request.user, "update", partner, changes)
        return Response(self.payload(partner))


def merge_values(keep: BusinessPartner, other: BusinessPartner) -> None:
    """Beim Zusammenführen: Werte des zweiten Eintrags übernehmen, wo der bleibende keine hat."""
    taken = set(
        PartnerFieldValue.objects.filter(partner=keep).values_list("definition_id", flat=True)
    )
    PartnerFieldValue.objects.filter(partner=other, definition_id__in=taken).delete()
    PartnerFieldValue.objects.filter(partner=other).update(partner=keep)
