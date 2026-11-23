"""Alle Verweise werden innerhalb der berechtigten Organisation aufgelöst."""

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils.translation import gettext
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from billing.models import BusinessPartner
from core.api_base import AuditMixin, OrgScopedMixin
from events import services

from .availability import ensure_performance
from .instrument_list import InstrumentField
from .models import Assignment, Musician, Performance, Position, Skill


def accepted(performance) -> bool:
    return performance.engagement_documents.filter(kind="offer", status="accepted").exists()


def validate_main(serializer, attrs):
    """Issue #711: weitere Tage hängen an einem Hauptauftritt und erben den Auftraggeber."""
    instance = serializer.instance
    if "main" not in attrs:
        main = instance.main if instance else None
        if main is not None:
            attrs["customer"] = main.customer
        return attrs
    main = attrs["main"]
    previous = instance.main if instance else None
    if main == previous:
        if main is not None:
            attrs["customer"] = main.customer
        return attrs
    if main is not None:
        view = serializer.context["view"]
        if instance and main.pk == instance.pk:
            raise serializers.ValidationError(
                gettext("Ein Auftritt kann nicht zu sich selbst gehören.")
            )
        if main.main_id:
            raise serializers.ValidationError(
                gettext("Bitte den Hauptauftritt wählen, nicht einen weiteren Tag.")
            )
        if instance and instance.days.exists():
            raise serializers.ValidationError(
                gettext("Dieser Auftritt hat selbst weitere Tage und bleibt Hauptauftritt.")
            )
        if not PerformanceViewSet.visible(view, main):
            raise serializers.ValidationError(gettext("Dieser Auftritt ist nicht verfügbar."))
        if accepted(main):
            raise serializers.ValidationError(
                gettext("Bitte zuerst die bestehende Zusage aufheben.")
            )
        if instance:
            own_contract(instance)
        attrs["customer"] = main.customer
    if previous is not None and accepted(previous):
        raise serializers.ValidationError(gettext("Bitte zuerst die bestehende Zusage aufheben."))
    return attrs


def own_contract(performance):
    """Ein Tag mit eigenem Vertrag oder eigener Abrechnung kann nicht angehängt werden."""
    from .models import EngagementDocument, MusicianClaim, PerformanceAccount

    account = PerformanceAccount.objects.filter(performance=performance).first()
    if (
        EngagementDocument.objects.filter(performance=performance).exists()
        or MusicianClaim.objects.filter(assignment__performance=performance).exists()
        or (
            account
            and (
                account.invoice_id
                or account.fee
                or account.travel
                or account.extras
                or account.payments.exists()
                or account.previous_invoices.exists()
            )
        )
    ):
        raise serializers.ValidationError(
            gettext(
                "Dieser Auftritt hat schon ein eigenes Angebot oder eine eigene Abrechnung "
                "und kann deshalb nicht angehängt werden."
            )
        )


