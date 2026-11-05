"""Finanzabläufe: gemeinsame Sperre mit Kasse, Originalbezüge und Freigaben."""

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from billing.einvoice_views import ElectronicInvoiceViewSet
from billing.models import Invoice
from billing.serializers import InvoiceDetailSerializer
from changes import idempotency
from core.api_base import AuditMixin, OrgScopedMixin
from finance.models import Booking
from finance.services import ensure_open, lock_bank_sources

from .models import (
    Assignment,
    FeeTemplate,
    MusicianClaim,
    PayoutItem,
    Performance,
    PerformanceAccount,
    PerformanceExpense,
    PreviousPerformanceInvoice,
)
from .views import PerformanceViewSet


def money():
    return serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)


class AgreementInput(serializers.Serializer):
    fee = money()
    travel = money()
    extras = money()
    note = serializers.CharField(max_length=2000, allow_blank=True, default="")


class ClaimInput(serializers.Serializer):
    assignment = serializers.IntegerField(min_value=1)
    fee = money()
    allowance = money()
    expenses = money()
    attended = serializers.BooleanField()
    note = serializers.CharField(max_length=2000, allow_blank=True, default="")


def total(claim):
    return claim.fee + claim.allowance + claim.expenses


def active_payments(claim):
    return claim.payments.filter(booking__cancellation__isnull=True)


def paid_amount(claim):
    return active_payments(claim).aggregate(amount=Sum("booking__amount"))["amount"] or Decimal(0)


class FeeTemplateInput(serializers.ModelSerializer):
    fee = money()
    allowance = money()

    class Meta:
        model = FeeTemplate
        fields = ["id", "name", "fee", "allowance", "active"]


class FeeTemplateViewSet(OrgScopedMixin, AuditMixin, viewsets.ModelViewSet):
    read_permission = "finance.view"
    write_permission = "finance.edit"
    allowed_org_types = ("club", "federation")
    serializer_class = FeeTemplateInput
    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not {"music", "finance"} <= set(self.org.enabled_modules):
            raise NotFound()
        if "music.view" not in self.org_permissions:
            raise PermissionDenied()

    def get_queryset(self):
        return FeeTemplate.objects.filter(organization=self.org).order_by("name", "pk")

    def get_create_kwargs(self):
        return {"organization": self.org}


class BatchClaimRow(serializers.Serializer):
    assignment = serializers.IntegerField(min_value=1)
    attended = serializers.BooleanField()


class BatchClaims(serializers.Serializer):
    template = serializers.IntegerField(min_value=1)
    rows = BatchClaimRow(many=True, allow_empty=False, max_length=500)


def personal_claim(claim):
    paid = paid_amount(claim)
    return {
        "id": claim.pk,
        "fee": str(claim.fee),
        "allowance": str(claim.allowance),
        "expenses": str(claim.expenses),
        "total": str(total(claim)),
        "status": claim.status,
        "paid": total(claim) > 0 and paid >= total(claim),
        "paid_amount": str(paid),
        "outstanding": str(max(Decimal(0), total(claim) - paid)),
    }


