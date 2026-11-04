"""Proben verwenden den Kalender; Bestände werden bei Ausgabe gesperrt."""

import datetime

from django.db import transaction
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from changes import idempotency
from core.api_base import OrgScopedMixin
from events import recurrence, services

from .availability import Availability, ensure_available, interval
from .models import (
    Arrangement,
    Musician,
    Rehearsal,
    RehearsalInvitation,
    RehearsalItem,
    RehearsalProgram,
    RehearsalProgramItem,
    RehearsalResponse,
    ScoreLoan,
    ScorePart,
    ScoreReturn,
)
from .practice_programs import content, program_for, with_programs
from .views import MusicViewSet, ScopedSerializer


def visible_events(view):
    if "events" not in view.org.enabled_modules or "events.view" not in view.org_permissions:
        from events.models import Event

        return Event.objects.none()
    return (
        services.org_viewer(view.request.user, view.org, view.org_permissions)
        .events()
        .filter(organization=view.org, department=None, remote_uid="")
    )


def window():
    now = timezone.now()
    return now - datetime.timedelta(days=14), now + datetime.timedelta(days=90)


def occurrence(event, original):
    if abs((original - timezone.now()).days) > 370:
        raise serializers.ValidationError(
            gettext("Dieser Probentermin gehört nicht zur aktuellen Terminserie.")
        )
    if not recurrence.is_rule_start(event, original):
        raise serializers.ValidationError(
            gettext("Dieser Probentermin gehört nicht zur aktuellen Terminserie.")
        )
    begins = original
    exc = event.exceptions.filter(original_start=original).first() if event.is_series else None
    if exc and exc.starts_at:
        begins = exc.starts_at
    rows = recurrence.occurrences(
        [event], begins - datetime.timedelta(days=2), begins + datetime.timedelta(days=2)
    )
    return next((o for o in rows if o.original_start == original), None)


class RehearsalSerializer(ScopedSerializer):
    title = serializers.CharField(source="event.title", read_only=True)
    remind_days = serializers.IntegerField(min_value=0, max_value=7)

    class Meta:
        model = Rehearsal
        fields = ["id", "event", "title", "focus", "remind_days"]

    def get_fields(self):
        fields = super().get_fields()
        view = self.context.get("view")
        if getattr(view, "org", None):
            fields["event"].queryset = visible_events(view)
        return fields


class RehearsalItemSerializer(ScopedSerializer):
    class Meta:
        model = RehearsalItem
        fields = ["id", "rehearsal", "arrangement", "focus"]


class RehearsalInvitationSerializer(ScopedSerializer):
    class Meta:
        model = RehearsalInvitation
        fields = ["id", "rehearsal", "musician", "active"]


class PracticeViewSet(MusicViewSet):
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(
            **{
                "event__in" if qs.model is Rehearsal else "rehearsal__event__in": visible_events(
                    self
                )
            }
        )

    def perform_create(self, serializer):
        rehearsal = serializer.validated_data.get("rehearsal")
        if rehearsal and not visible_events(self).filter(pk=rehearsal.event_id).exists():
            raise NotFound()
        super().perform_create(serializer)

    def perform_update(self, serializer):
        if (
            "rehearsal" in serializer.validated_data
            and serializer.validated_data["rehearsal"] != serializer.instance.rehearsal
        ):
            raise serializers.ValidationError(
                gettext("Bestehende Verknüpfungen können nicht umgehängt werden.")
            )
        super().perform_update(serializer)