class ScopedSerializer(serializers.ModelSerializer):
    def get_fields(self):
        fields = super().get_fields()
        org = getattr(self.context.get("view"), "org", None)
        for field in fields.values():
            if isinstance(field, serializers.PrimaryKeyRelatedField) and field.queryset is not None:
                field.queryset = (
                    field.queryset.filter(organization=org) if org else field.queryset.none()
                )
        return fields

    def validate(self, attrs):
        def value(key):
            return attrs.get(key, getattr(self.instance, key, None))

        if self.Meta.model is Musician and not value("membership") and not value("name"):
            raise serializers.ValidationError(gettext("Bitte Mitglied oder Gastnamen angeben."))
        if self.Meta.model is Performance:
            attrs = validate_main(self, attrs)
            for key in ("kind", "uniform_choice"):
                chosen = attrs.get(key)
                if (
                    chosen is not None
                    and not chosen.active
                    and chosen != getattr(self.instance, key, None)
                ):
                    raise serializers.ValidationError(
                        gettext("Archivierte Einträge lassen sich nicht neu wählen.")
                    )
            if (
                self.instance
                and accepted(self.instance.lead)
                and any(
                    k in attrs and attrs[k] != getattr(self.instance, k)
                    for k in [
                        "customer",
                        "meeting_at",
                        "meeting_place",
                        "setup_at",
                        "uniform",
                        "uniform_choice",
                        "formation",
                        "notes",
                        "event",
                        "main",
                    ]
                )
            ):
                raise serializers.ValidationError(
                    gettext("Bitte zuerst die bestehende Zusage aufheben.")
                )
            if (
                self.instance
                and "customer" in attrs
                and attrs["customer"] != self.instance.customer
            ):
                from .models import PerformanceAccount

                if PerformanceAccount.objects.filter(
                    performance=self.instance, invoice__isnull=False
                ).exists():
                    raise serializers.ValidationError(
                        gettext("Der Auftraggeber ist bereits mit einer Rechnung verbunden.")
                    )
            event = value("event")
            view = self.context["view"]
            if (
                "events" not in view.org.enabled_modules
                or "events.view" not in view.org_permissions
            ):
                raise serializers.ValidationError(
                    gettext("Für Auftritte ist Kalenderleserecht erforderlich.")
                )
            if (
                not services.org_viewer(view.request.user, view.org, view.org_permissions)
                .events()
                .filter(pk=event.pk, department=None)
                .exists()
            ):
                raise serializers.ValidationError(gettext("Dieser Termin ist nicht verfügbar."))
            if event.is_series or event.remote_uid:
                raise serializers.ValidationError(
                    gettext("Bitte einen eigenen Einzeltermin wählen.")
                )
            if value("meeting_at") and value("meeting_at") > event.starts_at:
                raise serializers.ValidationError(gettext("Der Treffpunkt liegt nach Spielbeginn."))
            if value("setup_at") and value("setup_at") > event.starts_at:
                raise serializers.ValidationError(gettext("Der Aufbau liegt nach Spielbeginn."))
        if self.Meta.model is Assignment:
            if value("position").performance_id != value("performance").pk:
                raise serializers.ValidationError(
                    gettext("Die Stimme gehört zu einem anderen Auftritt.")
                )
            if not value("musician").active:
                raise serializers.ValidationError(gettext("Dieser Musiker ist inaktiv."))
            from .scores import voice

            if voice(value("position").instrument, value("position").register) not in {
                voice(s.instrument, s.register) for s in value("musician").skills.all()
            }:
                raise serializers.ValidationError(
                    gettext("Für diese Stimme fehlt die instrumentale Fähigkeit.")
                )
            if value("status") != "declined":
                ensure_performance(value("musician"), value("performance"))
        if self.Meta.model is Position and self.instance:
            if self.instance.assignment_set.exists() and any(
                key in attrs and attrs[key] != getattr(self.instance, key)
                for key in ("instrument", "register")
            ):
                raise serializers.ValidationError(
                    gettext("Bitte zuerst die zugehörigen Einteilungen entfernen.")
                )
        return attrs


class MusicMusicianSerializer(ScopedSerializer):
    display_name = serializers.SerializerMethodField()

    def get_display_name(self, obj) -> str:
        return str(obj.membership.person) if obj.membership_id else obj.name

    @transaction.atomic
    def update(self, instance, validated_data):
        from django.utils import timezone

        from .models import GuestAccess, RehearsalGuestAccess

        instance = Musician.objects.select_for_update().get(pk=instance.pk)
        previous = (instance.guest_email, instance.membership_id)
        instance = super().update(instance, validated_data)
        if previous != (instance.guest_email, instance.membership_id):
            GuestAccess.objects.filter(assignment__musician=instance).update(
                revoked_at=timezone.now(),
                auto_notify=False,
            )
            RehearsalGuestAccess.objects.filter(invitation__musician=instance).update(
                revoked_at=timezone.now()
            )
        return instance

    class Meta:
        model = Musician
        fields = ["id", "membership", "name", "display_name", "contact", "guest_email", "active"]


class MusicSkillSerializer(ScopedSerializer):
    instrument = InstrumentField()

    class Meta:
        model = Skill
        fields = ["id", "musician", "instrument", "register", "primary"]