def account_data(account):
    claims = MusicianClaim.objects.filter(assignment__performance=account.performance)
    rows = [
        {
            **personal_claim(row),
            "assignment": row.assignment_id,
            "attended": row.attended,
            "note": row.note,
        }
        for row in claims.order_by("pk")
    ]
    payments = account.payments.select_related("booking").order_by("pk")
    expenses = sum(
        (row.booking.amount for row in payments if not hasattr(row.booking, "cancellation")),
        Decimal(0),
    )
    remuneration = sum((total(row) for row in claims if row.status == "approved"), Decimal(0))
    invoice = account.invoice
    revenue = (
        sum(
            (
                row.amount
                for row in invoice.payments.all()
                if not hasattr(row.booking, "cancellation")
            ),
            Decimal(0),
        )
        if invoice
        else Decimal(0)
    )
    if invoice:
        revenue += sum(
            (row.amount for row in invoice.advance_allocations.filter(active=True)), Decimal(0)
        )
    return {
        "id": account.pk,
        "performance": account.performance_id,
        "fee": str(account.fee),
        "travel": str(account.travel),
        "extras": str(account.extras),
        "note": account.note,
        "agreed": str(account.fee + account.travel + account.extras),
        "invoice": invoice.pk if invoice else None,
        "invoice_status": invoice.status if invoice else None,
        "invoiced": str(
            invoice.total if invoice and invoice.status not in ("draft", "cancelled") else 0
        ),
        "revenue": str(revenue),
        "remuneration": str(remuneration),
        "expenses": str(expenses),
        "result": str(revenue - expenses),
        "claims": rows,
        "previous_invoices": list(account.previous_invoices.values_list("invoice_id", flat=True)),
        "payments": [
            {
                "id": row.pk,
                "claim": row.claim_id,
                "booking": row.booking_id,
                "number": row.booking.display_number,
                "amount": str(row.booking.amount),
                "cancelled": hasattr(row.booking, "cancellation"),
            }
            for row in payments
        ],
    }