class RehearsalViewSet(PracticeViewSet):
    serializer_class = RehearsalSerializer

    @action(detail=False, methods=["get"])
    def choices(self, request, org_id):
        return Response(list(visible_events(self).order_by("-starts_at").values("id", "title")))

    @action(detail=True, methods=["get", "post"])
    @transaction.atomic
    def program(self, request, org_id, pk=None):
        rehearsal = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
        data = request.query_params if request.method == "GET" else request.data
        original = serializers.DateTimeField().run_validation(data.get("original_start"))
        if occurrence(rehearsal.event, original) is None:
            raise serializers.ValidationError(
                gettext("Dieser Probentermin gehört nicht zur aktuellen Terminserie.")
            )
        if request.method == "POST":
            scope = serializers.ChoiceField(
                choices=["occurrence", "series", "inherit"]
            ).run_validation(data.get("scope"))
            if scope == "inherit":
                RehearsalProgram.objects.filter(
                    rehearsal=rehearsal, original_start=original
                ).delete()
            else:
                values = RehearsalProgramInput(data=data)
                values.is_valid(raise_exception=True)
                values = values.validated_data
                # Alle Verweise vor dem ersten Schreiben im eigenen Mandanten auflösen.
                arrangements = {
                    a.pk: a
                    for a in Arrangement.objects.filter(
                        organization=self.org,
                        pk__in=[i["arrangement"] for i in values["items"]],
                    )
                }
                if any(i["arrangement"] not in arrangements for i in values["items"]):
                    raise NotFound()
                if scope == "series":
                    rehearsal.focus = values["focus"]
                    rehearsal.save(update_fields=["focus"])
                    rehearsal.items.all().delete()
                    for item in values["items"]:
                        RehearsalItem.objects.create(
                            organization=self.org,
                            rehearsal=rehearsal,
                            arrangement=arrangements[item["arrangement"]],
                            focus=item["focus"],
                        )
                else:
                    program, _ = RehearsalProgram.objects.update_or_create(
                        organization=self.org,
                        rehearsal=rehearsal,
                        original_start=original,
                        defaults={"focus": values["focus"]},
                    )
                    program.items.all().delete()
                    for position, item in enumerate(values["items"], 1):
                        RehearsalProgramItem.objects.create(
                            organization=self.org,
                            program=program,
                            position=position,
                            arrangement=arrangements[item["arrangement"]],
                            focus=item["focus"],
                        )
            record(
                self.org,
                request.user,
                "update",
                rehearsal,
                {
                    "Probenprogramm": [
                        None,
                        {"original_start": original.isoformat(), "scope": scope},
                    ]
                },
            )
        rehearsal = with_programs(Rehearsal.objects.filter(pk=rehearsal.pk)).get()
        return Response(
            {
                **program_for(rehearsal, original),
                "template": content(rehearsal),
                "is_series": rehearsal.event.is_series,
            }
        )


class RehearsalProgramItemInput(serializers.Serializer):
    arrangement = serializers.IntegerField(min_value=1)
    focus = serializers.CharField(max_length=500, allow_blank=True)


class RehearsalProgramInput(serializers.Serializer):
    focus = serializers.CharField(max_length=2000, allow_blank=True)
    items = RehearsalProgramItemInput(many=True, max_length=200)


class RehearsalItemViewSet(PracticeViewSet):
    serializer_class = RehearsalItemSerializer
    http_method_names = [*MusicViewSet.http_method_names, "delete"]


class RehearsalInvitationViewSet(PracticeViewSet):
    serializer_class = RehearsalInvitationSerializer

    def perform_create(self, serializer):
        super().perform_create(serializer)
        from .practice_tasks import invite_notice

        pk = serializer.instance.pk
        transaction.on_commit(lambda: invite_notice.delay(pk), robust=True)


class PracticeOverview(OrgScopedMixin, APIView):
    allowed_org_types = ("club", "federation")
    read_permission = "music.view"
    write_permission = "music.edit"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if "music" not in self.org.enabled_modules:
            raise NotFound()

    def get(self, request, org_id):
        rehearsals = with_programs(
            Rehearsal.objects.filter(
                organization=self.org, event__in=visible_events(self)
            ).select_related("event")
        )
        result = []
        for rehearsal in rehearsals:
            invitations = list(
                rehearsal.invitations.filter(active=True, musician__active=True).select_related(
                    "musician__membership__person"
                )
            )
            for o in recurrence.occurrences([rehearsal.event], *window()):
                members = []
                availability = Availability(
                    self.org,
                    [i.musician for i in invitations],
                    rehearsal.event,
                    *interval(rehearsal.event, o.starts_at, o.ends_at),
                )
                for invite in invitations:
                    response = invite.responses.filter(original_start=o.original_start).first()
                    members.append(
                        {
                            "invitation": invite.pk,
                            "name": str(invite.musician.membership.person)
                            if invite.musician.membership_id
                            else invite.musician.name,
                            "status": response.status if response else "pending",
                            "availability": availability.reasons(invite.musician),
                        }
                    )
                result.append(
                    {
                        "rehearsal": rehearsal.pk,
                        "event": rehearsal.event_id,
                        "title": rehearsal.event.title,
                        "original_start": o.original_start,
                        "starts_at": o.starts_at,
                        "ends_at": o.ends_at,
                        "cancelled": o.is_cancelled,
                        **program_for(rehearsal, o.original_start),
                        "members": members,
                    }
                )
        return Response(sorted(result, key=lambda r: r["starts_at"]))

    @transaction.atomic
    def post(self, request, org_id):
        invitation_id = serializers.IntegerField(min_value=1).run_validation(
            request.data.get("invitation")
        )
        invite = get_object_or_404(
            RehearsalInvitation.objects.select_for_update(),
            pk=invitation_id,
            organization=self.org,
            active=True,
            rehearsal__event__in=visible_events(self),
        )
        save_response(invite, request.data, request.user)
        return Response({"ok": True})


