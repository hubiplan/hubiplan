"""Abwesenheitszeiträume für die Musikverwaltung und den eigenen Mitgliederzugang."""

from types import SimpleNamespace

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from changes import idempotency
from core.tenancy import tenant_context
from portal.views import _portal_access

from .models import Musician, MusicianAbsence
from .practice_portal import own_musician
from .views import MusicViewSet, ScopedSerializer


class AbsenceSerializer(ScopedSerializer):
    class Meta:
        model = MusicianAbsence
        fields = ["id", "musician", "starts_at", "ends_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        musician = attrs.get("musician", getattr(self.instance, "musician", None))
        if self.instance and musician.pk != self.instance.musician_id:
            raise serializers.ValidationError(
                gettext("Bestehende Verknüpfungen können nicht umgehängt werden.")
            )
        start = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        end = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if end <= start:
            raise serializers.ValidationError(
                gettext("Das Ende der Abwesenheit muss nach dem Beginn liegen.")
            )
        if not musician.active:
            raise serializers.ValidationError(gettext("Dieser Musiker ist inaktiv."))
        return attrs


class AbsenceViewSet(MusicViewSet):
    serializer_class = AbsenceSerializer
    http_method_names = [*MusicViewSet.http_method_names, "delete"]

    def get_queryset(self):
        return super().get_queryset().order_by("starts_at", "pk")

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        key = idempotency.claim(request, f"music.absence.{self.org.pk}", required=True)
        if key.done:
            return Response(key.result, status=201)
        response = super().create(request, *args, **kwargs)
        key.remember(response.data)
        return response

    @transaction.atomic
    def perform_create(self, serializer):
        Musician.objects.select_for_update().get(pk=serializer.validated_data["musician"].pk)
        fresh = self._revalidate(serializer)
        super().perform_create(fresh)
        serializer.instance = fresh.instance

    @transaction.atomic
    def perform_update(self, serializer):
        Musician.objects.select_for_update().get(pk=serializer.instance.musician_id)
        self._lock_and_refresh(serializer.instance)
        super().perform_update(self._revalidate(serializer))

    @transaction.atomic
    def perform_destroy(self, instance):
        Musician.objects.select_for_update().get(pk=instance.musician_id)
        super().perform_destroy(instance)


class OwnAbsences(APIView):
    def get(self, request, access_id):
        access = _portal_access(request.user, access_id)
        with tenant_context(access.organization_id, request.user.pk):
            musician = own_musician(access)
            return Response(
                {
                    "enabled": bool(musician),
                    "items": AbsenceSerializer(musician.absences.all(), many=True).data
                    if musician
                    else [],
                }
            )

    @transaction.atomic
    def post(self, request, access_id):
        access = _portal_access(request.user, access_id)
        with tenant_context(access.organization_id, request.user.pk):
            musician = own_musician(access)
            if not musician:
                raise NotFound()
            Musician.objects.select_for_update().get(pk=musician.pk)
            key = idempotency.claim(request, f"music.own_absence.{access.pk}", required=True)
            if key.done:
                return Response(key.result)
            action = serializers.ChoiceField(choices=["save", "delete"]).run_validation(
                request.data.get("action")
            )
            row = None
            if request.data.get("id") is not None:
                pk = serializers.IntegerField(min_value=1).run_validation(request.data["id"])
                row = get_object_or_404(
                    MusicianAbsence.objects.select_for_update(),
                    pk=pk,
                    musician=musician,
                    organization=access.organization,
                )
            if action == "delete":
                if row is None:
                    raise NotFound()
                record(
                    access.organization,
                    request.user,
                    "delete",
                    row,
                    {"Abwesenheit": [row.pk, None]},
                )
                row.delete()
                result = {"ok": True}
            else:
                view = SimpleNamespace(org=access.organization)
                serializer = AbsenceSerializer(
                    row,
                    data={
                        "musician": musician.pk,
                        "starts_at": request.data.get("starts_at"),
                        "ends_at": request.data.get("ends_at"),
                    },
                    context={"view": view},
                )
                serializer.is_valid(raise_exception=True)
                row = serializer.save(organization=access.organization)
                record(
                    access.organization,
                    request.user,
                    "update",
                    row,
                    {
                        "Abwesenheit": [
                            None,
                            {
                                "starts_at": row.starts_at.isoformat(),
                                "ends_at": row.ends_at.isoformat(),
                            },
                        ]
                    },
                )
                result = dict(serializer.data)
            key.remember(result)
            return Response(result)
