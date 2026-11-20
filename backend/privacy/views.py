"""Schnittstelle der Datenschutz-Werkzeuge: Verzeichnis, Auftragsverarbeiter, Datenpannen."""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record

from . import access, report, services
from .catalog import BY_KEY
from .models import DataBreach, PrivacySettings, ProcessingActivity

MAX_ACTIVITIES = 100
MAX_BREACHES = 500


def conflict():
    exc = APIException(_("Der Eintrag wurde inzwischen geändert. Bitte neu laden."))
    exc.status_code = 409
    return exc


def iso(value):
    return value.isoformat() if value else None


def breach_data(b: DataBreach, now) -> dict:
    return {
        "id": b.pk,
        "title": b.title,
        "discovered_at": iso(b.discovered_at),
        "occurred": b.occurred,
        "description": b.description,
        "categories": b.categories,
        "affected": b.affected,
        "consequences": b.consequences,
        "measures": b.measures,
        "risk": b.risk,
        "report_deadline": iso(b.report_deadline),
        "reported_at": iso(b.reported_at),
        "report_reference": b.report_reference,
        "no_report_reason": b.no_report_reason,
        "notified_at": iso(b.notified_at),
        "closed_at": iso(b.closed_at),
        "status": services.breach_status(b, now),
        "created_by": (b.created_by.get_full_name() or b.created_by.email) if b.created_by else "",
        "version": b.version,
    }


class SettingsInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1, required=False)
    dpo_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    dpo_contact = serializers.CharField(max_length=300, required=False, allow_blank=True)
    hoster = serializers.CharField(max_length=300, required=False, allow_blank=True)
    toms = serializers.CharField(max_length=10000, required=False, allow_blank=True)


class ActivityInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1, required=False)
    title = serializers.CharField(max_length=200, required=False)
    purpose = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    legal_basis = serializers.CharField(max_length=300, required=False, allow_blank=True)
    subjects = serializers.CharField(max_length=300, required=False, allow_blank=True)
    categories = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    recipients = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    third_country = serializers.CharField(max_length=300, required=False, allow_blank=True)
    retention = serializers.CharField(max_length=3000, required=False, allow_blank=True)


class HideInput(serializers.Serializer):
    key = serializers.CharField(max_length=40)
    hidden = serializers.BooleanField()


class BreachInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1, required=False)
    title = serializers.CharField(max_length=200, required=False)
    discovered_at = serializers.DateTimeField(required=False)
    occurred = serializers.CharField(max_length=200, required=False, allow_blank=True)
    description = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    categories = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    affected = serializers.CharField(max_length=300, required=False, allow_blank=True)
    consequences = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    measures = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    risk = serializers.ChoiceField(choices=DataBreach.Risk.choices, required=False)
    reported_at = serializers.DateTimeField(required=False, allow_null=True)
    report_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    no_report_reason = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    notified_at = serializers.DateTimeField(required=False, allow_null=True)
    closed = serializers.BooleanField(required=False)


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.scope = access.scope_for(request.user, kwargs.get("org_id"))

    @property
    def org(self):
        return self.scope.org


class OverviewView(Base):
    """GET Verzeichnis (``?als=pdf``: als PDF), Auftragsverarbeiter und Stand der Pannen."""

    def get(self, request, **kwargs):
        settings = services.settings_for(self.org)
        if request.query_params.get("als") == "pdf":
            from finance.views import _file_response

            return _file_response(
                report.register_pdf(self.org, settings),
                _("Verarbeitungsverzeichnis"),
                "pdf",
                request.query_params.get("download") == "1",
            )
        now = timezone.now()
        return Response(
            {
                "controller": services.controller(self.org),
                "settings": {
                    "dpo_name": settings.dpo_name,
                    "dpo_contact": settings.dpo_contact,
                    "hoster": settings.hoster,
                    "toms": settings.toms,
                    "version": settings.version,
                },
                "activities": services.activities(
                    self.org, settings, with_hidden=self.scope.can_edit
                ),
                "processors": services.processors(self.org),
                "open_breaches": [breach_data(b, now) for b in services.open_breaches(self.org)],
                "can_edit": self.scope.can_edit,
                "can_partners": "partners.view" in self.scope.permissions,
            }
        )


class SettingsView(Base):
    @transaction.atomic
    def put(self, request, **kwargs):
        access.require_edit(self.scope)
        ser = SettingsInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        version = data.pop("version", None)
        obj = PrivacySettings.objects.select_for_update().filter(organization=self.org).first()
        if obj is None:
            obj = services.settings_for(self.org)
        elif version is not None and version != obj.version:
            raise conflict()
        else:
            obj.version += 1
        for field, value in data.items():
            setattr(obj, field, value.strip())
        obj.updated_by = request.user
        obj.save()
        record(self.org, request.user, "update", obj, {_("Datenschutz"): [None, ", ".join(data)]})
        return Response({**{f: getattr(obj, f) for f in data}, "version": obj.version})


class HideView(Base):
    @transaction.atomic
    def post(self, request, **kwargs):
        """Vorschlag aus dem Verzeichnis nehmen oder wieder aufnehmen."""
        access.require_edit(self.scope)
        ser = HideInput(data=request.data)
        ser.is_valid(raise_exception=True)
        key, hidden = ser.validated_data["key"], ser.validated_data["hidden"]
        if key not in BY_KEY:
            raise ValidationError({"key": _("Unbekannter Vorschlag.")})
        obj = PrivacySettings.objects.select_for_update().filter(organization=self.org).first()
        obj = obj or services.settings_for(self.org)
        keys = set(obj.hidden_keys or [])
        keys = keys | {key} if hidden else keys - {key}
        obj.hidden_keys = sorted(keys)
        obj.updated_by = request.user
        obj.save()
        title = _(BY_KEY[key].title)
        record(
            self.org,
            request.user,
            "update",
            obj,
            {_("Verarbeitungsverzeichnis"): [None if hidden else title, title if hidden else None]},
        )
        return Response({"hidden_keys": obj.hidden_keys})


