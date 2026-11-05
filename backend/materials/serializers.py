import datetime

from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers

from . import access
from .models import FACILITY_TYPES, OWNERSHIP


class LaneInput(serializers.Serializer):
    facility = serializers.CharField(max_length=20)
    count = serializers.IntegerField(min_value=1, max_value=500)

    def validate_facility(self, value):
        from competitions.targets import FACILITIES

        if value not in FACILITIES:
            raise serializers.ValidationError(_("Bitte gültige Schießmöglichkeiten wählen."))
        return value


class ItemInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1, required=False)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=2000)
    purpose = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    location_kind = serializers.ChoiceField(choices=["member", "address", "facility"])
    member = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    address = serializers.DictField(
        child=serializers.CharField(max_length=300, allow_blank=True), required=False
    )
    facility = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    belongs_to = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    location_note = serializers.CharField(max_length=300, allow_blank=True, required=False)
    condition = serializers.ChoiceField(
        choices=["ready", "limited", "defective", "retired"], required=False
    )
    condition_note = serializers.CharField(max_length=500, allow_blank=True, required=False)
    # Nur Infrastruktur
    facility_type = serializers.ChoiceField(
        choices=[k for k, _label in FACILITY_TYPES], required=False
    )
    ownership = serializers.ChoiceField(
        choices=[k for k, _label in OWNERSHIP], allow_blank=True, required=False
    )
    capacity = serializers.IntegerField(
        min_value=1, max_value=100000, allow_null=True, required=False
    )
    lanes = LaneInput(many=True, required=False)
    access_note = serializers.CharField(max_length=500, allow_blank=True, required=False)

    FACILITY_ONLY = ("facility_type", "ownership", "capacity", "lanes", "access_note")

    def validate(self, data):
        item = self.context.get("item")
        scope = self.context["scope"]
        kind = item.kind if item else self.context.get("kind", getattr(scope, "kind", "material"))
        current = {key: getattr(item, key) for key in ["location_kind", "purpose"]} if item else {}
        location_kind = data.get("location_kind", current.get("location_kind"))
        if kind == "facility":
            if location_kind == "member":
                raise serializers.ValidationError(
                    {"location_kind": _("Infrastruktur liegt an einer Adresse.")}
                )
            if "belongs_to" in data and data["belongs_to"]:
                raise serializers.ValidationError({"belongs_to": _("Ungültige Auswahl.")})
            data.pop("belongs_to", None)
            if not item:
                data.setdefault("facility_type", "other")
            facility_type = data.get("facility_type", item.facility_type if item else "other")
            if facility_type != "range":
                data["lanes"] = []
            elif "lanes" in data:
                keys = [row["facility"] for row in data["lanes"]]
                if len(keys) != len(set(keys)):
                    raise serializers.ValidationError(
                        {"lanes": _("Jede Disziplin bitte nur einmal angeben.")}
                    )
                data["lanes"] = [dict(row) for row in data["lanes"]]
        else:
            if any(key in data for key in self.FACILITY_ONLY):
                raise serializers.ValidationError(_("Diese Angaben gibt es nur bei Infrastruktur."))
            if not item and not data.get("purpose", "").strip():
                # Das Anlageformular kann alternativ seine Terminzuordnungen mitsenden.
                if not self.context.get("has_events"):
                    raise serializers.ValidationError(
                        {"purpose": _("Bitte einen Verwendungszweck oder Termin angeben.")}
                    )
            if (
                item
                and "purpose" in data
                and not data["purpose"].strip()
                and not item.event_links.exclude(kind="exclude").exists()
            ):
                raise serializers.ValidationError(
                    {"purpose": _("Bitte einen Verwendungszweck oder Termin angeben.")}
                )
            if data.get("belongs_to"):
                target = access.facilities(scope).filter(pk=data["belongs_to"]).first()
                if target is None:
                    raise serializers.ValidationError(
                        {"belongs_to": _("Bitte eine zugängliche Infrastruktur wählen.")}
                    )
                data["belongs_to_id"] = target.pk
            elif "belongs_to" in data:
                data["belongs_to_id"] = None
            data.pop("belongs_to", None)
        changing = not item or "location_kind" in data
        if location_kind == "member" and (changing or "member" in data):
            member_id = data.get("member", item.member_id if item else None)
            if not access.members(scope).filter(pk=member_id).exists():
                raise serializers.ValidationError(
                    {"member": _("Bitte ein zugängliches Mitglied wählen.")}
                )
            data["member_id"] = member_id
            data["address"] = {}
            data["facility_id"] = None
        elif location_kind == "address" and (changing or "address" in data):
            address = data.get("address", item.address if item else {})
            if set(address) - {"name", "street", "postal_code", "city", "country"}:
                raise serializers.ValidationError({"address": _("Ungültige Adressfelder.")})
            if not all(
                address.get(k, "").strip() for k in ["street", "postal_code", "city", "country"]
            ):
                raise serializers.ValidationError(
                    {"address": _("Bitte eine vollständige Adresse eingeben.")}
                )
            data["address"] = address
            data["member_id"] = None
            data["facility_id"] = None
        elif location_kind == "facility" and (changing or "facility" in data):
            target_id = data.get("facility", item.facility_id if item else None)
            target = access.facilities(scope).filter(pk=target_id).first()
            if target is None or (item and target.pk == item.pk):
                raise serializers.ValidationError(
                    {"facility": _("Bitte eine zugängliche Infrastruktur wählen.")}
                )
            if kind == "facility":
                # Nur eine Ebene: Gebäude → Bereich
                if target.location_kind == "facility":
                    raise serializers.ValidationError(
                        {"facility": _("Ein Bereich kann keine weiteren Bereiche haben.")}
                    )
                if item and item.contents.filter(kind="facility", deleted_at__isnull=True).exists():
                    raise serializers.ValidationError(
                        {"facility": _("Diese Infrastruktur hat selbst Bereiche.")}
                    )
            data["facility_id"] = target.pk
            data["member_id"] = None
            data["address"] = {}
        elif "member" in data or "address" in data or "facility" in data:
            raise serializers.ValidationError(_("Bitte zuerst die Standortart wählen."))
        data.pop("member", None)
        data.pop("facility", None)
        return data