class MusicPerformanceSerializer(ScopedSerializer):
    title = serializers.CharField(source="event.title", read_only=True)
    starts_at = serializers.DateTimeField(source="event.starts_at", read_only=True)
    ends_at = serializers.DateTimeField(source="event.ends_at", read_only=True)
    location = serializers.CharField(source="event.location", read_only=True)
    cancelled = serializers.BooleanField(source="event.is_cancelled", read_only=True)
    # Veranstaltung (Finanzen), zu der der Termin gehört (Issue #711)
    project = serializers.IntegerField(source="event.project_id", read_only=True)
    kind_name = serializers.SerializerMethodField()
    uniform_text = serializers.SerializerMethodField()
    uniform_details = serializers.SerializerMethodField()
    days = serializers.SerializerMethodField()

    def get_kind_name(self, obj) -> str:
        return obj.kind.name if obj.kind_id else ""

    def get_uniform_text(self, obj) -> str:
        return obj.uniform_text()

    def get_uniform_details(self, obj) -> dict | None:
        return obj.uniform_details()

    def get_days(self, obj) -> list[int]:
        return sorted(day.pk for day in obj.days.all())

    class Meta:
        model = Performance
        fields = [
            "id",
            "event",
            "title",
            "starts_at",
            "ends_at",
            "location",
            "cancelled",
            "project",
            "main",
            "days",
            "kind",
            "kind_name",
            "customer",
            "meeting_at",
            "meeting_place",
            "setup_at",
            "uniform_choice",
            "uniform",
            "uniform_text",
            "uniform_details",
            "formation",
            "notes",
            "remind_days",
        ]


class MusicPositionSerializer(ScopedSerializer):
    required = serializers.IntegerField(min_value=1, max_value=500)
    instrument = InstrumentField()

    class Meta:
        model = Position
        fields = ["id", "performance", "instrument", "register", "required"]


class MusicAssignmentSerializer(ScopedSerializer):
    class Meta:
        model = Assignment
        fields = ["id", "performance", "position", "musician", "status"]


class MusicViewSet(OrgScopedMixin, AuditMixin, viewsets.ModelViewSet):
    read_permission = "music.view"
    write_permission = "music.edit"
    allowed_org_types = ("club", "federation")
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if "music" not in self.org.enabled_modules:
            raise NotFound()

    def get_queryset(self):
        qs = self.serializer_class.Meta.model.objects.filter(organization=self.org).order_by("pk")
        # Kalenderfreigaben gelten auch für alle Besetzungsdaten.
        if qs.model in (Performance, Position, Assignment):
            if (
                "events.view" not in self.org_permissions
                or "events" not in self.org.enabled_modules
            ):
                return qs.none()
            events = (
                services.org_viewer(self.request.user, self.org, self.org_permissions)
                .events()
                .filter(organization=self.org, department=None)
            )
            qs = qs.filter(
                **{"event__in" if qs.model is Performance else "performance__event__in": events}
            )
        return qs

    def get_create_kwargs(self):
        return {"organization": self.org}

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except ProtectedError as exc:
            raise serializers.ValidationError(
                gettext("Bitte zuerst die zugehörigen Einteilungen entfernen.")
            ) from exc

    @transaction.atomic
    def perform_create(self, serializer):
        # Auch indirekte Auftrittsverweise müssen sichtbar sein.
        performance = serializer.validated_data.get("performance")
        if performance and not PerformanceViewSet.visible(self, performance):
            raise NotFound()
        super().perform_create(serializer)

    def perform_update(self, serializer):
        for key in ("performance", "musician", "position", "event", "membership"):
            if key in serializer.validated_data and serializer.validated_data[key] != getattr(
                serializer.instance, key
            ):
                raise serializers.ValidationError(
                    gettext("Bestehende Verknüpfungen können nicht umgehängt werden.")
                )
        super().perform_update(serializer)

    @action(detail=False, methods=["get"])
    def choices(self, request, org_id):
        events = []
        if "events.view" in self.org_permissions and "events" in self.org.enabled_modules:
            events = list(
                services.org_viewer(request.user, self.org, self.org_permissions)
                .events()
                .filter(organization=self.org, department=None, repeat="none", remote_uid="")
                .values("id", "title")
            )
        partners = []
        if self.org_permissions & {"billing.view", "finance.view"}:
            partners = [
                {"id": row.pk, "name": row.name}
                for row in BusinessPartner.objects.filter(organization=self.org, is_active=True)
            ]
        # Mitglieder wählt die Oberfläche per Suche (Gesamtaudit 11.11., P-04): keine Liste
        # aller Mitglieder mit entschlüsselten Namen bei jedem Öffnen des Musikbereichs.
        return Response({"events": events, "partners": partners})


class MusicianViewSet(MusicViewSet):
    serializer_class = MusicMusicianSerializer


class SkillViewSet(MusicViewSet):
    serializer_class = MusicSkillSerializer
    http_method_names = [*MusicViewSet.http_method_names, "delete"]