class SettlementView(OrgScopedMixin, APIView):
    read_permission = "finance.view"
    write_permission = "finance.edit"
    allowed_org_types = ("club", "federation")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not {"music", "finance", "events"} <= set(self.org.enabled_modules):
            raise NotFound()
        if not {"music.view", "events.view"} <= self.org_permissions:
            raise PermissionDenied()

    def account(self, pk):
        queryset = (
            Performance.objects.select_for_update()
            if self.request.method == "POST"
            else Performance.objects.all()
        )
        performance = get_object_or_404(queryset, pk=pk, organization=self.org)
        if not PerformanceViewSet.visible(self, performance):
            raise NotFound()
        return performance

    def get(self, request, org_id, pk):
        performance = self.account(pk)
        account = PerformanceAccount.objects.filter(performance=performance).first()
        # Lesen legt keine Finanzdaten an.
        return Response(
            account_data(account)
            if account
            else {"performance": performance.pk, "claims": [], "payments": []}
        )

    @transaction.atomic
    def post(self, request, org_id, pk):
        lock_bank_sources(self.org)
        performance = self.account(pk)
        account, _ = PerformanceAccount.objects.get_or_create(
            organization=self.org,
            performance=performance,
            defaults={"date": timezone.localdate(performance.event.starts_at)},
        )
        action = request.data.get("action")
        if action != "payment":
            try:
                ensure_open(self.org, date=account.date)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages) from exc
        if action == "agreement":
            if account.invoice_id and account.invoice.status != "draft":
                raise serializers.ValidationError(
                    gettext("Die Vereinbarung ist bereits mit einer Rechnung verbunden.")
                )
            data = AgreementInput(data=request.data)
            data.is_valid(raise_exception=True)
            previous = {field: str(getattr(account, field)) for field in data.validated_data}
            for field, value in data.validated_data.items():
                setattr(account, field, value)
            account.save()
            record(
                self.org,
                request.user,
                "update",
                account,
                {
                    "Vereinbarung": [
                        previous,
                        {field: str(getattr(account, field)) for field in data.validated_data},
                    ]
                },
            )
        elif action == "replace_invoice":
            if (
                "billing" not in self.org.enabled_modules
                or "billing.edit" not in self.org_permissions
            ):
                raise PermissionDenied()
            if not account.invoice_id or account.invoice.status != "cancelled":
                raise serializers.ValidationError(
                    gettext("Bitte die Veranstalterrechnung zuerst stornieren.")
                )
            PreviousPerformanceInvoice.objects.create(
                organization=self.org, account=account, invoice=account.invoice
            )
            record(
                self.org,
                request.user,
                "update",
                account,
                {"Frühere Rechnung": [None, account.invoice_id]},
            )
            account.invoice = None
            account.save(update_fields=["invoice"])
        elif action == "batch_claims":
            key = idempotency.claim(request, f"music.claims.{self.org.pk}.{pk}", required=True)
            if key.done:
                return Response(account_data(account))
            data = BatchClaims(data=request.data)
            data.is_valid(raise_exception=True)
            template = get_object_or_404(
                FeeTemplate.objects.select_for_update(),
                organization=self.org,
                active=True,
                pk=data.validated_data["template"],
            )
            rows = data.validated_data["rows"]
            ids = [r["assignment"] for r in rows]
            available = set(
                Assignment.objects.filter(
                    organization=self.org, performance=performance, pk__in=ids
                ).values_list("pk", flat=True)
            )
            if (
                len(ids) != len(set(ids))
                or available != set(ids)
                or MusicianClaim.objects.filter(assignment_id__in=ids).exists()
            ):
                raise serializers.ValidationError(
                    gettext(
                        "Bitte nur Einteilungen dieses Auftritts "
                        "ohne vorhandene Vergütung auswählen."
                    )
                )
            for row in rows:
                claim = MusicianClaim.objects.create(
                    organization=self.org,
                    assignment_id=row["assignment"],
                    fee=template.fee,
                    allowance=template.allowance,
                    expenses=0,
                    attended=row["attended"],
                )
                record(
                    self.org,
                    request.user,
                    "create",
                    claim,
                    {"Vergütungsvorlage": [None, template.pk], "Teilnahme": [None, claim.attended]},
                )
            key.remember({"created": len(rows)})
        elif action == "claim":
            data = ClaimInput(data=request.data)
            data.is_valid(raise_exception=True)
            values = dict(data.validated_data)
            assignment = get_object_or_404(
                Assignment,
                pk=values.pop("assignment"),
                performance=performance,
                organization=self.org,
            )
            claim, _ = MusicianClaim.objects.get_or_create(
                organization=self.org, assignment=assignment
            )
            if claim.status != "draft":
                raise serializers.ValidationError(
                    gettext("Freigegebene Vergütungen sind unveränderbar.")
                )
            previous = {field: str(getattr(claim, field)) for field in values}
            for field, value in values.items():
                setattr(claim, field, value)
            claim.save()
            record(
                self.org,
                request.user,
                "update",
                claim,
                {
                    "Vergütung": [
                        previous,
                        {field: str(getattr(claim, field)) for field in values},
                    ],
                    "Teilnahme": [None, claim.attended],
                    "Vermerk": [None, claim.note],
                },
            )
        elif action in ("approve", "void", "reopen"):
            claim = get_object_or_404(
                MusicianClaim,
                pk=request.data.get("claim"),
                assignment__performance=performance,
                organization=self.org,
            )
            if PayoutItem.objects.filter(claim=claim, released=False).exists():
                raise serializers.ValidationError(
                    gettext("Bitte zuerst den Zahlungslauf aufheben.")
                )
            if active_payments(claim).exists():
                raise serializers.ValidationError(
                    gettext("Bitte zuerst die Auszahlung in der Kasse stornieren.")
                )
            previous_status = claim.status
            if action == "approve":
                if (
                    claim.status != "draft"
                    or not claim.attended
                    or total(claim) <= 0
                    or performance.event.is_cancelled
                    or performance.event.ends_at > timezone.now()
                ):
                    raise serializers.ValidationError(
                        gettext(
                            "Freigabe erst nach dem Auftritt mit bestätigter Teilnahme "
                            "und positivem Betrag."
                        )
                    )
                claim.status, claim.approved_by, claim.approved_at = (
                    "approved",
                    request.user,
                    timezone.now(),
                )
            elif action == "reopen":
                if claim.status != "void":
                    raise serializers.ValidationError(
                        gettext("Bitte die Vergütung zuerst aufheben.")
                    )
                claim.status = "draft"
                claim.approved_by, claim.approved_at = None, None
            else:
                claim.status = "void"
            claim.save()
            record(
                self.org,
                request.user,
                "update",
                claim,
                {"Freigabe": [previous_status, claim.status]},
            )
        elif action == "payment":
            booking_id = serializers.IntegerField(min_value=1).run_validation(
                request.data.get("booking")
            )
            booking = get_object_or_404(
                Booking.objects.select_for_update(), pk=booking_id, organization=self.org
            )
            claim_id = request.data.get("claim")
            claim = (
                get_object_or_404(
                    MusicianClaim,
                    pk=claim_id,
                    assignment__performance=performance,
                    organization=self.org,
                )
                if claim_id
                else None
            )
            existing = PerformanceExpense.objects.filter(booking=booking).first()
            if (
                existing
                and existing.account_id == account.pk
                and existing.claim_id == (claim.pk if claim else None)
            ):
                return Response(account_data(account))
            if (
                existing
                or booking.kind != "expense"
                or booking.cancels_id
                or hasattr(booking, "cancellation")
                or hasattr(booking, "incoming_invoice")
                or hasattr(booking, "payment")
            ):
                raise serializers.ValidationError(
                    gettext("Diese Ausgabe ist bereits zugeordnet oder nicht verwendbar.")
                )
            if claim and (
                claim.status != "approved"
                or booking.amount <= 0
                or booking.amount > total(claim) - paid_amount(claim)
            ):
                raise serializers.ValidationError(
                    gettext(
                        "Die Auszahlung muss positiv sein und darf den offenen "
                        "Vergütungsbetrag nicht übersteigen."
                    )
                )
            try:
                ensure_open(self.org, date=booking.date)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages) from exc
            payout_item = (
                PayoutItem.objects.filter(claim=claim, released=False).select_related("run").first()
                if claim
                else None
            )
            if payout_item and (
                payout_item.expense_id
                or booking.amount != payout_item.amount
                or booking.account_id != payout_item.run.bank_account_id
                or not payout_item.run.exported_at
            ):
                raise serializers.ValidationError(
                    gettext("Die Buchung muss zum exportierten Zahlungslauf passen.")
                )
            expense = PerformanceExpense.objects.create(
                organization=self.org, account=account, claim=claim, booking=booking
            )
            if payout_item:
                payout_item.expense = expense
                payout_item.save(update_fields=["expense"])
            record(
                self.org,
                request.user,
                "update",
                account,
                {"Ausgabe": [None, booking.display_number]},
            )
        else:
            raise serializers.ValidationError(gettext("Unbekannte Abrechnungsaktion."))
        return Response(account_data(account))


