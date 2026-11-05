"""Music custody and maintenance reuse inventory identity, permissions and revisions."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from changes import idempotency
from core.api_base import OrgScopedMixin
from materials import access, services
from materials.serializers import ItemInput

from .models import Equipment, EquipmentLoan, EquipmentMaintenance, Musician

CONDITIONS = ["ready", "limited", "defective", "retired"]


def name(musician):
    return str(musician.membership.person) if musician.membership_id else musician.name


def data(equipment, include_location=False):
    item = equipment.item
    loans = list(
        equipment.loans.select_related("musician__membership__person").order_by("-pk")[:100]
    )
    active = next((row for row in loans if row.returned_at is None), None)
    return {
        "id": equipment.pk,
        "item": item.pk,
        "number": item.inventory_number,
        "title": item.title,
        "kind": equipment.kind,
        "instrument": equipment.instrument,
        "size": equipment.size,
        "version": item.version,
        "condition": item.condition,
        "condition_note": item.condition_note,
        "maintenance_due": equipment.maintenance_due,
        "maintenance_overdue": bool(
            equipment.maintenance_due and equipment.maintenance_due <= timezone.localdate()
        ),
        "active_loan": active.pk if active else None,
        "return_location": active.location_before if active and include_location else None,
        "loans": [
            {
                "id": row.pk,
                "musician": row.musician_id,
                "name": name(row.musician),
                "issued_at": row.issued_at,
                "due_date": row.due_date,
                "returned_at": row.returned_at,
                "overdue": not row.returned_at and row.due_date < timezone.localdate(),
                "issue_condition": row.issue_condition,
                "return_condition": row.return_condition,
                "note": row.note,
                "return_note": row.return_note,
            }
            for row in loans
        ],
        "maintenance": list(
            equipment.maintenance.order_by("-date", "-pk").values(
                "id", "date", "next_due", "condition", "note"
            )[:100]
        ),
    }


class EquipmentInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["instrument", "uniform"])
    instrument = serializers.CharField(max_length=100, allow_blank=True, default="")
    size = serializers.CharField(max_length=100, allow_blank=True, default="")
    maintenance_due = serializers.DateField(allow_null=True, default=None)


class EquipmentView(OrgScopedMixin, APIView):
    read_permission = "music.view"
    write_permission = "music.edit"
    allowed_org_types = ("club", "federation")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not {"music", "material"} <= set(self.org.enabled_modules):
            raise NotFound()
        write = request.method not in ["GET", "HEAD", "OPTIONS"]
        if ("material.edit" if write else "material.view") not in self.org_permissions:
            raise PermissionDenied()
        self.scope = access.scope_for(request.user, self.org.pk, write=write)

    def rows(self):
        return Equipment.objects.filter(
            organization=self.org, item__in=access.items(self.scope)
        ).select_related("item")

    def get(self, request, org_id):
        return Response(
            {
                "items": [
                    data(row, {"music.edit", "material.edit"} <= self.org_permissions)
                    for row in self.rows().order_by("pk")
                ],
                "available": [
                    {
                        "id": row.pk,
                        "title": row.title,
                        "number": row.inventory_number,
                        "version": row.version,
                    }
                    for row in access.items(self.scope)
                    .filter(music_equipment__isnull=True)
                    .order_by("pk")
                ],
                "musicians": [
                    {"id": row.pk, "name": name(row)}
                    for row in Musician.objects.filter(
                        organization=self.org, active=True
                    ).select_related("membership__person")
                ],
            }
        )

    @transaction.atomic
    def post(self, request, org_id):
        action = serializers.ChoiceField(
            choices=["register", "profile", "issue", "return", "maintenance"]
        ).run_validation(request.data.get("action"))
        key = idempotency.claim(request, f"music.equipment.{org_id}", required=True)
        if key.done:
            return Response(key.result)
        identifier = serializers.IntegerField(min_value=1).run_validation(request.data.get("item"))
        item = get_object_or_404(access.items(self.scope).select_for_update(), pk=identifier)
        services.expected(item, request.data.get("version"))
        before = services.snapshot(item)
        equipment = self.rows().filter(item=item).first()
        if action in ["register", "profile"]:
            form = EquipmentInput(data=request.data)
            form.is_valid(raise_exception=True)
            if action == "register" and equipment:
                raise serializers.ValidationError(
                    gettext("Dieses Material gehört bereits zur Musikausstattung.")
                )
            if not equipment:
                if action != "register":
                    raise NotFound()
                equipment = Equipment(organization=self.org, item=item)
            for field, value in form.validated_data.items():
                setattr(equipment, field, value)
            equipment.save()
        else:
            if not equipment:
                raise NotFound()
            if action == "issue":
                musician_id = serializers.IntegerField(min_value=1).run_validation(
                    request.data.get("musician")
                )
                musician = get_object_or_404(
                    Musician, pk=musician_id, organization=self.org, active=True
                )
                due = serializers.DateField().run_validation(request.data.get("due_date"))
                if (
                    due < timezone.localdate()
                    or item.condition not in ["ready", "limited"]
                    or equipment.loans.filter(returned_at=None).exists()
                ):
                    raise serializers.ValidationError(
                        gettext(
                            "Bitte einsatzfähiges, nicht ausgegebenes Material "
                            "und eine gültige Rückgabefrist wählen."
                        )
                    )
                note = serializers.CharField(
                    max_length=1000, allow_blank=True, default=""
                ).run_validation(request.data.get("note", ""))
                location = {
                    k: getattr(item, k)
                    for k in ["location_kind", "member_id", "address", "location_note"]
                }
                if musician.membership_id:
                    form = ItemInput(
                        data={"location_kind": "member", "member": musician.membership_id},
                        partial=True,
                        context={"scope": self.scope, "item": item},
                    )
                    form.is_valid(raise_exception=True)
                    for field, value in form.validated_data.items():
                        setattr(item, field, value)
                    item.location_note = ""
                else:
                    item.location_kind, item.member_id, item.address = "unknown", None, {}
                    item.location_note = gettext(
                        "Ausgegeben an Gastmusiker; Zuordnung in der Musikausstattung."
                    )
                EquipmentLoan.objects.create(
                    organization=self.org,
                    equipment=equipment,
                    musician=musician,
                    due_date=due,
                    issued_by=request.user,
                    location_before=location,
                    issue_condition=item.condition,
                    note=note,
                )
            elif action == "return":
                loan_id = serializers.IntegerField(min_value=1).run_validation(
                    request.data.get("loan")
                )
                loan = get_object_or_404(equipment.loans, pk=loan_id, returned_at=None)
                restore = serializers.BooleanField().run_validation(
                    request.data.get("restore_location")
                )
                location = (
                    dict(loan.location_before)
                    if restore
                    else {
                        "location_kind": "address",
                        "address": request.data.get("address", {}),
                        "location_note": "",
                    }
                )
                if "member_id" in location:
                    location["member"] = location.pop("member_id")
                if location.get("location_kind") not in ["address", "member"]:
                    raise serializers.ValidationError(
                        gettext("Bitte einen gültigen Rückgabeort wählen.")
                    )
                form = ItemInput(
                    data=location, partial=True, context={"scope": self.scope, "item": item}
                )
                form.is_valid(raise_exception=True)
                for field, value in form.validated_data.items():
                    setattr(item, field, value)
                item.condition = serializers.ChoiceField(choices=CONDITIONS).run_validation(
                    request.data.get("condition")
                )
                item.condition_note = serializers.CharField(
                    max_length=500, allow_blank=True
                ).run_validation(request.data.get("condition_note", ""))
                loan.returned_at, loan.returned_by, loan.return_condition = (
                    timezone.now(),
                    request.user,
                    item.condition,
                )
                loan.return_note = serializers.CharField(
                    max_length=1000, allow_blank=True
                ).run_validation(request.data.get("note", ""))
                loan.save()
            else:
                date = serializers.DateField().run_validation(request.data.get("date"))
                next_due = serializers.DateField(allow_null=True).run_validation(
                    request.data.get("next_due")
                )
                if date > timezone.localdate() or (next_due and next_due < date):
                    raise serializers.ValidationError(
                        gettext("Bitte Wartungsdatum und nächste Fälligkeit prüfen.")
                    )
                item.condition = serializers.ChoiceField(choices=CONDITIONS).run_validation(
                    request.data.get("condition")
                )
                note = serializers.CharField(max_length=1000, allow_blank=True).run_validation(
                    request.data.get("note", "")
                )
                item.condition_note = note[:500]
                EquipmentMaintenance.objects.create(
                    organization=self.org,
                    equipment=equipment,
                    date=date,
                    next_due=next_due,
                    condition=item.condition,
                    note=note,
                    actor=request.user,
                )
                equipment.maintenance_due = next_due
                equipment.save(update_fields=["maintenance_due"])
        services.changed(item, request.user, before, "music_" + action)
        record(self.org, request.user, "update", equipment, {"Musikausstattung": [None, action]})
        key.remember({"id": equipment.pk})
        return Response({"id": equipment.pk})
