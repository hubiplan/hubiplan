"""API Bankzugänge: /api/orgs/<org_id>/finance/bank-access/ und …/bank-tasks/.

Lesen mit finance.view, alles andere mit finance.edit. Einrichten, Ändern und Löschen eines
Zugangs verlangen zusätzlich einen frischen zweiten Faktor (accounts/step_up.py); der Abruf
nicht, weil die Bank ihn selbst mit PIN und TAN absichert. Ablauf in finance/bank_fetch.py.

Die PIN steht nur im Anfragekörper dieses einen Schritts. Sie wird weder gespeichert noch
protokolliert noch in einer Antwort zurückgegeben.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from accounts import step_up
from audit.log import record

from . import bank_fetch
from .bankweg import BankError
from .fints_weg import check_url
from .models import BankAccess, BankTask
from .views import FinanceMixin


class BankProblem(APIException):
    """Fehler eines Bankvorgangs: 409 mit ``code``, damit die Oberfläche passend reagiert."""

    status_code = status.HTTP_409_CONFLICT

    def __init__(self, exc: BankError):
        super().__init__({"detail": exc.message, "code": exc.code})


class BankAccessSerializer(serializers.ModelSerializer):
    accounts = serializers.SerializerMethodField()
    paused_until = serializers.SerializerMethodField()
    retry_needs_confirm = serializers.SerializerMethodField()
    login = serializers.CharField(max_length=100, write_only=True)
    customer_id = serializers.CharField(
        max_length=100, write_only=True, required=False, allow_blank=True
    )
    login_hint = serializers.SerializerMethodField()

    class Meta:
        model = BankAccess
        fields = [
            "id",
            "name",
            "way",
            "bank_code",
            "url",
            "login",
            "login_hint",
            "customer_id",
            "tan_mechanism",
            "tan_mechanism_name",
            "tan_medium",
            "ready",
            "ibans",
            "accounts",
            "last_success",
            "paused_until",
            "retry_needs_confirm",
        ]
        read_only_fields = [
            "id",
            "way",
            "tan_mechanism",
            "tan_mechanism_name",
            "tan_medium",
            "ready",
            "ibans",
            "last_success",
        ]

    def get_accounts(self, obj) -> list[dict]:
        return [
            {
                "id": a.pk,
                "name": a.name,
                "iban": a.iban,
                "fetched_until": a.bank_fetched_until.isoformat() if a.bank_fetched_until else None,
            }
            for a in bank_fetch.linked_accounts(obj)
        ]

    def get_paused_until(self, obj) -> str | None:
        if obj.locked_until and obj.locked_until > timezone.now():
            return obj.locked_until.isoformat()
        return None

    def get_retry_needs_confirm(self, obj) -> bool:
        return bool(obj.failures)

    def get_login_hint(self, obj) -> str:
        """Nur die letzten zwei Zeichen, damit man Zugänge unterscheiden kann."""
        return ("…" + obj.login[-2:]) if obj.login else ""

    def validate_bank_code(self, value: str) -> str:
        value = "".join(value.split())
        if not (value.isdigit() and len(value) == 8):
            raise serializers.ValidationError(gettext("Die Bankleitzahl hat acht Ziffern."))
        return value

    def validate_url(self, value: str) -> str:
        try:
            return check_url(value)
        except BankError as exc:
            raise serializers.ValidationError(exc.message) from exc


class StepSerializer(serializers.Serializer):
    pin = serializers.CharField(max_length=100, trim_whitespace=False)
    tan = serializers.CharField(max_length=100, required=False, allow_blank=True)
    mechanism = serializers.CharField(max_length=10, required=False, allow_blank=True)
    medium = serializers.CharField(max_length=100, required=False, allow_blank=True)
    confirm_retry = serializers.BooleanField(required=False, default=False)


class BankAccessViewSet(FinanceMixin, viewsets.ModelViewSet):
    serializer_class = BankAccessSerializer
    pagination_class = None

    def get_queryset(self):
        return BankAccess.objects.filter(organization=self.org).order_by("name", "pk")

    def list(self, request, *args, **kwargs):
        return Response(
            {
                "available": bank_fetch.available(),
                "enabled": bank_fetch.enabled(self.org),
                "accesses": self.get_serializer(self.get_queryset(), many=True).data,
            }
        )

    def _require_enabled(self):
        if not bank_fetch.enabled(self.org):
            raise serializers.ValidationError(
                gettext("Die Bankanbindung ist für diesen Verein nicht eingeschaltet.")
            )

    def perform_create(self, serializer):
        self._require_enabled()
        step_up.require(self.request)
        access = serializer.save(organization=self.org, created_by=self.request.user)
        record(self.org, self.request.user, "create", access, {"Bankzugang": [None, access.name]})

    def perform_update(self, serializer):
        self._require_enabled()
        step_up.require(self.request)
        before = serializer.instance
        changed = {
            field
            for field in ("bank_code", "url", "login", "customer_id")
            if field in serializer.validated_data
            and serializer.validated_data[field] != getattr(before, field)
        }
        access = serializer.save()
        if changed:
            # Andere Bank oder anderer Anmeldename: Sitzungsstand und Konten gelten nicht mehr
            access.state = ""
            access.ready = False
            access.ibans = []
            access.tan_mechanism = access.tan_mechanism_name = access.tan_medium = ""
            access.failures = 0
            access.locked_until = None
            access.save()
            access.accounts.update(bank_access=None)
        record(
            self.org,
            self.request.user,
            "update",
            access,
            {"Bankzugang": [None, "Zugangsdaten geändert" if changed else "Bezeichnung geändert"]},
        )

    def perform_destroy(self, instance):
        step_up.require(self.request)
        record(
            self.org, self.request.user, "delete", instance, {"Bankzugang": [instance.name, None]}
        )
        instance.delete()

    def _step(self, request, kind: str):
        access = self.get_object()
        data = StepSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        options = {key: values[key] for key in ("mechanism", "medium") if values.get(key)}
        try:
            answer = bank_fetch.begin(
                self.org,
                access,
                request.user,
                values["pin"],
                kind,
                options=options,
                confirm_retry=values["confirm_retry"],
            )
        except BankError as exc:
            raise BankProblem(exc) from exc
        return Response(answer)

    @action(detail=True, methods=["post"])
    def setup(self, request, org_id: int, pk=None):
        """Anmelden, TAN-Verfahren festlegen und die Konten der Bank holen."""
        self._require_enabled()
        step_up.require(request)
        return self._step(request, BankTask.Kind.SETUP)

    @action(detail=True, methods=["post"])
    def fetch(self, request, org_id: int, pk=None):
        """Umsätze aller Konten des Zugangs abrufen und einlesen."""
        return self._step(request, BankTask.Kind.FETCH)


class BankTaskSerializer(serializers.ModelSerializer):
    access_name = serializers.CharField(source="access.name", read_only=True)

    class Meta:
        model = BankTask
        fields = [
            "id",
            "access",
            "access_name",
            "kind",
            "status",
            "message",
            "created_at",
            "finished_at",
        ]
        read_only_fields = fields


class BankTaskViewSet(FinanceMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Vorgänge bei der Bank: Liste zum Nachvollziehen, Fortsetzen nach der Freigabe."""

    pagination_class = None

    serializer_class = BankTaskSerializer

    def get_queryset(self):
        return (
            BankTask.objects.filter(organization=self.org)
            .select_related("access")
            .order_by("-created_at", "-pk")[:50]
        )

    def _task(self, pk) -> BankTask:
        return get_object_or_404(BankTask, organization=self.org, pk=pk)

    @action(detail=True, methods=["post"], url_path="continue")
    def proceed(self, request, org_id: int, pk=None):
        task = self._task(pk)
        if task.user_id != request.user.pk:
            raise serializers.ValidationError(
                gettext("Diesen Vorgang hat eine andere Person begonnen.")
            )
        data = StepSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            answer = bank_fetch.proceed(
                self.org,
                task,
                request.user,
                data.validated_data["pin"],
                data.validated_data.get("tan", ""),
            )
        except BankError as exc:
            raise BankProblem(exc) from exc
        return Response(answer)

    @action(detail=True, methods=["post"])
    def cancel(self, request, org_id: int, pk=None):
        bank_fetch.cancel(self._task(pk))
        return Response(status=status.HTTP_204_NO_CONTENT)
