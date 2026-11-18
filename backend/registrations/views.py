"""Schnittstelle der Anmeldungen am Termin.

Verwaltung (Verein, Verband): ``/api/orgs/<id>/events/<pk>/registration/…``
Mitgliederbereich und Apps: ``/api/portal/<access>/events/<pk>/registration/…``
"""

from __future__ import annotations

import io
from decimal import Decimal

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext
from openpyxl import Workbook
from openpyxl.styles import Font
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import BILLING_EDIT, REGISTRATIONS_EDIT, REGISTRATIONS_VIEW
from audit.log import record
from events.views import OrgCalendarMixin, PortalCalendarMixin
from exchange.export import safe_cell
from members.models import Membership

from . import services
from .models import (
    MAX_PRICES,
    MAX_STEPS,
    Participant,
    PriceOption,
    PriceStep,
    Registration,
    RegistrationSetup,
)


def _money(value) -> str:
    return str(value) if value is not None else None


def participant_data(p: Participant) -> dict:
    return {
        "id": p.pk,
        "name": p.name,
        "membership_id": p.membership_id,
        "price_id": p.price_id,
        "price_name": p.price_name,
        "amount": str(p.amount),
        "status": p.status,
    }


def registration_data(reg: Registration, *, full: bool) -> dict:
    inv = reg.invoice
    data = {
        "id": reg.pk,
        "number": reg.display_number,
        "status": reg.status,
        "name": reg.name,
        "total": str(reg.total),
        "paid_state": services.paid_state(reg),
        "created_at": reg.created_at,
        "cancelled_at": reg.cancelled_at,
        "participants": [participant_data(p) for p in reg.participants.all()],
        "invoice": (
            {
                "id": inv.pk,
                "number": inv.display_number,
                "status": inv.status,
                "total": str(inv.total),
                "paid": str(inv.paid),
                "due_date": inv.due_date,
            }
            if inv
            else None
        ),
    }
    if full:
        data.update(
            {
                "membership_id": reg.membership_id,
                "email": reg.email,
                "phone": reg.phone,
                "address": reg.address,
                "note": reg.note,
                "source": reg.source,
                "source_label": reg.get_source_display(),
                "cancel_reason": reg.cancel_reason,
                "confirmation_sent_at": reg.confirmation_sent_at,
                "payment_confirmed_at": reg.payment_confirmed_at,
            }
        )
    return data


# --- Einrichten (Verwaltung) ---


class StepInput(serializers.Serializer):
    name = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal(0), max_value=Decimal(100000)
    )
    until_date = serializers.DateField(required=False, allow_null=True, default=None)
    until_count = serializers.IntegerField(
        required=False, allow_null=True, default=None, min_value=1
    )


class PriceInput(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField(max_length=100)
    name_en = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    applies = serializers.ChoiceField(choices=PriceOption.Applies.choices, default="all")
    age_from = serializers.IntegerField(
        required=False, allow_null=True, default=None, min_value=0, max_value=120
    )
    age_to = serializers.IntegerField(
        required=False, allow_null=True, default=None, min_value=0, max_value=120
    )
    capacity = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=1)
    vat_rate = serializers.DecimalField(
        max_digits=4,
        decimal_places=2,
        min_value=Decimal(0),
        max_value=Decimal(99),
        required=False,
        allow_null=True,
        default=None,
    )
    is_active = serializers.BooleanField(default=True)
    steps = StepInput(many=True)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(gettext("Bitte einen Namen angeben."))
        return value

    def validate(self, attrs):
        steps = attrs["steps"]
        if not steps:
            raise serializers.ValidationError(gettext("Jeder Tarif braucht einen Preis."))
        if len(steps) > MAX_STEPS:
            raise serializers.ValidationError(
                gettext("Höchstens {n} Preisstufen je Tarif.").format(n=MAX_STEPS)
            )
        last = steps[-1]
        if last["until_date"] is not None or last["until_count"] is not None:
            raise serializers.ValidationError(
                gettext(
                    "Die letzte Preisstufe gilt bis zum Anmeldeschluss; bitte dort kein Datum "
                    "und keine Platzzahl angeben."
                )
            )
        dates = [s["until_date"] for s in steps if s["until_date"] is not None]
        if dates != sorted(dates):
            raise serializers.ValidationError(
                gettext("Die Preisstufen müssen nach ihrem Datum aufeinander folgen.")
            )
        if (
            attrs.get("age_from") is not None
            and attrs.get("age_to") is not None
            and attrs["age_from"] > attrs["age_to"]
        ):
            raise serializers.ValidationError(gettext("Das Alter „von“ ist größer als „bis“."))
        return attrs