class PerformanceViewSet(MusicViewSet):
    serializer_class = MusicPerformanceSerializer

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("event", "kind", "uniform_choice")
            .prefetch_related("days")
        )

    @transaction.atomic
    def perform_update(self, serializer):
        from .models import PerformanceAccount

        Performance.objects.select_for_update().get(pk=serializer.instance.pk)
        super().perform_update(serializer)
        instance = serializer.instance
        if instance.main_id:
            # Leere eigene Abrechnung eines angehängten Tages (nur Lesen/Öffnen) fällt weg
            PerformanceAccount.objects.filter(performance=instance, invoice__isnull=True).delete()
        # Auftraggeber gilt für alle Tage des Vertrags
        Performance.objects.filter(main=instance).exclude(customer=instance.customer).update(
            customer=instance.customer
        )

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def combine(self, request, org_id, pk):
        """Alle Auftritte derselben Veranstaltung als weitere Tage an diesen hängen."""
        lead = self.get_object()
        Performance.objects.select_for_update().get(pk=lead.pk)
        if lead.main_id:
            raise serializers.ValidationError(
                gettext("Bitte den Hauptauftritt wählen, nicht einen weiteren Tag.")
            )
        if not lead.event.project_id:
            raise serializers.ValidationError(gettext("Der Termin gehört zu keiner Veranstaltung."))
        added, skipped = [], []
        candidates = (
            self.get_queryset()
            .filter(event__project_id=lead.event.project_id)
            .exclude(pk=lead.pk)
            .exclude(main=lead)
            .order_by("event__starts_at", "pk")
        )
        for day in candidates:
            serializer = self.get_serializer(day, data={"main": lead.pk}, partial=True)
            try:
                with transaction.atomic():
                    serializer.is_valid(raise_exception=True)
                    self.perform_update(serializer)
                added.append(day.pk)
            except serializers.ValidationError as exc:
                detail = exc.detail
                text = (
                    " ".join(str(v) for v in detail)
                    if isinstance(detail, list)
                    else " ".join(
                        str(x) for v in detail.values() for x in (v if isinstance(v, list) else [v])
                    )
                    if isinstance(detail, dict)
                    else str(detail)
                )
                skipped.append({"id": day.pk, "title": day.event.title, "reason": text})
        return Response({"added": added, "skipped": skipped})

    @action(detail=False, methods=["get"])
    def overview(self, request, org_id):
        from .overview import result

        return result(self, request)

    def visible(self, performance):
        return (
            services.org_viewer(self.request.user, self.org, self.org_permissions)
            .events()
            .filter(pk=performance.event_id)
            .exists()
            and "events.view" in self.org_permissions
            and "events" in self.org.enabled_modules
        )


class PerformanceChildViewSet(MusicViewSet):
    """Einzeländerungen teilen sich die Auftrittssperre mit Sammeländerungen."""

    def lock_performance(self, pk):
        Performance.objects.select_for_update().get(pk=pk, organization=self.org)

    @transaction.atomic
    def perform_create(self, serializer):
        self.lock_performance(serializer.validated_data["performance"].pk)
        if self.serializer_class.Meta.model is Assignment:
            Musician.objects.select_for_update().get(pk=serializer.validated_data["musician"].pk)
        fresh = self._revalidate(serializer)
        super().perform_create(fresh)
        serializer.instance = fresh.instance

    @transaction.atomic
    def perform_update(self, serializer):
        self.lock_performance(serializer.instance.performance_id)
        if isinstance(serializer.instance, Assignment):
            Musician.objects.select_for_update().get(pk=serializer.instance.musician_id)
        self._lock_and_refresh(serializer.instance)
        super().perform_update(self._revalidate(serializer))

    @transaction.atomic
    def perform_destroy(self, instance):
        self.lock_performance(instance.performance_id)
        if isinstance(instance, Assignment):
            Musician.objects.select_for_update().get(pk=instance.musician_id)
        super().perform_destroy(instance)


class PositionViewSet(PerformanceChildViewSet):
    serializer_class = MusicPositionSerializer
    http_method_names = [*MusicViewSet.http_method_names, "delete"]


class AssignmentViewSet(PerformanceChildViewSet):
    serializer_class = MusicAssignmentSerializer
    http_method_names = [*MusicViewSet.http_method_names, "delete"]
