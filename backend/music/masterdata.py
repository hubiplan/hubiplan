"""Uniformen und Auftrittsarten je Einheit (Issues #712 und #713)."""

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext, gettext_noop
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from core.api_base import OrgScopedMixin
from core.i18n import language_of
from core.tenancy import tenant_context

from .models import FORMATIONS, Assignment, PerformanceKind, Uniform
from .views import MusicViewSet, ScopedSerializer

MAX_CHECKLIST = 30

# Vorbelegte Auftrittsarten mit Vorschlag für die Spielform (Issue #713)
DEFAULT_KINDS = [
    (gettext_noop("Umzug"), "march"),
    (gettext_noop("Parade"), "march"),
    (gettext_noop("Zapfenstreich"), "standing"),
    (gettext_noop("Fackelumzug"), "march"),
    (gettext_noop("Frühschoppen"), "seated"),
    (gettext_noop("Biwak"), "seated"),
    (gettext_noop("Konzert"), "seated"),
    (gettext_noop("Martinsumzug"), "march"),
    (gettext_noop("Karneval"), "march"),
    (gettext_noop("Ständchen"), "standing"),
]


def ensure_default_kinds(org):
    """Legt die vorbelegten Arten einmal an, solange die Einheit noch keine hat."""
    if PerformanceKind.objects.filter(organization=org).exists():
        return
    with language_of(org):
        for name, formation in DEFAULT_KINDS:
            PerformanceKind.objects.get_or_create(
                organization=org, name=gettext(name), defaults={"formation": formation}
            )


class ChecklistField(serializers.ListField):
    child = serializers.CharField(max_length=200)

    def to_internal_value(self, data):
        items = [item.strip() for item in super().to_internal_value(data) if item.strip()]
        if len(items) > MAX_CHECKLIST:
            raise serializers.ValidationError(
                gettext("Höchstens %(n)d Punkte in der Checkliste.") % {"n": MAX_CHECKLIST}
            )
        return items


class UniformSerializer(ScopedSerializer):
    checklist = ChecklistField(required=False)
    has_image = serializers.SerializerMethodField()

    def get_has_image(self, obj) -> bool:
        return bool(obj.image)

    class Meta:
        model = Uniform
        fields = ["id", "name", "description", "checklist", "has_image", "active"]


class PerformanceKindSerializer(ScopedSerializer):
    formation = serializers.ChoiceField(
        choices=[("", ""), *FORMATIONS], required=False, allow_blank=True
    )

    class Meta:
        model = PerformanceKind
        fields = ["id", "name", "formation", "uniform", "on_website", "active"]


class NamedViewSet(MusicViewSet):
    http_method_names = [*MusicViewSet.http_method_names, "delete"]

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                super().perform_create(serializer)
        except IntegrityError as exc:
            raise serializers.ValidationError(gettext("Dieser Name ist schon vergeben.")) from exc

    def perform_update(self, serializer):
        try:
            with transaction.atomic():
                super().perform_update(serializer)
        except IntegrityError as exc:
            raise serializers.ValidationError(gettext("Dieser Name ist schon vergeben.")) from exc

    def perform_destroy(self, instance):
        try:
            with transaction.atomic():
                super().perform_destroy(instance)
        except ProtectedError as exc:
            raise serializers.ValidationError(
                gettext("Wird noch bei Auftritten verwendet. Bitte stattdessen archivieren.")
            ) from exc


class UniformViewSet(NamedViewSet):
    serializer_class = UniformSerializer

    def perform_destroy(self, instance):
        image = instance.image.name if instance.image else ""
        super().perform_destroy(instance)
        if image:
            instance.image.storage.delete(image)


class PerformanceKindViewSet(NamedViewSet):
    serializer_class = PerformanceKindSerializer

    def list(self, request, *args, **kwargs):
        ensure_default_kinds(self.org)
        return super().list(request, *args, **kwargs)


def image_response(uniform):
    if not uniform.image:
        raise NotFound()
    response = FileResponse(uniform.image.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class UniformImageView(OrgScopedMixin, APIView):
    """Bild einer Uniform: lesen mit Musikleserecht, hochladen/entfernen mit Bearbeitungsrecht."""

    read_permission = "music.view"
    write_permission = "music.edit"
    allowed_org_types = ("club", "federation")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if "music" not in self.org.enabled_modules:
            raise NotFound()

    def uniform(self, pk, lock=False):
        qs = Uniform.objects.filter(organization=self.org)
        return get_object_or_404(qs.select_for_update() if lock else qs, pk=pk)

    def data(self, uniform):
        return UniformSerializer(uniform, context={"view": self}).data

    def get(self, request, org_id, pk):
        return image_response(self.uniform(pk))

    @transaction.atomic
    def post(self, request, org_id, pk):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from documents.services import check_budget
        from materials.services import image_content

        uniform = self.uniform(pk, lock=True)
        content = image_content(request.FILES.get("file"), request)
        try:
            check_budget(self.org, content.size)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        old = uniform.image.name if uniform.image else ""
        uniform.image.save("uniform.jpg", content, save=True)
        if old:
            uniform.image.storage.delete(old)
        record(self.org, request.user, "update", uniform, {"Bild": [bool(old), True]})
        return Response(self.data(uniform))

    @transaction.atomic
    def delete(self, request, org_id, pk):
        uniform = self.uniform(pk, lock=True)
        if uniform.image:
            old = uniform.image.name
            uniform.image = ""
            uniform.save(update_fields=["image"])
            uniform.image.storage.delete(old)
            record(self.org, request.user, "update", uniform, {"Bild": [True, False]})
        return Response(self.data(uniform))


class OwnUniformImage(APIView):
    """Bild der Uniform für eingeteilte Musiker im Mitgliederbereich."""

    def get(self, request, access_id, pk):
        from portal.views import _portal_access

        access = _portal_access(request.user, access_id)
        if "music" not in access.organization.enabled_modules:
            raise NotFound()
        with tenant_context(access.organization_id, request.user.pk):
            assigned = Assignment.objects.filter(
                organization=access.organization,
                musician__membership_id=access.membership_id,
                musician__active=True,
                performance__uniform_choice_id=pk,
            ).exists()
            if not assigned:
                raise NotFound()
            return image_response(
                get_object_or_404(Uniform, organization=access.organization, pk=pk)
            )
