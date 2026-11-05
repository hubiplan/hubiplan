"""Verwaltung der Dokumente der Webseite (Pressespiegel, eigene Dokumente; Ralf 05.11.)."""

from __future__ import annotations

from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record

from . import documents
from .content_models import WebsiteDocument
from .content_views import _ContentMixin


class DocumentSerializer(serializers.Serializer):
    section = serializers.ChoiceField(choices=WebsiteDocument.Section.choices, required=False)
    title = serializers.CharField(max_length=200)
    source = serializers.CharField(max_length=200, required=False, allow_blank=True)
    date = serializers.DateField(required=False, allow_null=True)
    published = serializers.BooleanField(required=False)


def document_data(org_id: int, d: WebsiteDocument) -> dict:
    base = f"/api/orgs/{org_id}/website/documents/{d.pk}/file/"
    return {
        "id": d.pk,
        "section": d.section,
        "title": d.title,
        "source": d.source,
        "date": d.date,
        "published": d.published,
        "kind": "pdf" if d.content_type == "application/pdf" else "image",
        "size": d.size,
        "file_name": d.file_name,
        "url": base,
        "preview_url": f"{base}?size=small" if d.preview.name else None,
        "uploaded_at": d.uploaded_at,
    }


class DocumentListView(_ContentMixin, APIView):
    """GET: Dokumente · POST: Datei hochladen (PDF oder Bild)."""

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, org_id: int):
        website = self.website()
        rows = WebsiteDocument.objects.filter(website=website)
        return Response([document_data(self.org.pk, d) for d in rows])

    @transaction.atomic
    def post(self, request, org_id: int):
        website = self.website()
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": gettext("Bitte eine Datei auswählen.")})
        ser = DocumentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        doc = documents.store(
            website,
            upload,
            section=v.get("section") or WebsiteDocument.Section.PRESS,
            title=v["title"],
            source=v.get("source", ""),
            date=v.get("date"),
            user=request.user,
        )
        # Formulardaten: ein fehlender Schalter gälte sonst als „aus“
        if "published" in request.data:
            doc.published = v["published"]
            doc.save(update_fields=["published"])
        record(self.org, request.user, "create", doc, {"Dokument": [None, doc.title]})
        return Response(document_data(self.org.pk, doc), status=status.HTTP_201_CREATED)


class _DocumentMixin(_ContentMixin):
    def document(self) -> WebsiteDocument:
        return get_object_or_404(WebsiteDocument, website=self.website(), pk=self.kwargs["pk"])


class DocumentDetailView(_DocumentMixin, APIView):
    """PATCH: Angaben ändern · DELETE: löschen."""

    @transaction.atomic
    def patch(self, request, org_id: int, pk: int):
        doc = self.document()
        ser = DocumentSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        changes = {}
        for field, value in ser.validated_data.items():
            old = getattr(doc, field)
            if old != value:
                changes[field] = [str(old), str(value)]
                setattr(doc, field, value)
        if changes:
            doc.save()
            record(self.org, request.user, "update", doc, changes)
        return Response(document_data(self.org.pk, doc))

    @transaction.atomic
    def delete(self, request, org_id: int, pk: int):
        doc = self.document()
        record(self.org, request.user, "delete", doc, {"Dokument": [doc.title, None]})
        documents.delete(doc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentFileView(_DocumentMixin, APIView):
    def get(self, request, org_id: int, pk: int):
        doc = self.document()
        if request.query_params.get("size") == "small" and doc.preview.name:
            f = doc.preview
            ctype = "image/png" if f.name.endswith(".png") else "image/jpeg"
        else:
            f, ctype = doc.file, doc.content_type
        response = FileResponse(f.open("rb"), content_type=ctype)
        response["Content-Disposition"] = "inline"
        response["X-Content-Type-Options"] = "nosniff"
        return response