def rule(event):
    return {
        "start": event.starts_at.isoformat(),
        "repeat": event.repeat,
        "interval": event.repeat_interval,
        "until": str(event.repeat_until or ""),
    }


def needs_review(link):
    event = link.event
    if event is None:
        return True
    if (link.kind == "event") == event.is_series:
        return True
    return link.kind != "event" and link.rule != rule(event)


class EventInput(serializers.Serializer):
    event = serializers.IntegerField(min_value=1)
    kind = serializers.ChoiceField(choices=["event", "series", "occurrence", "exclude"])
    original_start = serializers.DateTimeField(required=False, allow_null=True)
    valid_from = serializers.DateField(required=False, allow_null=True)
    valid_until = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(max_length=300, allow_blank=True, required=False)

    def validate(self, data):
        from events.recurrence import is_rule_start

        event = (
            access.events(self.context["user"], self.context["scope"])
            .filter(pk=data["event"])
            .first()
        )
        if not event:
            raise serializers.ValidationError(_("Termin nicht verfügbar."))
        kind = data["kind"]
        if (kind == "event") == event.is_series:
            raise serializers.ValidationError(_("Bitte die passende Terminzuordnung wählen."))
        if kind in ("occurrence", "exclude"):
            if not data.get("original_start") or not is_rule_start(event, data["original_start"]):
                raise serializers.ValidationError(
                    _("Dieses Vorkommen gehört nicht zur Terminreihe.")
                )
        else:
            data["original_start"] = None
        if kind == "series":
            data.setdefault("valid_from", timezone.localdate())
        else:
            data["valid_from"] = data["valid_until"] = None
        if (
            data.get("valid_from")
            and data.get("valid_until")
            and data["valid_until"] < data["valid_from"]
        ):
            raise serializers.ValidationError(_("Das Ende liegt vor dem Beginn."))
        data["event"] = event
        data["rule"] = rule(event)
        return data


def event_data(link):
    event = link.event
    return {
        "id": link.pk,
        "event": link.event_id,
        "title": event.title if event else "",
        "kind": link.kind,
        "original_start": link.original_start,
        "all_day": event.all_day if event else False,
        "valid_from": link.valid_from,
        "valid_until": link.valid_until,
        "note": link.note,
        "needs_review": needs_review(link),
        "cancelled": event.is_cancelled if event else False,
    }


def effective_links(item, user, scope, *, start=None, end=None):
    from events.recurrence import occurrences

    start = start or timezone.now()
    end = end or start + datetime.timedelta(days=366)
    links = list(
        item.event_links.filter(event__in=access.events(user, scope)).select_related("event")
    )
    result = {}
    excluded = {
        (r.event_id, r.original_start) for r in links if r.kind == "exclude" and not needs_review(r)
    }
    for link in links:
        if link.kind == "exclude" or needs_review(link):
            continue
        for occ in occurrences([link.event], start, end):
            key = (link.event_id, occ.original_start)
            if occ.is_cancelled or key in excluded:
                continue
            if link.kind == "occurrence" and occ.original_start != link.original_start:
                continue
            day = timezone.localtime(occ.original_start).date()
            if (
                link.valid_from
                and day < link.valid_from
                or link.valid_until
                and day > link.valid_until
            ):
                continue
            result[key] = {
                "event": link.event_id,
                "title": link.event.title,
                "starts_at": occ.starts_at,
                "original_start": occ.original_start,
                "all_day": link.event.all_day,
                "kind": link.kind,
            }
    return sorted(result.values(), key=lambda r: r["starts_at"])