class ActivityListView(Base):
    @transaction.atomic
    def post(self, request, **kwargs):
        access.require_edit(self.scope)
        ser = ActivityInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        data.pop("version", None)
        if not (data.get("title") or "").strip():
            raise ValidationError({"title": _("Bitte eine Bezeichnung eingeben.")})
        if ProcessingActivity.objects.filter(organization=self.org).count() >= MAX_ACTIVITIES:
            raise ValidationError({"detail": _("Höchstens 100 eigene Tätigkeiten.")})
        a = ProcessingActivity.objects.create(
            organization=self.org, **{k: v.strip() for k, v in data.items()}
        )
        record(self.org, request.user, "create", a, {_("Verarbeitungstätigkeit"): [None, a.title]})
        return Response({**services.own_data(a), "hidden": False}, status=201)


class ActivityDetailView(Base):
    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        qs = ProcessingActivity.objects.filter(organization=self.org).select_for_update()
        a = get_object_or_404(qs, pk=pk)
        ser = ActivityInput(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        version = data.pop("version", None)
        if version is not None and version != a.version:
            raise conflict()
        before = a.title
        for field, value in data.items():
            setattr(a, field, value.strip())
        if not a.title:
            raise ValidationError({"title": _("Bitte eine Bezeichnung eingeben.")})
        a.version += 1
        a.save()
        record(
            self.org, request.user, "update", a, {_("Verarbeitungstätigkeit"): [before, a.title]}
        )
        return Response({**services.own_data(a), "hidden": False})

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        a = get_object_or_404(ProcessingActivity.objects.filter(organization=self.org), pk=pk)
        record(self.org, request.user, "delete", a, {_("Verarbeitungstätigkeit"): [a.title, None]})
        a.delete()
        return Response(status=204)


def apply_breach(b: DataBreach, data: dict) -> None:
    closed = data.pop("closed", None)
    for field, value in data.items():
        setattr(b, field, value.strip() if isinstance(value, str) else value)
    if not (b.title or "").strip():
        raise ValidationError({"title": _("Bitte eine Kurzbezeichnung eingeben.")})
    if b.discovered_at is None:
        raise ValidationError({"discovered_at": _("Bitte angeben, wann die Panne bekannt wurde.")})
    now = timezone.now()
    if b.discovered_at > now:
        raise ValidationError({"discovered_at": _("Der Zeitpunkt liegt in der Zukunft.")})
    for field in ("reported_at", "notified_at"):
        value = getattr(b, field)
        if value and value < b.discovered_at:
            raise ValidationError({field: _("Der Zeitpunkt liegt vor dem Bekanntwerden.")})
    if closed is True and not b.closed_at:
        if b.needs_report and not b.reported_at and not b.no_report_reason:
            raise ValidationError(
                {
                    "closed": _(
                        "Vor dem Abschluss bitte die Meldung an die Aufsichtsbehörde eintragen "
                        "oder begründen, warum nicht gemeldet wurde."
                    )
                }
            )
        b.closed_at = now
    elif closed is False:
        b.closed_at = None


class BreachListView(Base):
    def get(self, request, **kwargs):
        now = timezone.now()
        rows = DataBreach.objects.filter(organization=self.org).select_related("created_by")
        return Response(
            {"items": [breach_data(b, now) for b in rows], "can_edit": self.scope.can_edit}
        )

    @transaction.atomic
    def post(self, request, **kwargs):
        access.require_edit(self.scope)
        ser = BreachInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        data.pop("version", None)
        if DataBreach.objects.filter(organization=self.org).count() >= MAX_BREACHES:
            raise ValidationError({"detail": _("Zu viele Einträge.")})
        b = DataBreach(organization=self.org, created_by=request.user)
        apply_breach(b, data)
        b.save()
        record(self.org, request.user, "create", b, {_("Datenpanne"): [None, b.title]})
        return Response(breach_data(b, timezone.now()), status=201)


class BreachDetailView(Base):
    def get(self, request, pk, **kwargs):
        b = get_object_or_404(DataBreach.objects.filter(organization=self.org), pk=pk)
        if request.query_params.get("als") == "pdf":
            from finance.views import _file_response

            return _file_response(
                report.breach_pdf(self.org, b),
                _("Datenpanne-{n}").format(n=b.pk),
                "pdf",
                request.query_params.get("download") == "1",
            )
        return Response(breach_data(b, timezone.now()))

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        qs = DataBreach.objects.filter(organization=self.org).select_for_update()
        b = get_object_or_404(qs, pk=pk)
        ser = BreachInput(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        version = data.pop("version", None)
        if version is not None and version != b.version:
            raise conflict()
        was_closed = bool(b.closed_at)
        apply_breach(b, data)
        b.version += 1
        b.save()
        change = {_("Datenpanne"): [b.title, b.title]}
        if was_closed != bool(b.closed_at):
            change = {_("Abgeschlossen"): [str(was_closed), str(bool(b.closed_at))]}
        record(self.org, request.user, "update", b, change)
        return Response(breach_data(b, timezone.now()))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        """Nur für versehentliche Einträge; das Änderungsprotokoll hält das Löschen fest."""
        access.require_edit(self.scope)
        b = get_object_or_404(DataBreach.objects.filter(organization=self.org), pk=pk)
        record(self.org, request.user, "delete", b, {_("Datenpanne"): [b.title, None]})
        b.delete()
        return Response(status=204)