class PerformanceInvoiceView(SettlementView):
    @transaction.atomic
    def post(self, request, org_id, pk):
        if "billing" not in self.org.enabled_modules or "billing.edit" not in self.org_permissions:
            raise PermissionDenied()
        claim = idempotency.claim(request, f"music.invoice.{pk}", required=True)
        lock_bank_sources(self.org)
        performance = self.account(pk)
        account = get_object_or_404(
            PerformanceAccount, performance=performance, organization=self.org
        )
        if claim.done:
            invoice = get_object_or_404(Invoice, organization=self.org, pk=claim.result["invoice"])
            return Response(InvoiceDetailSerializer(invoice).data)
        if account.invoice_id:
            claim.remember({"invoice": account.invoice_id})
            return Response(InvoiceDetailSerializer(account.invoice).data)
        invoice = Invoice(organization=self.org, created_by=request.user)
        ElectronicInvoiceViewSet._save_commercial(self, invoice, request)
        if invoice.document_kind == "advance":
            raise serializers.ValidationError(
                gettext("Für die Auftrittsabrechnung bitte Rechnung oder Schlussrechnung wählen.")
            )
        if (
            invoice.partner_id != performance.customer_id
            or invoice.total != account.fee + account.travel + account.extras
        ):
            raise serializers.ValidationError(
                gettext("Kunde und Bruttobetrag müssen zur Auftrittsvereinbarung passen.")
            )
        account.invoice = invoice
        account.save(update_fields=["invoice"])
        claim.remember({"invoice": invoice.pk})
        record(self.org, request.user, "create", invoice, {"Auftritt": [None, performance.pk]})
        return Response(InvoiceDetailSerializer(invoice).data, status=201)