class SetupInput(serializers.Serializer):
    opens_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    closes_at = serializers.DateTimeField()
    is_open = serializers.BooleanField(default=True)
    capacity = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=1)
    max_persons = serializers.IntegerField(min_value=1, max_value=20, default=6)
    guests_allowed = serializers.BooleanField(default=True)
    due_days = serializers.IntegerField(min_value=0, max_value=90, default=14)
    category = serializers.IntegerField(required=False, allow_null=True, default=None)
    terms = serializers.CharField(max_length=5000, required=False, allow_blank=True, default="")
    prices = PriceInput(many=True)

    def validate(self, attrs):
        if not attrs["prices"]:
            raise serializers.ValidationError(
                {"prices": gettext("Bitte mindestens einen Tarif angeben.")}
            )
        if len(attrs["prices"]) > MAX_PRICES:
            raise serializers.ValidationError(
                {"prices": gettext("Höchstens {n} Tarife.").format(n=MAX_PRICES)}
            )
        if attrs["opens_at"] and attrs["opens_at"] >= attrs["closes_at"]:
            raise serializers.ValidationError(
                {"closes_at": gettext("Der Anmeldeschluss liegt vor dem Anmeldestart.")}
            )
        return attrs


class _OrgRegistrationMixin(OrgCalendarMixin):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not services.module_on(self.org):
            raise NotFound()
        if REGISTRATIONS_VIEW not in self.viewer.perms:
            raise PermissionDenied(gettext("Dafür fehlt dir die Berechtigung."))

    def event(self, pk: int):
        event = self.visible_event(pk)
        if not self.viewer.owns(event):
            raise NotFound()
        return event

    def require_edit(self, event) -> None:
        if REGISTRATIONS_EDIT not in self.viewer.perms or not self.viewer.can_edit(event):
            raise PermissionDenied(gettext("Dafür fehlt dir die Berechtigung."))

    def setup_for(self, event) -> RegistrationSetup:
        setup = services.setup_of(event)
        if setup is None:
            raise NotFound(gettext("Zu diesem Termin gibt es keine Anmeldung."))
        return setup

    def payload(self, event, setup) -> dict:
        regs = (
            Registration.objects.filter(setup=setup)
            .select_related("invoice")
            .prefetch_related("participants")
            .order_by("status", "created_at", "pk")
        )
        return {
            "event_id": event.pk,
            "offer": services.offer_data(setup, full=True),
            "summary": services.summary(setup),
            "can_edit": REGISTRATIONS_EDIT in self.viewer.perms and self.viewer.can_edit(event),
            "can_set_prices": BILLING_EDIT in self.viewer.perms,
            "registrations": [registration_data(r, full=True) for r in regs],
        }