def save_response(invite, data, user):
    original = serializers.DateTimeField().run_validation(data.get("original_start"))
    status = serializers.ChoiceField(choices=["accepted", "declined"]).run_validation(
        data.get("status")
    )
    o = occurrence(invite.rehearsal.event, original)
    if o is None or o.is_cancelled or o.starts_at <= timezone.now():
        raise serializers.ValidationError(
            gettext("Für diesen Probentermin ist keine Rückmeldung mehr möglich.")
        )
    if status == "accepted":
        musician = Musician.objects.select_for_update().get(pk=invite.musician_id)
        ensure_available(
            musician,
            invite.rehearsal.event,
            *interval(invite.rehearsal.event, o.starts_at, o.ends_at),
        )
    row, _ = RehearsalResponse.objects.update_or_create(
        organization=invite.organization,
        invitation=invite,
        original_start=original,
        defaults={"status": status},
    )
    record(invite.organization, user, "update", row, {"Probenrückmeldung": [None, status]})


def loan_data(row):
    return {
        "id": row.pk,
        "part": row.part_id,
        "musician": row.musician_id,
        "quantity": row.quantity,
        "returned": row.returned,
        "issued_on": row.issued_on,
        "due_on": row.due_on,
        "overdue": row.returned < row.quantity and row.due_on < timezone.localdate(),
        "title": row.part.arrangement.piece.title,
        "instrument": row.part.instrument,
        "register": row.part.register,
        "returns": list(row.returns.values("quantity", "created_at")),
    }


class LoanView(PracticeOverview):
    def get(self, request, org_id):
        return Response(
            [
                loan_data(row)
                for row in ScoreLoan.objects.filter(organization=self.org)
                .select_related("part__arrangement__piece")
                .order_by("-pk")
            ]
        )

    @transaction.atomic
    def post(self, request, org_id):
        key = idempotency.claim(request, f"music.loan.{self.org.pk}", required=True)
        if key.done:
            return Response(
                loan_data(
                    get_object_or_404(ScoreLoan, organization=self.org, pk=key.result["loan"])
                )
            )
        quantity = serializers.IntegerField(min_value=1, max_value=10000).run_validation(
            request.data.get("quantity")
        )
        if request.data.get("action") == "issue":
            part_id = serializers.IntegerField(min_value=1).run_validation(request.data.get("part"))
            part = get_object_or_404(
                ScorePart.objects.select_for_update(), organization=self.org, pk=part_id
            )
            musician_id = serializers.IntegerField(min_value=1).run_validation(
                request.data.get("musician")
            )
            musician = get_object_or_404(
                Musician, organization=self.org, pk=musician_id, active=True
            )
            due = serializers.DateField().run_validation(request.data.get("due_on"))
            if due < timezone.localdate():
                raise serializers.ValidationError(
                    gettext("Die Rückgabefrist liegt vor der Ausgabe.")
                )
            outstanding = part.loans.aggregate(n=Sum(F("quantity") - F("returned")))["n"] or 0
            if quantity > part.copies - outstanding:
                raise serializers.ValidationError(
                    gettext("Es sind nicht genügend freie Notenexemplare vorhanden.")
                )
            row = ScoreLoan.objects.create(
                organization=self.org, part=part, musician=musician, quantity=quantity, due_on=due
            )
            record(self.org, request.user, "create", row, {"Notenausgabe": [None, quantity]})
        elif request.data.get("action") == "return":
            loan_id = serializers.IntegerField(min_value=1).run_validation(request.data.get("loan"))
            row = get_object_or_404(ScoreLoan, organization=self.org, pk=loan_id)
            # Gleiche Sperrreihenfolge wie bei der Ausgabe: Bestand, danach Ausgabebeleg.
            ScorePart.objects.select_for_update().get(pk=row.part_id)
            row = ScoreLoan.objects.select_for_update().get(pk=row.pk)
            if quantity > row.quantity - row.returned:
                raise serializers.ValidationError(
                    gettext("Die Rückgabe übersteigt die ausstehende Menge.")
                )
            ScoreReturn.objects.create(organization=self.org, loan=row, quantity=quantity)
            row.returned += quantity
            row.save(update_fields=["returned"])
            record(self.org, request.user, "update", row, {"Notenrückgabe": [None, quantity]})
        else:
            raise serializers.ValidationError(gettext("Unbekannte Notenausgabe-Aktion."))
        key.remember({"loan": row.pk})
        return Response(loan_data(row))