def item_data(item, user, scope, *, detail=False):
    member = access.members(scope).filter(pk=item.member_id).first() if item.member_id else None
    location_review = (
        item.location_kind == "unknown"
        or (item.location_kind == "member" and not item.member_id)
        or (item.location_kind == "facility" and not item.facility_id)
    )
    facility = (
        access.facilities(scope).filter(pk=item.facility_id).first() if item.facility_id else None
    )
    if item.facility_id and facility is None and access.facilities_enabled(scope):
        location_review = True
    belongs_to = (
        access.facilities(scope).filter(pk=item.belongs_to_id).first()
        if item.belongs_to_id
        else None
    )
    if member and member.current_period(timezone.localdate()) is None:
        location_review = True
    photo = item.photos.filter(deleted_at__isnull=True).first()
    prefix = (
        f"/api/depts/{scope.department_id}" if scope.department_id else f"/api/orgs/{scope.org.pk}"
    )
    data = {
        "id": item.pk,
        "kind": item.kind,
        "inventory_number": item.inventory_number,
        "title": item.title,
        "description": item.description,
        "purpose": item.purpose,
        "location_kind": item.location_kind,
        "member": member.pk if member else None,
        "member_name": str(member.person) if member else "",
        "address": item.address,
        "facility": facility.pk if facility else None,
        "facility_title": facility.title if facility else "",
        "belongs_to": belongs_to.pk if belongs_to else None,
        "belongs_to_title": belongs_to.title if belongs_to else "",
        "location_note": item.location_note,
        "condition": item.condition,
        "condition_note": item.condition_note,
        "version": item.version,
        "deleted_at": item.deleted_at,
        "location_review": location_review,
        "photo_url": f"{prefix}/{collection(item)}/{item.pk}/photo/?v={photo.pk}"
        if photo
        else None,
    }
    if item.kind == "facility":
        data.update(
            {
                "facility_type": item.facility_type,
                "ownership": item.ownership,
                "capacity": item.capacity,
                "lanes": item.lanes,
                "access_note": item.access_note,
            }
        )
    if detail:
        if "music" in scope.org.enabled_modules and "music.view" in scope.permissions:
            equipment = getattr(item, "music_equipment", None)
            if equipment:
                loan = equipment.loans.filter(returned_at=None).first()
                data["music_equipment"] = {
                    "id": equipment.pk,
                    "loaned": bool(loan),
                    "due_date": loan.due_date if loan else None,
                }
        data["events"] = [
            event_data(r)
            for r in item.event_links.filter(event__in=access.events(user, scope)).select_related(
                "event"
            )
        ]
        data["todos"] = [
            {"id": r.todo_id, "title": r.todo.title, "status": r.todo.status}
            for r in item.todo_links.filter(todo__in=access.todos(user, scope)).select_related(
                "todo"
            )
        ]
        data["documents"] = [
            {"id": r.document_id, "title": r.document.title}
            for r in item.document_links.filter(
                document__in=access.documents(scope)
            ).select_related("document")
        ]
        data["uses"] = effective_links(item, user, scope)
        if item.kind == "facility":
            data.update(facility_details(item, scope))
        data["usage_review"] = not item.purpose and (
            not item.event_links.exclude(kind="exclude").exists()
            or item.event_links.filter(event__isnull=True).exists()
        )
    return data


def collection(item):
    return "facilities" if item.kind == "facility" else "materials"


def facility_details(item, scope):
    """Bereiche, hier gelagertes Material und zugehörige Teile (z. B. Schlüssel)."""

    members = set(access.members(scope).values_list("pk", flat=True))

    def rows(qs):
        # Den Namen des Mitglieds nur mit Mitgliederleserecht zeigen
        return [
            {
                "id": r.pk,
                "kind": r.kind,
                "inventory_number": r.inventory_number,
                "title": r.title,
                "condition": r.condition,
                "location_kind": r.location_kind,
                "member_name": str(r.member.person) if r.member_id in members else "",
                "location_note": r.location_note,
            }
            for r in qs.select_related("member__person").order_by("pk")
        ]

    live = {"organization": scope.org, "department_id": scope.department_id, "deleted_at": None}
    data = {"areas": rows(item.contents.filter(kind="facility", **live)), "parent": None}
    if item.facility_id:
        parent = access.facilities(scope).filter(pk=item.facility_id).first()
        if parent:
            data["parent"] = {"id": parent.pk, "title": parent.title, "address": parent.address}
    if access.can_view(scope, "material"):
        data["contents"] = rows(item.contents.filter(kind="material", **live))
        data["accessories"] = rows(item.accessories.filter(kind="material", **live))
    return data