class SetupView(_OrgRegistrationMixin, APIView):
    """GET Stand mit allen Anmeldungen · PUT einrichten/ändern · DELETE (ohne Anmeldungen)."""

    def get(self, request, pk: int, **kwargs):
        event = self.event(pk)
        setup = services.setup_of(event)
        if setup is None:
            return Response(
                {
                    "event_id": event.pk,
                    "offer": None,
                    "can_edit": REGISTRATIONS_EDIT in self.viewer.perms
                    and self.viewer.can_edit(event),
                    "can_set_prices": BILLING_EDIT in self.viewer.perms,
                    "registrations": [],
                }
            )
        return Response(self.payload(event, setup))

    @transaction.atomic
    def put(self, request, pk: int, **kwargs):
        event = self.event(pk)
        self.require_edit(event)
        if event.rsvp_enabled:
            raise serializers.ValidationError(
                {
                    "detail": gettext(
                        "Der Termin hat Zu- und Absagen. Bitte diese zuerst ausschalten; ein "
                        "Termin hat entweder Zu- und Absagen oder eine verbindliche Anmeldung."
                    )
                }
            )
        data = SetupInput(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        setup = services.setup_of(event)
        paid = any(s["amount"] > 0 for p in v["prices"] for s in p["steps"])
        old_paid = (
            setup is not None
            and PriceStep.objects.filter(price__setup=setup, amount__gt=0).exists()
        )
        if (paid or old_paid) and BILLING_EDIT not in self.viewer.perms:
            raise PermissionDenied(
                gettext(
                    "Preise legt fest, wer Rechnungen bearbeiten darf. Ohne dieses Recht sind nur "
                    "kostenlose Tarife möglich."
                )
            )
        category = None
        if v["category"] is not None:
            from finance.models import Category

            category = Category.objects.filter(
                organization=self.org, pk=v["category"], kind="income"
            ).first()
            if category is None:
                raise serializers.ValidationError(
                    {"category": gettext("Bitte eine Einnahme-Kategorie wählen.")}
                )
        created = setup is None
        if created:
            setup = RegistrationSetup(event=event)
        for field in (
            "opens_at",
            "closes_at",
            "is_open",
            "capacity",
            "max_persons",
            "guests_allowed",
            "due_days",
            "terms",
        ):
            setattr(setup, field, v[field])
        setup.category = category
        setup.save()
        if paid and services.payment_category(setup) is None:
            raise serializers.ValidationError(
                {
                    "category": gettext(
                        "Bitte eine Kategorie für die Kasse wählen (oder unter Finanzen › "
                        "Einrichtung eine Kategorie für Zahlungen)."
                    )
                }
            )
        self._save_prices(setup, v["prices"])
        if created and event.project_id is None and "finance" in (self.org.enabled_modules or []):
            # Finanz-Veranstaltung vorschlagen: Einnahmen landen in der Auswertung
            from finance.models import Project

            project = Project.objects.create(
                organization=self.org,
                name=event.title[:200],
                starts_on=timezone.localtime(event.starts_at).date(),
                ends_on=timezone.localtime(event.ends_at).date(),
                created_by=request.user,
            )
            event.project = project
            event.save(update_fields=["project"])
        record(
            self.org,
            request.user,
            "create" if created else "update",
            event,
            {"Anmeldung": [None if created else "geändert", "eingerichtet"]},
        )
        return Response(self.payload(event, setup))

    def _save_prices(self, setup: RegistrationSetup, prices: list[dict]) -> None:
        existing = {p.pk: p for p in setup.prices.all()}
        keep: set[int] = set()
        for index, item in enumerate(prices):
            price = existing.get(item.get("id") or 0)
            if price is None:
                price = PriceOption(setup=setup)
            used = price.pk is not None and Participant.objects.filter(price=price).exists()
            for field in ("name", "name_en", "applies", "age_from", "age_to", "capacity"):
                setattr(price, field, item[field])
            price.vat_rate = item["vat_rate"]
            price.is_active = item["is_active"]
            price.position = index
            price.save()
            keep.add(price.pk)
            # Gebuchte Stufen bleiben erhalten (die Anmeldungen verweisen darauf); geändert
            # wird, was neu kommt. Die Preise der Anmeldungen sind ohnehin festgehalten.
            old_steps = list(price.steps.all())
            for pos, step_in in enumerate(item["steps"]):
                step = old_steps[pos] if pos < len(old_steps) else PriceStep(price=price)
                step.name = step_in["name"].strip()
                step.amount = step_in["amount"]
                step.until_date = step_in["until_date"]
                step.until_count = step_in["until_count"]
                step.position = pos
                step.save()
            for step in old_steps[len(item["steps"]) :]:
                if used and Participant.objects.filter(step=step).exists():
                    # gebuchte Stufe: ans Ende, nicht mehr gültig
                    step.until_date = timezone.localdate().replace(year=2000)
                    step.position = 99
                    step.save()
                else:
                    step.delete()
        for pk, price in existing.items():
            if pk in keep:
                continue
            if Participant.objects.filter(price=price).exists():
                price.is_active = False
                price.save(update_fields=["is_active"])
            else:
                price.delete()

    @transaction.atomic
    def delete(self, request, pk: int, **kwargs):
        event = self.event(pk)
        self.require_edit(event)
        setup = self.setup_for(event)
        if setup.registrations.exists():
            raise serializers.ValidationError(
                {
                    "detail": gettext(
                        "Es gibt schon Anmeldungen. Bitte die Anmeldung schließen statt sie zu "
                        "entfernen."
                    )
                }
            )
        setup.delete()
        record(self.org, request.user, "update", event, {"Anmeldung": ["eingerichtet", None]})
        return Response(status=status.HTTP_204_NO_CONTENT)


class PersonIn(serializers.Serializer):
    membership_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    birth_date = serializers.DateField(required=False, allow_null=True, default=None)
    price_id = serializers.IntegerField()


class BoardRegistrationIn(serializers.Serializer):
    membership_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    address = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    persons = PersonIn(many=True)


def _person_inputs(setup, persons: list[dict], allowed_members=None) -> list:
    prices = {p.pk: p for p in setup.prices.all()}
    ids = [p["membership_id"] for p in persons if p["membership_id"]]
    members = {
        m.pk: m
        for m in Membership.objects.filter(
            pk__in=ids, organization=setup.organization, purged_at__isnull=True
        ).select_related("person")
    }
    result = []
    for p in persons:
        price = prices.get(p["price_id"])
        if price is None:
            raise serializers.ValidationError(gettext("Bitte einen gültigen Tarif wählen."))
        member = None
        if p["membership_id"]:
            member = members.get(p["membership_id"])
            if member is None or (allowed_members is not None and member.pk not in allowed_members):
                raise serializers.ValidationError(gettext("Unbekanntes Mitglied."))
        name = member.person.display_name if member else p["name"].strip()
        result.append(
            services.PersonInput(
                membership=member, name=name, birth_date=p["birth_date"], price=price
            )
        )
    return result


def _contact(member: Membership) -> dict:
    from members.services import contact_for

    contact = contact_for(member.person, member.organization)
    address = ""
    if contact is not None:
        address = "\n".join(
            x for x in (contact.street, f"{contact.postal_code} {contact.city}".strip()) if x
        )
    return {
        "name": member.person.display_name,
        "email": contact.email if contact else "",
        "phone": (getattr(contact, "mobile", "") or getattr(contact, "phone", ""))
        if contact
        else "",
        "address": address,
    }


class RegistrationListView(_OrgRegistrationMixin, APIView):
    """POST: Verwaltung meldet jemanden an (Mitglied oder Gast)."""

    def post(self, request, pk: int, **kwargs):
        event = self.event(pk)
        self.require_edit(event)
        setup = self.setup_for(event)
        data = BoardRegistrationIn(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        booker = None
        contact = {
            "name": v["name"],
            "email": v["email"],
            "phone": v["phone"],
            "address": v["address"],
        }
        if v["membership_id"]:
            booker = (
                Membership.objects.filter(
                    pk=v["membership_id"], organization=self.org, purged_at__isnull=True
                )
                .select_related("person", "organization")
                .first()
            )
            if booker is None:
                raise serializers.ValidationError(gettext("Unbekanntes Mitglied."))
            contact = {**_contact(booker), **{k: val for k, val in contact.items() if val}}
            contact["name"] = booker.person.display_name
        persons = _person_inputs(setup, v["persons"])
        with transaction.atomic():
            reg = services.register(
                setup,
                persons,
                booker=booker,
                note=v["note"],
                source=Registration.Source.BOARD,
                user=request.user,
                **contact,
            )
            record(
                self.org,
                request.user,
                "update",
                event,
                {f"Anmeldung {reg.display_number}": [None, reg.name]},
            )
        return Response(self.payload(event, setup), status=status.HTTP_201_CREATED)


class CancelIn(serializers.Serializer):
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class RegistrationCancelView(_OrgRegistrationMixin, APIView):
    def post(self, request, pk: int, reg_id: int, **kwargs):
        event = self.event(pk)
        self.require_edit(event)
        setup = self.setup_for(event)
        reg = Registration.objects.filter(setup=setup, pk=reg_id).first()
        if reg is None:
            raise NotFound()
        data = CancelIn(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            services.cancel(reg, user=request.user, reason=data.validated_data["reason"])
            record(
                self.org,
                request.user,
                "update",
                event,
                {f"Anmeldung {reg.display_number}": [reg.name, "abgemeldet"]},
            )
        return Response(self.payload(event, setup))


class RegistrationExportView(_OrgRegistrationMixin, APIView):
    """Teilnehmerliste als Excel."""

    def get(self, request, pk: int, **kwargs):
        event = self.event(pk)
        setup = self.setup_for(event)
        wb = Workbook()
        ws = wb.active
        ws.title = gettext("Teilnehmende")[:30]
        head = [
            gettext("Anmeldung"),
            gettext("Name"),
            gettext("Tarif"),
            gettext("Betrag"),
            gettext("angemeldet von"),
            gettext("E-Mail"),
            gettext("Telefon"),
            gettext("Rechnung"),
            gettext("bezahlt"),
            gettext("Bemerkung"),
        ]
        ws.append(head)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        labels = {
            "free": gettext("kostenlos"),
            "open": gettext("offen"),
            "partly": gettext("teilweise"),
            "paid": gettext("bezahlt"),
            "cancelled": gettext("abgemeldet"),
        }
        regs = (
            Registration.objects.filter(setup=setup, status=Registration.Status.REGISTERED)
            .select_related("invoice")
            .prefetch_related("participants")
        )
        for reg in regs:
            for p in reg.participants.all():
                if p.status != Participant.Status.ACTIVE:
                    continue
                ws.append(
                    [
                        safe_cell(reg.display_number),
                        safe_cell(p.name),
                        safe_cell(p.price_name),
                        float(p.amount),
                        safe_cell(reg.name),
                        safe_cell(reg.email),
                        safe_cell(reg.phone),
                        safe_cell(reg.invoice.display_number if reg.invoice else ""),
                        labels[services.paid_state(reg)],
                        safe_cell(reg.note),
                    ]
                )
        out = io.BytesIO()
        wb.save(out)
        response = HttpResponse(
            out.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="teilnehmende.xlsx"'
        return response


# --- Mitgliederbereich und Apps ---


class MemberRegistrationIn(serializers.Serializer):
    persons = PersonIn(many=True)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    terms_accepted = serializers.BooleanField(default=False)
    app = serializers.BooleanField(default=False)


class _PortalRegistrationMixin(PortalCalendarMixin):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not services.module_on(self.viewer.org):
            raise NotFound()

    def member(self) -> Membership:
        return Membership.objects.select_related("person", "organization").get(
            pk=self.viewer.membership_id
        )

    def mine(self, setup):
        member_id = self.viewer.membership_id
        return (
            Registration.objects.filter(setup=setup)
            .filter(models_q_member(member_id))
            .select_related("invoice")
            .prefetch_related("participants")
            .order_by("-created_at", "-pk")
        )

    def payload(self, event, setup) -> dict:
        member = self.member()
        family = services.family_of(member)
        taken = services.registered_memberships(setup)
        return {
            "event_id": event.pk,
            "offer": services.offer_data(setup),
            "can_cancel": services.member_can_cancel(setup),
            "persons": [
                {
                    "membership_id": m.pk,
                    "name": m.person.display_name,
                    "self": m.pk == member.pk,
                    "registered": m.pk in taken,
                    "has_birth_date": m.person.birth_date is not None,
                }
                for m in [member, *family]
            ],
            "mine": [registration_data(r, full=False) for r in self.mine(setup)],
        }


def models_q_member(member_id: int):
    from django.db.models import Q

    return Q(membership_id=member_id) | Q(participants__membership_id=member_id)


class MemberRegistrationView(_PortalRegistrationMixin, APIView):
    """GET Angebot, eigene Anmeldungen, Familie · POST verbindlich anmelden."""

    def get(self, request, pk: int, **kwargs):
        event = self.visible_event(pk)
        setup = services.setup_of(event)
        if setup is None:
            raise NotFound(gettext("Zu diesem Termin gibt es keine Anmeldung."))
        return Response(self.payload(event, setup))

    def post(self, request, pk: int, **kwargs):
        event = self.visible_event(pk)
        setup = services.setup_of(event)
        if setup is None:
            raise NotFound(gettext("Zu diesem Termin gibt es keine Anmeldung."))
        data = MemberRegistrationIn(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        member = self.member()
        allowed = {member.pk, *(m.pk for m in services.family_of(member))}
        persons = _person_inputs(setup, v["persons"], allowed_members=allowed)
        with transaction.atomic():
            reg = services.register(
                setup,
                persons,
                booker=member,
                note=v["note"],
                source=Registration.Source.APP if v["app"] else Registration.Source.MEMBER,
                user=request.user,
                terms_accepted=v["terms_accepted"],
                **_contact(member),
            )
            record(
                self.viewer.org,
                request.user,
                "update",
                event,
                {f"Anmeldung {reg.display_number}": [None, reg.name]},
            )
        return Response(self.payload(event, setup), status=status.HTTP_201_CREATED)


class MemberCancelView(_PortalRegistrationMixin, APIView):
    def post(self, request, pk: int, reg_id: int, **kwargs):
        event = self.visible_event(pk)
        setup = services.setup_of(event)
        if setup is None:
            raise NotFound()
        reg = Registration.objects.filter(
            setup=setup, pk=reg_id, membership_id=self.viewer.membership_id
        ).first()
        if reg is None:
            raise NotFound()
        with transaction.atomic():
            services.cancel(reg, user=request.user, by_member=True)
            record(
                self.viewer.org,
                request.user,
                "update",
                event,
                {f"Anmeldung {reg.display_number}": [reg.name, "abgemeldet"]},
            )
        return Response(self.payload(event, setup))


class MemberRegistrationsView(PortalCalendarMixin, APIView):
    """Alle eigenen Anmeldungen (Mitgliederbereich, Apps)."""

    def get(self, request, **kwargs):
        if not services.module_on(self.viewer.org):
            raise NotFound()
        regs = (
            Registration.objects.filter(models_q_member(self.viewer.membership_id))
            .filter(setup__event__in=self.viewer.events())
            .distinct()
            .select_related("invoice", "setup__event")
            .prefetch_related("participants")
            .order_by("-setup__event__starts_at", "-pk")
        )
        return Response(
            {
                "items": [
                    {
                        **registration_data(r, full=False),
                        "event": {
                            "id": r.setup.event_id,
                            "title": r.setup.event.title,
                            "starts_at": r.setup.event.starts_at,
                        },
                    }
                    for r in regs
                ]
            }
        )
