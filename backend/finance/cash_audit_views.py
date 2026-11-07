"""API Kassenprüfung: /api/orgs/<org_id>/finance/audits/ (Konzept vereinskasse-steuern, S6).

Lesen mit finance.view. Prüfauftrag anlegen, ändern und löschen mit finance.edit (Kasse).
Stichproben, Kontenabgleich, Prüfpunkte, Feststellungen, Empfehlung und Abschluss nur
für Kassenprüfer: Kasse lesen, aber nicht führen. ``GET …/<id>/pdf/`` liefert den
Prüfbericht."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from access.catalog import FINANCE_EDIT, FINANCE_VIEW
from audit.log import record

from . import cash_audit
from .bank_views import _drf
from .models import CashAudit
from .views import FinanceMixin

STATUS_OPEN = CashAudit.Status.OPEN


def _money(value) -> str | None:
    return None if value is None else f"{value:.2f}"


class CashAuditSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    recommendation_label = serializers.CharField(
        source="get_recommendation_display", read_only=True
    )
    open_points = serializers.SerializerMethodField()

    class Meta:
        model = CashAudit
        fields = [
            "id",
            "year",
            "label",
            "status",
            "status_label",
            "auditors",
            "due_on",
            "recommendation",
            "recommendation_label",
            "open_points",
            "closed_at",
        ]

    def get_label(self, obj) -> str:
        return obj.organization.fiscal_label(obj.year)

    def get_open_points(self, obj) -> int:
        return cash_audit.open_points(obj)


class CashAuditDetailSerializer(CashAuditSerializer):
    meeting_title = serializers.SerializerMethodField()
    checks = serializers.SerializerMethodField()
    samples = serializers.SerializerMethodField()
    accounts = serializers.SerializerMethodField()
    facts = serializers.SerializerMethodField()
    access = serializers.SerializerMethodField()
    can_audit = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()

    class Meta(CashAuditSerializer.Meta):
        fields = [
            *CashAuditSerializer.Meta.fields,
            "sample_size",
            "findings",
            "meeting",
            "meeting_title",
            "checks",
            "samples",
            "accounts",
            "facts",
            "access",
            "can_audit",
            "can_manage",
        ]

    def get_meeting_title(self, obj) -> str | None:
        if not obj.meeting_id:
            return None
        start = timezone.localdate(obj.meeting.event.starts_at)
        return f"{obj.meeting.event.title} ({start:%d.%m.%Y})"

    def get_checks(self, obj) -> list:
        return cash_audit.check_rows(obj)

    def get_samples(self, obj) -> list:
        rows = []
        qs = obj.samples.select_related(
            "booking__organization", "booking__category", "booking__account"
        ).prefetch_related("booking__receipts")
        for s in qs:
            b = s.booking
            rows.append(
                {
                    "id": s.id,
                    "booking": b.pk,
                    "number": b.display_number,
                    "date": b.date,
                    "kind": b.kind,
                    "kind_label": str(b.get_kind_display()),
                    "amount": _money(b.amount),
                    "text": b.text,
                    "counterparty": b.counterparty,
                    "category": b.frozen_category_name or (b.category.name if b.category else ""),
                    "account": b.account.name if b.account_id else "",
                    "receipts": [
                        {"id": r.pk, "name": r.name}
                        for r in b.receipts.all()
                        if r.hidden_at is None
                    ],
                    "result": s.result,
                    "note": s.note,
                    "checked_by": s.checked_by_name,
                    "checked_at": s.checked_at,
                }
            )
        return rows

    def get_accounts(self, obj) -> list:
        balances = cash_audit.book_balances(obj)
        rows = []
        for row in obj.accounts.select_related("account"):
            book = balances.get(row.account_id, Decimal("0"))
            diff = None
            if row.statement_balance is not None:
                diff = row.statement_balance - book
            rows.append(
                {
                    "id": row.id,
                    "account": row.account_id,
                    "name": row.account.name,
                    "kind": row.account.kind,
                    "book_balance": _money(book),
                    "statement_balance": _money(row.statement_balance),
                    "difference": _money(diff),
                    "note": row.note,
                    "checked_by": row.checked_by_name,
                    "checked_at": row.checked_at,
                }
            )
        return rows

    def get_facts(self, obj) -> dict:
        return cash_audit.facts(obj.organization, obj.year)

    def get_access(self, obj) -> list:
        return cash_audit.auditors_with_access(obj.organization)

    def get_can_audit(self, obj) -> bool:
        return cash_audit.is_auditor(self.context.get("perms", set()))

    def get_can_manage(self, obj) -> bool:
        return FINANCE_EDIT in self.context.get("perms", set())


class CashAuditViewSet(
    FinanceMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CashAuditSerializer
    pagination_class = None
    # Kassenprüfer schreiben mit Leserecht; was nur die Kasse darf, prüft jede Aktion
    write_permission = (FINANCE_VIEW, FINANCE_EDIT)

    def get_queryset(self):
        return CashAudit.objects.filter(organization=self.org).select_related(
            "organization", "meeting__event"
        )

    def get_serializer_class(self):
        if self.action == "list":
            return CashAuditSerializer
        return CashAuditDetailSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["perms"] = getattr(self, "org_permissions", set())
        return ctx

    # --- Rechte -------------------------------------------------------------------------

    def _manager(self) -> None:
        if FINANCE_EDIT not in self.org_permissions:
            raise PermissionDenied(gettext("Den Prüfauftrag legt die Kasse an."))

    def _auditor(self) -> None:
        if not cash_audit.is_auditor(self.org_permissions):
            raise PermissionDenied(
                gettext("Prüfen dürfen nur Kassenprüfer: Kasse lesen, aber nicht führen.")
            )

    def _open(self, audit: CashAudit) -> None:
        if audit.status != STATUS_OPEN:
            raise serializers.ValidationError(
                gettext("Die Kassenprüfung ist abgeschlossen. Erst wieder öffnen.")
            )

    def _detail(self, audit: CashAudit, code=status.HTTP_200_OK) -> Response:
        audit.refresh_from_db()
        return Response(
            CashAuditDetailSerializer(audit, context=self.get_serializer_context()).data,
            status=code,
        )

    def retrieve(self, request, *args, **kwargs):
        audit = self.get_object()
        cash_audit.sync_accounts(audit)
        return self._detail(audit)

    # --- Prüfauftrag (Kasse) -------------------------------------------------------------

    def _settings(self, data, audit: CashAudit | None) -> dict:
        fields: dict = {}
        if "auditors" in data:
            fields["auditors"] = " ".join(str(data["auditors"] or "").split())[:300]
        if "due_on" in data:
            raw = data["due_on"] or None
            fields["due_on"] = (
                serializers.DateField(allow_null=True).to_internal_value(raw) if raw else None
            )
        if "sample_size" in data:
            try:
                fields["sample_size"] = int(data["sample_size"])
            except (TypeError, ValueError):
                raise serializers.ValidationError(
                    {"sample_size": gettext("Bitte 1 bis 200 Stichproben angeben.")}
                ) from None
            if not 1 <= fields["sample_size"] <= 200:
                raise serializers.ValidationError(
                    {"sample_size": gettext("Bitte 1 bis 200 Stichproben angeben.")}
                )
        if "meeting" in data:
            fields["meeting"] = None
            if data["meeting"]:
                ids = {m["id"] for m in cash_audit.meetings(self.org)}
                try:
                    meeting_id = int(data["meeting"])
                except (TypeError, ValueError):
                    meeting_id = 0
                if meeting_id not in ids:
                    raise serializers.ValidationError(
                        {"meeting": gettext("Unbekannte Versammlung.")}
                    )
                from meetings.models import Meeting

                fields["meeting"] = Meeting.objects.get(pk=meeting_id)
        return fields

    @extend_schema(request=dict, responses=CashAuditDetailSerializer)
    @transaction.atomic
    def create(self, request, org_id: int):
        self._manager()
        raw = str(request.data.get("year", ""))
        if not raw.isdigit() or not 1990 <= int(raw) <= 2100:
            raise serializers.ValidationError({"year": gettext("Bitte ein Geschäftsjahr wählen.")})
        year = int(raw)
        if CashAudit.objects.filter(organization=self.org, year=year).exists():
            raise serializers.ValidationError(
                {"year": gettext("Für dieses Geschäftsjahr gibt es schon eine Kassenprüfung.")}
            )
        fields = self._settings(request.data, None)
        try:
            with transaction.atomic():
                audit = cash_audit.create(self.org, year, request.user, **fields)
        except IntegrityError:
            raise serializers.ValidationError(
                {"year": gettext("Für dieses Geschäftsjahr gibt es schon eine Kassenprüfung.")}
            ) from None
        record(
            self.org,
            request.user,
            "create",
            audit,
            {"Kassenprüfung": [None, f"{self.org.fiscal_label(year)}, {audit.auditors}"]},
        )
        return self._detail(audit, status.HTTP_201_CREATED)

    @extend_schema(request=dict, responses=CashAuditDetailSerializer)
    @transaction.atomic
    def partial_update(self, request, org_id: int, pk=None):
        audit = self.get_object()
        self._open(audit)
        data = request.data
        manager_keys = {"auditors", "due_on", "sample_size", "meeting"} & set(data)
        auditor_keys = {"checks", "findings", "recommendation"} & set(data)
        if manager_keys:
            self._manager()
        if auditor_keys:
            self._auditor()
        fields = self._settings(data, audit)
        if "checks" in data:
            try:
                checks = cash_audit.clean_checks(data["checks"])
            except ValueError as exc:
                raise serializers.ValidationError({"checks": str(exc)}) from exc
            fields["checks"] = {**audit.checks, **checks}
        if "findings" in data:
            findings = str(data["findings"] or "").strip()
            if len(findings) > 5000:
                raise serializers.ValidationError(
                    {"findings": gettext("Bitte höchstens 5000 Zeichen.")}
                )
            fields["findings"] = findings
        if "recommendation" in data:
            value = data["recommendation"] or ""
            if value not in CashAudit.Recommendation.values:
                raise serializers.ValidationError(
                    {"recommendation": gettext("Unbekannte Empfehlung.")}
                )
            fields["recommendation"] = value
        changes = {}
        for key, value in fields.items():
            before = getattr(audit, key)
            if before != value:
                if key not in ("checks", "findings"):
                    changes[key] = [str(before or ""), str(value or "")]
                setattr(audit, key, value)
        if "checks" in fields or "findings" in fields:
            changes.setdefault("Prüfpunkte/Feststellungen", [None, "geändert"])
        if changes:
            try:
                audit.full_clean(exclude=["organization", "meeting", "created_by", "closed_by"])
            except DjangoValidationError as exc:
                raise _drf(exc) from exc
            audit.save()
            record(self.org, request.user, "update", audit, changes)
        return self._detail(audit)

    @transaction.atomic
    def destroy(self, request, org_id: int, pk=None):
        audit = self.get_object()
        self._manager()
        self._open(audit)
        if (
            audit.samples.exclude(result="").exists()
            or audit.accounts.filter(statement_balance__isnull=False).exists()
        ):
            raise serializers.ValidationError(
                gettext("Die Prüfer haben schon geprüft. Die Kassenprüfung bleibt erhalten.")
            )
        record(
            self.org,
            request.user,
            "delete",
            audit,
            {"Kassenprüfung": [self.org.fiscal_label(audit.year), None]},
        )
        audit.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # --- Prüfen (Kassenprüfer) -----------------------------------------------------------

    @extend_schema(request=dict, responses=CashAuditDetailSerializer)
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def draw(self, request, org_id: int, pk=None):
        """Weitere Stichproben ziehen ({count}, Standard 5)."""
        audit = self.get_object()
        self._open(audit)
        if not (
            cash_audit.is_auditor(self.org_permissions) or FINANCE_EDIT in self.org_permissions
        ):
            self._auditor()
        try:
            count = int(request.data.get("count", 5))
        except (TypeError, ValueError):
            count = 0
        if not 1 <= count <= 50:
            raise serializers.ValidationError({"count": gettext("Bitte 1 bis 50 angeben.")})
        drawn = cash_audit.draw(audit, count)
        if not drawn:
            raise serializers.ValidationError(
                {"count": gettext("Es gibt keine weiteren Buchungen für die Stichprobe.")}
            )
        record(self.org, request.user, "update", audit, {"Stichproben": [None, f"+{drawn}"]})
        return self._detail(audit)

    @extend_schema(request=dict, responses=CashAuditDetailSerializer)
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def check(self, request, org_id: int, pk=None):
        """Stichprobe {sample, result, note} oder Konto {account, statement_balance, note}."""
        audit = self.get_object()
        self._auditor()
        self._open(audit)
        data = request.data
        note = str(data.get("note", "") or "").strip()
        if len(note) > 300:
            raise serializers.ValidationError({"note": gettext("Bitte höchstens 300 Zeichen.")})
        if data.get("sample"):
            row = (
                audit.samples.select_related("booking__organization")
                .filter(pk=data.get("sample"))
                .first()
            )
            if row is None:
                raise serializers.ValidationError({"sample": gettext("Unbekannte Stichprobe.")})
            result = data.get("result", "")
            if result not in ("", "ok", "issue"):
                raise serializers.ValidationError({"result": gettext("Unbekanntes Ergebnis.")})
            if result == "issue" and not note:
                raise serializers.ValidationError(
                    {"note": gettext("Bitte die Rückfrage kurz beschreiben.")}
                )
            row.result, row.note = result, note
            cash_audit.stamp(row, request.user)
            row.save()
            label = f"Stichprobe {row.booking.display_number}"
            record(self.org, request.user, "update", audit, {label: [None, result or "offen"]})
        elif data.get("account"):
            row = audit.accounts.select_related("account").filter(pk=data.get("account")).first()
            if row is None:
                raise serializers.ValidationError({"account": gettext("Unbekanntes Konto.")})
            raw = data.get("statement_balance")
            value = None
            if raw not in (None, ""):
                try:
                    value = Decimal(str(raw).replace(",", ".")).quantize(Decimal("0.01"))
                except InvalidOperation:
                    raise serializers.ValidationError(
                        {"statement_balance": gettext("Bitte einen Betrag angeben.")}
                    ) from None
                if abs(value) >= Decimal("10000000000"):
                    raise serializers.ValidationError(
                        {"statement_balance": gettext("Bitte einen Betrag angeben.")}
                    )
            row.statement_balance, row.note = value, note
            cash_audit.stamp(row, request.user)
            row.save()
            label = f"Kontenabgleich {row.account.name}"
            record(
                self.org, request.user, "update", audit, {label: [None, _money(value) or "offen"]}
            )
        else:
            raise serializers.ValidationError(gettext("Bitte Stichprobe oder Konto angeben."))
        return self._detail(audit)

    @extend_schema(request=dict, responses=CashAuditDetailSerializer)
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def close(self, request, org_id: int, pk=None):
        """Prüfung abschließen: Empfehlung gewählt und nichts mehr offen."""
        audit = self.get_object()
        self._auditor()
        self._open(audit)
        if not audit.recommendation:
            raise serializers.ValidationError(
                {"recommendation": gettext("Bitte eine Empfehlung zur Entlastung wählen.")}
            )
        missing = cash_audit.open_points(audit)
        if missing:
            raise serializers.ValidationError(
                gettext("Noch {n} Punkte offen (Stichproben, Konten oder Prüfpunkte).").format(
                    n=missing
                )
            )
        audit.status = CashAudit.Status.DONE
        audit.closed_at = timezone.now()
        audit.closed_by = request.user
        audit.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
        record(
            self.org,
            request.user,
            "update",
            audit,
            {"Kassenprüfung": ["in Prüfung", str(audit.get_recommendation_display())]},
        )
        return self._detail(audit)

    @extend_schema(request=dict, responses=CashAuditDetailSerializer)
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def reopen(self, request, org_id: int, pk=None):
        """Abgeschlossene Prüfung wieder öffnen (Prüfer oder Kasse), mit Grund."""
        audit = self.get_object()
        if not (
            cash_audit.is_auditor(self.org_permissions) or FINANCE_EDIT in self.org_permissions
        ):
            self._auditor()
        if audit.status == STATUS_OPEN:
            return self._detail(audit)
        reason = " ".join(str(request.data.get("reason", "") or "").split())
        if not reason:
            raise serializers.ValidationError({"reason": gettext("Bitte einen Grund angeben.")})
        audit.status = STATUS_OPEN
        audit.closed_at = None
        audit.closed_by = None
        audit.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
        record(
            self.org,
            request.user,
            "update",
            audit,
            {"Kassenprüfung": ["abgeschlossen", f"wieder geöffnet: {reason[:200]}"]},
        )
        return self._detail(audit)

    @extend_schema(responses={(200, "*/*"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def pdf(self, request, org_id: int, pk=None):
        from .cash_audit_report import render

        audit = self.get_object()
        content = render(audit)
        response = HttpResponse(content, content_type="application/pdf")
        name = f"Pruefbericht-Kasse-{audit.organization.fiscal_label(audit.year)}.pdf"
        disposition = "attachment" if request.query_params.get("download") == "1" else "inline"
        response["Content-Disposition"] = f'{disposition}; filename="{name}"'
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(responses=dict)
    @action(detail=False, methods=["get"])
    def meetings(self, request, org_id: int):
        """Versammlungen zur Auswahl (nur mit Modul Versammlungen)."""
        return Response(cash_audit.meetings(self.org))
