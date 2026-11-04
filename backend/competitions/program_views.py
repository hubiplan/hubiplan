"""Schießbedingungen unabhängig von den daraus berechneten Ranglisten."""

from django.db import transaction
from django.db.models import Count, F, Max
from django.utils.translation import gettext
from rest_framework import serializers, viewsets
from rest_framework.exceptions import ValidationError

from core.api_base import AuditMixin

from . import target_views, targets
from .models import Competition, Score, Scoring, ShootingProgram
from .views import ScoringSerializer, _Mixin

CONDITIONS = ("target", "custom_target", "shots", "position", "distance")


class ProgramSerializer(serializers.ModelSerializer):
    target_info = serializers.SerializerMethodField()
    has_results = serializers.SerializerMethodField()
    confirm_recalculation = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = ShootingProgram
        fields = [
            "id",
            "competition",
            "name",
            "sort_order",
            "target",
            "custom_target",
            "shots",
            "position",
            "distance",
            "target_info",
            "has_results",
            "confirm_recalculation",
        ]
        read_only_fields = ["competition", "sort_order"]

    validate_target = ScoringSerializer.validate_target
    validate_custom_target = ScoringSerializer.validate_custom_target

    def get_target_info(self, obj):
        target = targets.get(obj.target, obj.custom_target) if obj.target else None
        return target.as_dict() if target else None

    def get_has_results(self, obj):
        return obj.hits.exists() or Score.objects.filter(scoring__program=obj).exists()

    def validate(self, attrs):
        comp = self.context["competition"]
        if not comp.own or comp.form != Competition.Form.RANKING:
            raise ValidationError(gettext("Schießdurchgänge gibt es nur bei eigenen Ranglisten."))
        if comp.status == Competition.Status.FINAL:
            raise ValidationError(gettext("Der Wettbewerb ist endgültig abgeschlossen."))
        if "name" in attrs:
            attrs["name"] = attrs["name"].strip()
            if not attrs["name"]:
                raise ValidationError({"name": gettext("Bitte eine Bezeichnung angeben.")})
        get = lambda key: attrs.get(key, getattr(self.instance, key, None))  # noqa: E731
        target = get("target")
        if target == targets.CUSTOM and not get("custom_target"):
            raise ValidationError(
                {"custom_target": gettext("Bitte die Maße der eigenen Scheibe angeben.")}
            )
        if get("shots") is not None and not 1 <= get("shots") <= target_views.MAX_HITS:
            raise ValidationError({"shots": gettext("Bitte 1 bis 200 Schüsse angeben.")})
        if (
            self.instance
            and get("shots")
            and self.instance.hits.values("starter_id")
            .annotate(n=Count("pk"))
            .filter(n__gt=get("shots"))
            .exists()
        ):
            raise ValidationError(
                {
                    "shots": gettext(
                        "Es sind bereits mehr Treffer erfasst. Bitte zuerst die Treffer prüfen."
                    )
                }
            )
        if get("distance") == 0:
            raise ValidationError({"distance": gettext("Bitte eine positive Entfernung angeben.")})
        distances = targets.get(target).as_dict()["distances"] if target in targets.BY_KEY else []
        if get("distance") and distances and get("distance") not in distances:
            raise ValidationError({"distance": gettext("Die Entfernung passt nicht zur Scheibe.")})
        if self.instance and any(
            key in attrs and attrs[key] != getattr(self.instance, key) for key in CONDITIONS
        ):
            if self.get_has_results(self.instance) and not attrs.get("confirm_recalculation"):
                raise ValidationError(
                    {
                        "confirm_recalculation": gettext(
                            "Die Änderung betrifft vorhandene Ergebnisse. "
                            "Bitte die Neuberechnung bestätigen."
                        )
                    }
                )
            for scoring in self.instance.scorings.all():
                data = {key: get(key) for key in ("target", "custom_target", "shots")}
                if not target:
                    data["method"] = Scoring.Method.FREE
                elif not self.instance.target and scoring.method == Scoring.Method.FREE:
                    data["method"] = Scoring.Method.RINGS
                validator = ScoringSerializer(
                    scoring,
                    data=data,
                    partial=True,
                    context={"competition": comp, "program_update": True},
                )
                validator.is_valid(raise_exception=True)
        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_recalculation", None)
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        validated_data.pop("confirm_recalculation", None)
        changed = any(
            key in validated_data and validated_data[key] != getattr(instance, key)
            for key in CONDITIONS
        )
        previous_target = instance.target
        instance = super().update(instance, validated_data)
        if changed:
            groups = []
            for program in instance.competition.programs.all():
                target = targets.BY_KEY.get(program.target)
                if target and target.group not in groups:
                    groups.append(target.group)
            Competition.objects.filter(pk=instance.competition_id).update(
                discipline=" / ".join(groups)
            )
            for scoring in instance.scorings.all():
                data = {key: getattr(instance, key) for key in ("target", "custom_target", "shots")}
                if not instance.target:
                    data["method"] = Scoring.Method.FREE
                elif not previous_target and scoring.method == Scoring.Method.FREE:
                    data["method"] = Scoring.Method.RINGS
                serializer = ScoringSerializer(
                    scoring,
                    data=data,
                    partial=True,
                    context={"competition": instance.competition, "program_update": True},
                )
                serializer.is_valid(raise_exception=True)
                scoring = serializer.save()
                request = self.context["request"]
                target_views.recompute_all(
                    instance.organization, request.user, instance.competition, scoring
                )
            # Alte Offline-Treffer wurden unter anderen Bedingungen erfasst.
            Competition.objects.filter(pk=instance.competition_id).update(
                generation=F("generation") + 1
            )
        return instance


class ProgramViewSet(_Mixin, AuditMixin, viewsets.ModelViewSet):
    serializer_class = ProgramSerializer

    def get_queryset(self):
        return ShootingProgram.objects.filter(
            organization=self.org, competition_id=self.kwargs["competition_id"]
        )

    def get_serializer_context(self):
        return {
            **super().get_serializer_context(),
            "competition": self.competition(self.kwargs["competition_id"]),
        }

    def get_create_kwargs(self):
        comp = self.competition(self.kwargs["competition_id"])
        order = comp.programs.aggregate(last=Max("sort_order"))["last"] or 0
        return {"organization": self.org, "competition": comp, "sort_order": order + 1}

    @transaction.atomic
    def perform_update(self, serializer):
        comp = Competition.objects.select_for_update().get(pk=serializer.instance.competition_id)
        serializer.context["competition"] = comp
        super().perform_update(self._revalidate(serializer))

    @transaction.atomic
    def perform_create(self, serializer):
        comp = Competition.objects.select_for_update().get(pk=serializer.context["competition"].pk)
        serializer.context["competition"] = comp
        fresh = self._revalidate(serializer)
        super().perform_create(fresh)
        serializer.instance = fresh.instance

    @transaction.atomic
    def perform_destroy(self, instance):
        comp = Competition.objects.select_for_update().get(pk=instance.competition_id)
        if comp.status == Competition.Status.FINAL:
            raise ValidationError(gettext("Der Wettbewerb ist endgültig abgeschlossen."))
        if instance.scorings.exists() or instance.hits.exists():
            raise ValidationError(
                gettext("Dieser Durchgang wird noch von Wertungen oder Treffern verwendet.")
            )
        super().perform_destroy(instance)
