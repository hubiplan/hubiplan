"""Geschäftspartner, Leistungsrechnungen und dauerhafter Rechnungseingang."""

import hashlib
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from audit.log import record
from changes import idempotency
from finance import einvoice
from finance.models import Booking, Category, Project, Receipt
from finance.services import lock_bank_sources
from finance.views import FinanceMixin

from . import (
    einvoice_services,
    einvoice_validator,
    einvoice_xml,
    incoming_check,
    incoming_import,
    incoming_mail,
)
from .einvoice_schema import CommercialInvoiceSerializer
from .models import (
    BusinessPartner,
    IncomingInvoice,
    IncomingMail,
    IncomingValidation,
    Invoice,
)

# Geschäftspartner: billing/partners.py (Konzept P1)
from .partners import PartnerSerializer, PartnerViewSet  # noqa: F401
from .serializers import InvoiceDetailSerializer
from .views import InvoicePagination, InvoiceViewSet, _as_drf


def file_response(data, content_type, filename):
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class ElectronicInvoiceViewSet(InvoiceViewSet):
    """Gleiche Rechnungen, Nummern, Zahlungen und Rechte; eigener strukturierter Editor."""

    def get_queryset(self):
        qs = super().get_queryset().exclude(electronic_data={})
        if self.action == "advances":
            qs = qs.filter(document_kind="advance", status__in=["open", "paid"], paid__gt=0)
            for field in ["partner", "project"]:
                value = self.request.query_params.get(field)
                if value and value.isdigit():
                    qs = qs.filter(**{field + "_id": int(value)})
            if not self.request.query_params.get("project"):
                qs = qs.filter(project__isnull=True)
        return qs

    @action(detail=False, methods=["get"])
    def advances(self, request, org_id):
        return Response(InvoiceDetailSerializer(self.get_queryset()[:100], many=True).data)

    @action(detail=True, methods=["get", "post"])
    def hybrid(self, request, org_id, pk):
        from . import hybrid

        document = "cancellation" if request.query_params.get("cancellation") == "1" else "invoice"
        try:
            if request.method == "POST":
                with transaction.atomic():
                    invoice = self._locked_object()
                    if document == "cancellation" and invoice.status != "cancelled":
                        raise NotFound()
                    hybrid.create(invoice, document)
                return self._detail(invoice)
            invoice = self.get_object()
            if not invoice.hybrid_artifacts.filter(document=document).exclude(pdf="").exists():
                raise NotFound()
            pdf = hybrid.read(invoice, document)
        except DjangoValidationError as exc:
            raise _as_drf(exc) from exc
        suffix = "-S" if document == "cancellation" else ""
        return file_response(
            pdf, "application/pdf", f"{invoice.display_number}{suffix}-zugferd.pdf"
        )

    @action(detail=True, methods=["get", "post"])
    def delivery(self, request, org_id, pk):
        from . import delivery

        invoice = self.get_object()
        try:
            if request.method == "GET":
                return Response(delivery.overview(invoice))
            document = serializers.ChoiceField(choices=["invoice", "cancellation"]).run_validation(
                request.data.get("document", "invoice")
            )
            operation = serializers.ChoiceField(choices=["send", "refresh"]).run_validation(
                request.data.get("operation", "send")
            )
            result = delivery.dispatch(invoice, document, operation)
            record(
                self.org,
                request.user,
                "update",
                invoice,
                {"E-Rechnungsversand": [None, result["status"]]},
            )
            return Response(result)
        except DjangoValidationError as exc:
            raise _as_drf(exc) from exc

    def _save_commercial(self, invoice, request):
        serializer = CommercialInvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        category = get_object_or_404(
            Category, organization=self.org, pk=data["payment_category"], is_active=True
        )
        if not category.allows("income"):
            raise serializers.ValidationError(gettext("Die Kategorie gilt nicht für Einnahmen."))
        invoice.payment_category = category
        partner = get_object_or_404(
            BusinessPartner,
            organization=self.org,
            pk=data["partner"],
            is_active=True,
            is_customer=True,
        )
        project = (
            get_object_or_404(Project, organization=self.org, pk=data["project"])
            if data["project"]
            else None
        )
        try:
            einvoice_services.save_draft(invoice, data, partner, project)
            if hasattr(invoice, "performanceaccount"):
                if invoice.document_kind == "advance":
                    raise serializers.ValidationError(
                        gettext(
                            "Für die Auftrittsabrechnung bitte Rechnung oder "
                            "Schlussrechnung wählen."
                        )
                    )
                account = invoice.performanceaccount
                if (
                    invoice.partner_id != account.performance.customer_id
                    or invoice.total != account.fee + account.travel + account.extras
                ):
                    raise serializers.ValidationError(
                        gettext("Kunde und Bruttobetrag müssen zur Auftrittsvereinbarung passen.")
                    )
        except DjangoValidationError as exc:
            raise _as_drf(exc) from exc

    @transaction.atomic
    def create(self, request, org_id):
        claim = idempotency.claim(request, f"billing.electronic.new.{self.org.pk}", required=True)
        if claim.done:
            return self._detail(get_object_or_404(self.get_queryset(), pk=claim.result["invoice"]))
        invoice = Invoice(organization=self.org, created_by=request.user)
        self._save_commercial(invoice, request)
        claim.remember({"invoice": invoice.pk})
        record(self.org, request.user, "create", invoice, {"E-Rechnung": [None, "Entwurf"]})
        return Response(InvoiceDetailSerializer(invoice).data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def partial_update(self, request, org_id, pk):
        invoice = self._locked_object()
        if invoice.status != Invoice.Status.DRAFT:
            raise serializers.ValidationError(
                gettext("Festgeschriebene E-Rechnungen sind unveränderbar.")
            )
        self._save_commercial(invoice, request)
        record(
            self.org,
            request.user,
            "update",
            invoice,
            {"E-Rechnung": ["Entwurf", "Entwurf bearbeitet"]},
        )
        return self._detail(invoice)

    @action(detail=True, methods=["post"])
    def validate(self, request, org_id, pk):
        invoice = self.get_object()
        if invoice.status != Invoice.Status.DRAFT:
            return Response(invoice.electronic_artifact.report)
        from .advances import ensure_current

        try:
            ensure_current(invoice)
        except DjangoValidationError as exc:
            raise _as_drf(exc) from exc
        report, _ = einvoice_validator.validate(einvoice_xml.generate(invoice))
        return Response(report)

    @action(detail=True, methods=["get"])
    def xml(self, request, org_id, pk):
        invoice = self.get_object()
        try:
            part = "cancellation_xml" if request.query_params.get("cancellation") == "1" else "xml"
            if part == "cancellation_xml" and invoice.status != "cancelled":
                raise NotFound()
            data = einvoice_services.read_artifact(invoice, part)
        except DjangoValidationError as exc:
            raise _as_drf(exc) from exc
        suffix = "-S" if part == "cancellation_xml" else ""
        return file_response(data, "application/xml", f"{invoice.display_number}{suffix}.xml")

    @action(detail=True, methods=["get"])
    def report(self, request, org_id, pk):
        try:
            data = einvoice_services.read_artifact(self.get_object(), "report_xml")
        except DjangoValidationError as exc:
            raise _as_drf(exc) from exc
        return file_response(data, "application/xml", "validation.xml")


class IncomingMailSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncomingMail
        fields = [
            "id",
            "sender",
            "subject",
            "sender_known",
            "status",
            "skipped",
            "received_at",
            "dismissed_at",
        ]
        read_only_fields = fields


class IncomingSerializer(serializers.ModelSerializer):
    has_report = serializers.SerializerMethodField()
    mail = IncomingMailSerializer(read_only=True, allow_null=True)

    def get_has_report(self, obj) -> bool:
        return bool(obj.report_xml)

    class Meta:
        model = IncomingInvoice
        fields = [
            "id",
            "name",
            "sha256",
            "content_type",
            "data",
            "report",
            "status",
            "validation",
            "review_note",
            "reviewed_at",
            "booking",
            "created_at",
            "has_report",
            "mail",
        ]
        read_only_fields = fields


class IncomingInvoiceViewSet(FinanceMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = IncomingSerializer
    pagination_class = InvoicePagination

    def get_queryset(self):
        return IncomingInvoice.objects.filter(organization=self.org).select_related("mail")

    @action(detail=False, methods=["get", "post"])
    def mailbox(self, request, org_id):
        """Plus-Adresse des Vereins im Rechnungspostfach; POST vergibt eine neue (#374)."""
        if not incoming_mail.configured():
            return Response({"enabled": False, "address": ""})
        if request.method == "POST":
            incoming_mail.mailbox_of(self.org, renew=True)
            record(
                self.org,
                request.user,
                "update",
                incoming_mail.mailbox_of(self.org),
                {"Rechnungspostfach": [None, gettext("Neue Adresse vergeben")]},
            )
        return Response({"enabled": True, "address": incoming_mail.address_for(self.org)})

    @action(detail=False, methods=["get"])
    def mails(self, request, org_id):
        """Offene Hinweise des Rechnungspostfachs: Mails ohne übernommene E-Rechnung."""
        rows = IncomingMail.objects.filter(organization=self.org, dismissed_at__isnull=True)
        return Response(IncomingMailSerializer(rows[:100], many=True).data)

    @action(detail=False, methods=["post"], url_path=r"mails/(?P<mail_id>[0-9]+)/dismiss")
    def dismiss_mail(self, request, org_id, mail_id):
        mail = get_object_or_404(IncomingMail, organization=self.org, pk=mail_id)
        if mail.dismissed_at is None:
            mail.dismissed_at = timezone.now()
            mail.save(update_fields=["dismissed_at"])
        return Response(IncomingMailSerializer(mail).data)

    @transaction.atomic
    def create(self, request, org_id):
        upload = request.FILES.get("file")
        if not upload or upload.size > incoming_import.MAX_BYTES:
            raise serializers.ValidationError(
                gettext("Bitte eine XML- oder PDF-Datei mit höchstens 15 MB wählen.")
            )
        item, created = incoming_import.store(self.org, upload.read(), upload.name, request.user)
        if not created:
            return Response(self.get_serializer(item).data)
        return Response(self.get_serializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def review(self, request, org_id, pk):
        lock_bank_sources(self.org)
        item = get_object_or_404(self.get_queryset().select_for_update(of=("self",)), pk=pk)
        decision = request.data.get("status")
        note = str(request.data.get("note", "")).strip()
        if decision not in ("approved", "rejected") or not note or len(note) > 2000:
            raise serializers.ValidationError(
                gettext("Bitte Freigabe oder Ablehnung mit einer Begründung angeben.")
            )
        if item.booking_id:
            raise serializers.ValidationError(
                gettext("Die Rechnung ist bereits einer Buchung zugeordnet.")
            )
        if decision == "approved" and item.report.get("status") != "valid":
            raise serializers.ValidationError(
                gettext("Nur erfolgreich geprüfte E-Rechnungen können freigegeben werden.")
            )
        previous = item.status
        item.status, item.review_note = decision, note
        item.reviewed_by, item.reviewed_at = request.user, timezone.now()
        item.save()
        record(
            self.org,
            request.user,
            "update",
            item,
            {"Prüfung": [previous, decision], "Begründung": [None, note]},
        )
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def revalidate(self, request, org_id, pk):
        lock_bank_sources(self.org)
        item = get_object_or_404(self.get_queryset().select_for_update(of=("self",)), pk=pk)
        if item.status != "review" or not item.xml:
            raise serializers.ValidationError(
                gettext("Nur ungeprüfte Eingänge mit XML können erneut geprüft werden.")
            )
        if item.validation == "pending":
            return Response(self.get_serializer(item).data)
        IncomingValidation.objects.create(
            organization=self.org,
            incoming=item,
            report=item.report,
            report_xml=item.report_xml.name,
        )
        # Die neue Prüfung läuft im Hintergrund (billing/incoming_check.py).
        item.report, item.report_xml = incoming_check.pending_report(), ""
        item.validation = "pending"
        item.save()
        record(self.org, request.user, "update", item, {"Prüfung": [None, "pending"]})
        incoming_check.schedule(self.org.pk)
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def link(self, request, org_id, pk):
        lock_bank_sources(self.org)
        link_input = serializers.IntegerField(min_value=1)
        booking_id = link_input.run_validation(request.data.get("booking"))
        item = get_object_or_404(self.get_queryset().select_for_update(of=("self",)), pk=pk)
        booking = get_object_or_404(
            Booking.objects.select_for_update(),
            organization=self.org,
            pk=booking_id,
        )
        if item.booking_id == booking.pk:
            return Response(self.get_serializer(item).data)
        if item.booking_id or item.status != "approved":
            raise serializers.ValidationError(
                gettext(
                    "Bitte die Rechnung zuerst freigeben; eine Zuordnung ist nur einmal möglich."
                )
            )
        from finance import services

        try:
            services.ensure_open(self.org, date=booking.date)
        except DjangoValidationError as exc:
            raise _as_drf(exc) from exc
        expected_kind = "income" if item.data.get("credit_note") else "expense"
        if (
            hasattr(booking, "performance_expense")
            or booking.kind != expected_kind
            or booking.cancels_id
            or hasattr(booking, "cancellation")
            or item.data.get("currency") != "EUR"
            or booking.amount != Decimal(item.data["payable"])
            or IncomingInvoice.objects.filter(booking=booking).exists()
        ):
            raise serializers.ValidationError(
                gettext(
                    "Buchungsart, Währung oder Betrag passen nicht, "
                    "oder die Buchung ist bereits zugeordnet."
                )
            )
        item.booking = booking
        item.save(update_fields=["booking"])
        # Eigene unveränderte Kopie: unterschiedliche Fristen dürfen nicht das
        # Original im Rechnungseingang über den Kassenbeleg entfernen.
        receipt = Receipt(
            organization=self.org,
            booking=booking,
            name=item.name,
            content_type=item.content_type,
            size=item.original.size,
            uploaded_by=request.user,
            einvoice=item.data,
        )
        with item.original.open("rb") as stream:
            receipt.file.save(
                "invoice.pdf" if item.content_type == "application/pdf" else "invoice.xml",
                ContentFile(stream.read()),
                save=False,
            )
        receipt.save()
        record(self.org, request.user, "update", item, {"Buchung": [None, booking.display_number]})
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["get"])
    def download(self, request, org_id, pk):
        item = self.get_object()
        if request.query_params.get("check"):
            previous = get_object_or_404(
                IncomingValidation,
                organization=self.org,
                incoming=item,
                pk=request.query_params["check"],
            )
            if not previous.report_xml:
                raise NotFound()
            with previous.report_xml.open("rb") as stream:
                return file_response(stream.read(), "application/xml", "validation.xml")
        which = request.query_params.get("part", "original")
        if which == "view":
            if not item.data:
                raise NotFound()
            return file_response(
                einvoice.render(item.data, self.org.display_name),
                "application/pdf",
                "invoice-view.pdf",
            )
        if which not in ("original", "xml", "report_xml"):
            raise NotFound()
        field = getattr(item, which)
        if not field:
            raise NotFound()
        with field.open("rb") as stream:
            raw = stream.read()
        if which == "original" and hashlib.sha256(raw).hexdigest() != item.sha256:
            raise PermissionDenied(gettext("Die Prüfsumme des Rechnungsoriginals stimmt nicht."))
        content_type = item.content_type if which == "original" else "application/xml"
        return file_response(
            raw, content_type, "invoice.pdf" if content_type == "application/pdf" else "invoice.xml"
        )
