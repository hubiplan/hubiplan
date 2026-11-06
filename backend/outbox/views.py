"""Postausgang je Organisation und Test-Postfach der Plattform."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import AUDIT_VIEW, ORG_EDIT
from audit.log import diff, record, snapshot
from core.api_base import OrgScopedMixin
from core.listing import ListPagination, search
from core.tenancy import rls_bypass
from organizations.views import IsPlatformAdmin

from .models import OutgoingMail


class OutgoingMailSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    organization_name = serializers.CharField(
        source="organization.display_name", read_only=True, default=None
    )
    attachments = serializers.SerializerMethodField()

    class Meta:
        model = OutgoingMail
        fields = [
            "id",
            "created_at",
            "organization_name",
            "to",
            "reply_to",
            "subject",
            "body",
            "kind",
            "status",
            "status_label",
            "error",
            "attachments",
        ]

    def to_representation(self, obj):
        data = super().to_representation(obj)
        data["content_hidden"] = self.context.get("platform", False) and not _platform_may_read(obj)
        if data["content_hidden"]:
            data["body"] = ""
            data["error"] = ""
        return data

    def get_attachments(self, obj) -> list[dict]:
        return [
            {"index": i, "name": a["name"], "size": a["size"]}
            for i, a in enumerate(obj.attachments or [])
        ]


def _platform_may_read(mail: OutgoingMail) -> bool:
    """Plattform-Betreuung: Inhalt nur bei Mails ohne Verein (Plattform selbst) oder mit
    Freigabe des Vereins (Gesamtaudit 05.11. F-04)."""
    return mail.organization is None or mail.organization.outbox_platform_content


def _attachment_response(mail: OutgoingMail, index: int) -> FileResponse:
    try:
        item = mail.attachments[index]
    except (IndexError, TypeError) as exc:
        raise Http404 from exc
    root = Path(settings.PRIVATE_ROOT).resolve()
    path = (root / item["path"]).resolve()
    if root not in path.parents or not path.exists():
        raise Http404
    from exchange.models import private_storage

    return FileResponse(
        # Über den privaten Speicher: entschlüsselt Anhänge aus Rundschreiben
        private_storage().open(str(path.relative_to(root)), "rb"),
        as_attachment=True,
        filename=item["name"],
        content_type=item.get("content_type") or "application/octet-stream",
    )


def _filtered(qs, params):
    """Suche in Empfänger und Betreff, Zeitraum und Status."""
    if params.get("status") in OutgoingMail.Status.values:
        qs = qs.filter(status=params["status"])
    return search(qs, params, ("to", "subject"), "created_at")


class OrgOutboxView(OrgScopedMixin, generics.ListAPIView):
    """Mails, die diese Organisation versendet hat (mit Suche und Seiten)."""

    serializer_class = OutgoingMailSerializer
    read_permission = AUDIT_VIEW
    pagination_class = ListPagination

    def get_queryset(self):
        qs = OutgoingMail.objects.filter(organization=self.org).select_related("organization")
        return _filtered(qs, self.request.query_params)


class OrgOutboxAttachmentView(OrgScopedMixin, APIView):
    read_permission = AUDIT_VIEW

    def get(self, request, org_id: int, pk: int, index: int):
        mail = get_object_or_404(OutgoingMail, organization=self.org, pk=pk)
        return _attachment_response(mail, index)


class PlatformOutboxView(generics.ListAPIView):
    """Test-Postfach: alle Mails der Instanz (nur Plattform-Administration)."""

    serializer_class = OutgoingMailSerializer
    permission_classes = [IsPlatformAdmin]
    pagination_class = ListPagination

    def list(self, request, *args, **kwargs):
        with rls_bypass():
            qs = _filtered(
                OutgoingMail.objects.select_related("organization"), request.query_params
            )
            page = self.paginate_queryset(qs)
            data = self.get_serializer(page, many=True, context={"platform": True}).data
            return self.get_paginated_response(data)


class PlatformOutboxAttachmentView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request, pk: int, index: int):
        with rls_bypass():
            mail = get_object_or_404(OutgoingMail.objects.select_related("organization"), pk=pk)
            if not _platform_may_read(mail):
                raise Http404
        return _attachment_response(mail, index)


class OrgOutboxSettingsView(OrgScopedMixin, APIView):
    """Freigabe der Inhalte für die Plattform-Betreuung (Gesamtaudit 05.11. F-04)."""

    read_permission = AUDIT_VIEW
    write_permission = ORG_EDIT

    def get(self, request, org_id: int):
        return Response({"platform_content": self.org.outbox_platform_content})

    def patch(self, request, org_id: int):
        value = request.data.get("platform_content")
        if not isinstance(value, bool):
            raise serializers.ValidationError(
                {"platform_content": gettext("Bitte ja oder nein angeben.")}
            )
        before = snapshot(self.org)
        self.org.outbox_platform_content = value
        self.org.save(update_fields=["outbox_platform_content"])
        record(self.org, request.user, "update", self.org, diff(before, snapshot(self.org)))
        return Response({"platform_content": value})
