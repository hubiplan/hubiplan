"""Dokumente an der Partnerakte und Serienbrief an Partnergruppen (Konzept
geschaeftspartner.md, P5)."""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import diff, record, snapshot
from documents.services import check_budget, check_upload, clean_name, storage_name

from .agreements import greeting, recipient_lines
from .models import BusinessPartner, PartnerAgreement, PartnerDocument
from .partners import PartnerAccess

LETTER_MAX = 5000
LETTERS_MAX = 500


def document_data(org_id: int, doc: PartnerDocument) -> dict:
    return {
        "id": doc.pk,
        "title": doc.title,
        "name": doc.name,
        "size": doc.size,
        "content_type": doc.content_type,
        "agreement": doc.agreement_id,
        "uploaded_at": doc.uploaded_at,
        "uploaded_by": (doc.uploaded_by.get_full_name() or doc.uploaded_by.email)
        if doc.uploaded_by_id
        else "",
        "url": f"/api/orgs/{org_id}/billing/partners/{doc.partner_id}/documents/{doc.pk}/",
    }


class _PartnerScope(PartnerAccess, APIView):
    def partner(self) -> BusinessPartner:
        return get_object_or_404(
            BusinessPartner, organization=self.org, pk=self.kwargs["partner_pk"]
        )


class PartnerDocumentListView(_PartnerScope):
    """GET: Dokumente der Akte · POST: Datei hochladen (``file``, ``title?``, ``agreement?``)."""

    # Eingehende Dateien: bei ausgefallenem Scanner in Quarantäne statt abgelehnt
    virus_quarantine = True
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, org_id: int, partner_pk: int):
        partner = self.partner()
        rows = PartnerDocument.objects.filter(organization=self.org, partner=partner)
        return Response([document_data(self.org.pk, d) for d in rows.select_related("uploaded_by")])

    @transaction.atomic
    def post(self, request, org_id: int, partner_pk: int):
        partner = self.partner()
        upload = request.FILES.get("file")
        if upload is None:
            raise serializers.ValidationError({"file": gettext("Bitte eine Datei wählen.")})
        title = serializers.CharField(max_length=200, required=False, allow_blank=True)
        title = title.run_validation(request.data.get("title", ""))
        agreement = None
        if raw := request.data.get("agreement"):
            agreement = get_object_or_404(
                PartnerAgreement, organization=self.org, partner=partner, pk=raw
            )
        try:
            content_type = check_upload(upload)
            check_budget(self.org, upload.size)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        doc = PartnerDocument(
            organization=self.org,
            partner=partner,
            agreement=agreement,
            title=title,
            name=clean_name(upload.name),
            content_type=content_type,
            size=upload.size,
            uploaded_by=request.user,
        )
        doc.file.save(storage_name(upload.name), upload, save=False)
        try:
            doc.save()
            record(self.org, request.user, "create", doc, diff({}, snapshot(doc)))
        except Exception:
            doc.file.storage.delete(doc.file.name)
            raise
        return Response(document_data(self.org.pk, doc), status=status.HTTP_201_CREATED)


class PartnerDocumentDetailView(_PartnerScope):
    """GET: Datei herunterladen · DELETE: Dokument entfernen."""

    def doc(self) -> PartnerDocument:
        return get_object_or_404(
            PartnerDocument, organization=self.org, partner=self.partner(), pk=self.kwargs["pk"]
        )

    def get(self, request, org_id: int, partner_pk: int, pk: int):
        from core.virenscan import ensure_released

        doc = self.doc()
        ensure_released(doc.file)
        record(self.org, request.user, "view", doc, {"Datei": [None, doc.name]})
        response = FileResponse(
            doc.file.open("rb"),
            filename=doc.name,
            content_type=doc.content_type,
            as_attachment=True,
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @transaction.atomic
    def delete(self, request, org_id: int, partner_pk: int, pk: int):
        doc = self.doc()
        record(self.org, request.user, "delete", doc, diff(snapshot(doc), {}))
        name = doc.file.name
        storage = doc.file.storage
        doc.delete()
        transaction.on_commit(lambda: storage.delete(name))
        return Response(status=status.HTTP_204_NO_CONTENT)


def group(org, role: str = "", kind: str = "", include_inactive: bool = False):
    """Partner einer Gruppe (Rolle und/oder Art), für Serienbrief und E-Mail-Verteiler."""
    rows = BusinessPartner.objects.filter(organization=org)
    if not include_inactive:
        rows = rows.filter(is_active=True)
    if kind:
        rows = rows.filter(kind=kind)
    partners = list(rows.prefetch_related("contacts").order_by("name"))
    if role:
        partners = [p for p in partners if role in (p.roles or [])]
    return partners


def mail_addresses(partner: BusinessPartner) -> list[str]:
    """Ansprechpartner mit „erhält Post“ und E-Mail, sonst die E-Mail des Partners."""
    contacts = [c.email for c in partner.contacts.all() if c.receives_mail and c.email]
    if contacts:
        return contacts
    email = (partner.details or {}).get("email", "")
    return [email] if email else []


class GroupSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=BusinessPartner.Role.choices, required=False, allow_blank=True
    )
    kind = serializers.ChoiceField(
        choices=BusinessPartner.Kind.choices, required=False, allow_blank=True
    )


class LetterSerializer(GroupSerializer):
    subject = serializers.CharField(max_length=200)
    text = serializers.CharField(max_length=LETTER_MAX)


def mailing_get(view, request):
    """``?role=&kind=``: Empfänger der Gruppe mit E-Mail-Adressen."""
    params = GroupSerializer(data=request.query_params)
    params.is_valid(raise_exception=True)
    rows = group(view.org, **params.validated_data)
    return Response(
        [
            {
                "id": p.pk,
                "name": p.name,
                "emails": mail_addresses(p),
                "has_address": has_address(p),
            }
            for p in rows
        ]
    )


def has_address(partner: BusinessPartner) -> bool:
    details = partner.details or {}
    return bool(details.get("street") and details.get("city"))


def mailing_post(view, request):
    """``{role?, kind?, subject, text}``: Serienbrief als PDF, ein Brief je Partner mit
    Anschrift, auf dem Briefbogen des Vereins."""
    params = LetterSerializer(data=request.data)
    params.is_valid(raise_exception=True)
    data = params.validated_data
    rows = [
        p for p in group(view.org, data.get("role", ""), data.get("kind", "")) if has_address(p)
    ]
    if not rows:
        raise serializers.ValidationError(
            gettext("In dieser Gruppe hat kein Geschäftspartner eine Anschrift.")
        )
    if len(rows) > LETTERS_MAX:
        raise serializers.ValidationError(
            gettext("Höchstens {n} Briefe auf einmal.").format(n=LETTERS_MAX)
        )
    content = letters_pdf(view.org, rows, data["subject"], data["text"])
    record(
        view.org,
        request.user,
        "view",
        view.org,
        {"Serienbrief an Geschäftspartner": [None, f"{data['subject']} ({len(rows)})"]},
    )
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="Serienbrief.pdf"'
    return response


def letters_pdf(org, partners: list[BusinessPartner], subject: str, text: str) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer

    from letterhead.data import letter_data
    from letterhead.pdf import LetterDocument, text_styles

    data = letter_data(org)
    st = text_styles(data)
    story: list = []
    info = [(gettext("Datum"), f"{timezone.localdate():%d.%m.%Y}")]
    for n, partner in enumerate(partners):
        story.extend(LetterDocument.start(data, recipient_lines(partner), info, n == 0))
        story.append(Paragraph(escape(subject), st["title"]))
        story.append(Paragraph(escape(greeting(partner)), st["body"]))
        for part in text.split("\n\n"):
            if part.strip():
                story.append(Paragraph(escape(part.strip()).replace("\n", "<br/>"), st["body"]))
        story.append(Spacer(1, 4 * mm))
        story.append(
            Paragraph(
                f"{escape(gettext('Mit freundlichen Grüßen'))}<br/>{escape(data.name)}", st["body"]
            )
        )
    buf = io.BytesIO()
    LetterDocument(buf, [data] * len(partners), title=subject, author=org.name).build(story)
    return buf.getvalue()
