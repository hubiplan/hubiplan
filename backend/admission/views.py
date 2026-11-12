"""Online-Anträge im Verein: Einrichtung, Liste, Prüfseite, Entscheidungen, Stand-Links.

Lesen: „Mitglieder lesen“; entscheiden, korrigieren, einrichten: „Mitglieder bearbeiten“.
Zustimmen dürfen zusätzlich alle, die die Regel des Vereins nennt (admission/rules.py).
"""

from __future__ import annotations

import datetime

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import MEMBERS_EDIT, MEMBERS_VIEW
from audit.log import record
from core.api_base import OrgScopedMixin
from members.models import MemberType, Person
from members.serializers import OptionalDateField
from organizations.models import Department, Organization

from . import public, rules, services
from .models import Application, ApplicationForm, KioskLink


class _Mixin(OrgScopedMixin):
    allowed_org_types = (Organization.Type.CLUB, Organization.Type.FEDERATION)
    read_permission = MEMBERS_VIEW
    write_permission = MEMBERS_EDIT

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        from rest_framework.exceptions import NotFound

        if not self.org.keeps_members:
            raise NotFound()


def form_data(form: ApplicationForm, request) -> dict:
    from access.models import Role
    from customfields.views import definitions_for

    org = form.organization
    from members.models import MemberType as MT

    return {
        "enabled": form.enabled,
        "public_key": form.public_key,
        "form_url": f"{services.base_url(org)}/mitglied-werden/{form.public_key}",
        "types": form.types,
        "fields": {k: (form.fields or {}).get(k, "off") for k in public.FIELD_KEYS},
        "custom_fields": form.custom_fields,
        "sepa": form.sepa,
        "sepa_available": public.sepa_state(ApplicationForm(organization=org, sepa="offer"))[0]
        != "off",
        "confirm_statute": form.confirm_statute,
        "confirm_fee_rules": form.confirm_fee_rules,
        "statute_docs": public.statute_docs(org, request),
        "consents": form.consents,
        "signature": form.signature,
        "texts": form.texts,
        "notify_roles": form.notify_roles,
        "rule": form.rule,
        "rule_text": rules.describe(form.rule or {}, org),
        "entry_date": form.entry_date,
        "purge_months": form.purge_months,
        "min_age": form.min_age,
        "minors": form.minors,
        "choices": {
            "member_types": [
                {"id": t.pk, "name": t.name}
                for t in MT.objects.filter(organization=org, is_archived=False).order_by(
                    "sort_order", "name"
                )
            ],
            "roles": [
                {"id": r.pk, "name": r.name}
                for r in Role.objects.filter(organization=org).order_by("position", "name")
            ],
            "custom_fields": [
                {"id": d.pk, "label": d.label}
                for d in definitions_for(org)
                if not d.is_archived and not d.repeatable
            ],
            "consents": public.allowed_consents(),
            "units": [{"id": u.pk, "name": u.name} for u in public.units_of(org)],
        },
    }


class FormSettingsView(_Mixin, APIView):
    def get(self, request, org_id: int):
        return Response(form_data(services.form_for(self.org), request))

    @transaction.atomic
    def patch(self, request, org_id: int):
        form = services.form_for(self.org)
        values = public.clean_settings(form, request.data)
        changes = {}
        for key, value in values.items():
            if getattr(form, key) != value:
                changes[key] = [getattr(form, key), value]
                setattr(form, key, value)
        if changes:
            form.save()
            record(
                self.org,
                request.user,
                "update",
                form,
                {
                    k: v
                    for k, v in changes.items()
                    if k in ("enabled", "sepa", "signature", "entry_date", "rule")
                },
            )
        return Response(form_data(form, request))


def approvals_data(app: Application) -> list[dict]:
    return [
        {
            "id": a.pk,
            "user_name": a.user_name,
            "roles": a.role_names,
            "for_unit": a.for_unit,
            "decision": a.decision,
            "note": a.note,
            "created_at": a.created_at,
        }
        for a in app.approvals.all()
    ]


def row(app: Application, form: ApplicationForm) -> dict:
    st = services.state(app, form) if app.is_open else None
    d = app.data or {}
    return {
        "id": app.pk,
        "number": app.number,
        "status": app.status,
        "status_label": str(Application.Status(app.status).label),
        "source": app.source,
        "kind": app.kind,
        "name": app.display_name,
        "last_name": d.get("last_name", ""),
        "first_name": d.get("first_name", ""),
        "birth_date": d.get("birth_date") or None,
        "member_type": app.member_type.name if app.member_type_id else "",
        "member_type_id": app.member_type_id,
        "unit": app.unit.name if app.unit_id else "",
        "unit_id": app.unit_id,
        "minor": bool(app.guardians),
        "created_at": app.created_at,
        "approvals_met": st.met if st else None,
        "disputed": st.disputed if st else False,
        "missing": st.missing if st else [],
        "membership_id": app.membership_id,
    }


class ApplicationListView(_Mixin, APIView):
    def get(self, request, org_id: int):
        form = services.form_for(self.org)
        qs = (
            Application.objects.filter(organization=self.org)
            .exclude(status="unconfirmed")
            .select_related("member_type", "unit")
            .prefetch_related("approvals")
        )
        wanted = request.query_params.get("status", "offen")
        if wanted == "offen":
            qs = qs.filter(status__in=Application.OPEN_STATES)
        elif wanted in Application.Status.values:
            qs = qs.filter(status=wanted)
        if request.query_params.get("art"):
            qs = qs.filter(member_type_id=request.query_params["art"])
        if request.query_params.get("einheit"):
            qs = qs.filter(unit_id=request.query_params["einheit"])
        rows = [row(a, form) for a in qs[:500]]
        return Response(
            {
                "results": rows,
                "enabled": form.enabled,
                "rule": form.rule,
                "rule_text": rules.describe(form.rule or {}, self.org),
                "may_approve": rules.may_approve(
                    form.rule or {}, rules.user_roles(request.user, self.org), self.org_permissions
                ),
                "counts": {
                    s: Application.objects.filter(organization=self.org, status=s).count()
                    for s in Application.OPEN_STATES
                },
            }
        )


def find_matches(org, app: Application) -> dict:
    """Treffer für die Prüfung: eigene, frühere, verbandsweite, anderswo aktive."""
    from members import services as member_services
    from members.models import Membership

    d = app.data or {}
    birth = public_date(d.get("birth_date"))
    if app.kind == "organization":
        found = member_services.find_duplicates(
            org, d.get("last_name", ""), "", None, organization=True
        )
    elif birth:
        found = member_services.find_duplicates(
            org, d.get("last_name", ""), d.get("first_name", ""), birth
        )
    else:
        found = member_services.club_namesakes(org, d.get("last_name", ""), d.get("first_name", ""))
    result = []
    today = timezone.localdate()
    for person in found:
        here = Membership.objects.filter(organization=org, person=person).first()
        elsewhere = member_services.active_elsewhere(person, org, today)
        result.append(
            {
                "person_id": person.pk,
                "name": person.display_name,
                "birth_date": person.birth_date,
                "here": bool(here),
                "member_id": here.pk if here else None,
                "former": bool(here and here.current_period(today) is None),
                "active_elsewhere": elsewhere or "",
            }
        )
    return {"persons": result}


def public_date(value):
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        return None


class ApplicationDetailView(_Mixin, APIView):
    def get_app(self, pk: int) -> Application:
        return get_object_or_404(
            Application.objects.select_related("member_type", "unit", "decided_by"),
            organization=self.org,
            pk=pk,
        )

    def payload(self, app: Application, request) -> dict:
        form = services.form_for(self.org)
        from billing.sepa import masked_iban

        data = row(app, form)
        d = dict(app.data or {})
        d.pop("custom_values", None)
        mandate = None
        if app.mandate:
            mandate = {
                "holder": app.mandate.get("holder", ""),
                "iban": masked_iban(app.mandate.get("iban", "")),
                "bic": app.mandate.get("bic", ""),
            }
        roles = rules.user_roles(request.user, self.org)
        data.update(
            {
                "data": d,
                "summary": services.summary_lines(app),
                "entry_wish": app.entry_wish,
                "mandate": mandate,
                "consents": app.consents,
                "guardians": app.guardians,
                "signed": bool(app.signature),
                "signed_at": app.signed_at,
                "confirmed_at": app.confirmed_at,
                "decided_at": app.decided_at,
                "decided_by": services._user_name(app.decided_by) if app.decided_by else "",
                "decision_note": app.decision_note,
                "approvals": approvals_data(app),
                "events": [
                    {
                        "kind": e.kind,
                        "note": e.note,
                        "created_at": e.created_at,
                        "user": services._user_name(e.user) if e.user else "",
                    }
                    for e in app.events.select_related("user")
                ],
                "matches": find_matches(self.org, app) if app.is_open else {"persons": []},
                "rule": form.rule,
                "rule_text": rules.describe(form.rule or {}, self.org),
                "entry_date": services.entry_date_for(app, form),
                "may_approve": rules.may_approve(form.rule or {}, roles, self.org_permissions),
                "may_decide": MEMBERS_EDIT in self.org_permissions,
                "own_decision": next(
                    (
                        a.decision
                        for a in app.approvals.all()
                        if a.user_id == request.user.pk and not a.for_unit
                    ),
                    None,
                ),
                "portal_available": bool(getattr(self.org, "member_portal_enabled", False)),
            }
        )
        return data

    def get(self, request, org_id: int, pk: int):
        return Response(self.payload(self.get_app(pk), request))

    @transaction.atomic
    def patch(self, request, org_id: int, pk: int):
        """Angaben korrigieren (setzt Zustimmungen zurück)."""
        app = self.get_app(pk)
        allowed = (
            "last_name",
            "first_name",
            "birth_date",
            "gender",
            "email",
            "phone",
            "street",
            "address_extra",
            "postal_code",
            "city",
            "country",
            "note",
        )
        changes = {k: str(request.data[k]).strip() for k in allowed if k in request.data}
        if "birth_date" in changes and changes["birth_date"]:
            if public_date(changes["birth_date"]) is None:
                raise serializers.ValidationError({"birth_date": gettext("Ungültiges Datum.")})
        services.update_data(app, request.user, changes)
        member_type = unit = None
        if request.data.get("member_type"):
            member_type = get_object_or_404(
                MemberType, organization=self.org, pk=request.data["member_type"], is_archived=False
            )
        unit_given = "unit" in request.data
        if unit_given and request.data.get("unit"):
            unit = get_object_or_404(Department, organization=self.org, pk=request.data["unit"])
        services.set_choice(app, request.user, member_type, unit, unit_given)
        return Response(self.payload(self.get_app(pk), request))


class AcceptSerializer(serializers.Serializer):
    entry_date = OptionalDateField()
    member_type = serializers.IntegerField(required=False, allow_null=True)
    club_number = serializers.CharField(max_length=30, required=False, allow_blank=True)
    person = serializers.IntegerField(required=False, allow_null=True)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)
    welcome = serializers.BooleanField(default=True)
    invite = serializers.BooleanField(default=False)


class ActionView(ApplicationDetailView):
    """POST mit ``action``: accept, reject, approve, ask, resume, signed."""

    http_method_names = ["post", "options"]

    read_permission = MEMBERS_VIEW
    write_permission = MEMBERS_VIEW  # feiner je Aktion (Zustimmende brauchen kein Bearbeiten)

    @transaction.atomic
    def post(self, request, org_id: int, pk: int, action: str):
        app = self.get_app(pk)
        perms = self.org_permissions
        edit = MEMBERS_EDIT in perms
        if action == "approve":
            services.approve(
                app,
                request.user,
                perms,
                request.data.get("decision", "approve"),
                request.data.get("note", ""),
                bool(request.data.get("for_unit")),
            )
        elif not edit:
            raise PermissionDenied(gettext("Dafür fehlt dir die Berechtigung."))
        elif action == "accept":
            ser = AcceptSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            v = dict(ser.validated_data)
            if v.get("member_type"):
                v["member_type"] = get_object_or_404(
                    MemberType, organization=self.org, pk=v["member_type"], is_archived=False
                )
            if v.get("person"):
                from members import services as member_services

                scope = member_services.scope_for(self.org)
                v["person"] = get_object_or_404(Person, scope=scope, pk=v["person"])
            services.accept(app, request.user, perms, v)
        elif action == "reject":
            services.reject(
                app,
                request.user,
                request.data.get("note", ""),
                bool(request.data.get("send_mail")),
                request.data.get("text", ""),
            )
        elif action == "ask":
            services.ask(app, request.user, request.data.get("text", ""))
        elif action == "resume":
            services.resume(app, request.user)
        elif action == "signed":
            services.mark_signed(app, request.user)
        else:
            return Response({"detail": gettext("Unbekannte Aktion.")}, status=400)
        return Response(self.payload(self.get_app(pk), request))


class BulkAcceptView(_Mixin, APIView):
    """Sammelannahme geprüfter Anträge mit gleichem Eintrittsdatum (B5)."""

    @transaction.atomic
    def post(self, request, org_id: int):
        ids = request.data.get("ids") or []
        if not isinstance(ids, list) or not ids or len(ids) > 200:
            raise serializers.ValidationError({"ids": gettext("Bitte Anträge auswählen.")})
        entry = OptionalDateField().to_internal_value(request.data.get("entry_date"))
        done, failed = [], []
        for app in Application.objects.filter(organization=self.org, pk__in=ids):
            sid = transaction.savepoint()
            try:
                services.accept(
                    app,
                    request.user,
                    self.org_permissions,
                    {"entry_date": entry, "invite": bool(request.data.get("invite"))},
                )
                transaction.savepoint_commit(sid)
                done.append(app.pk)
            except Exception as exc:  # noqa: BLE001 - je Antrag melden, Rest weiter
                transaction.savepoint_rollback(sid)
                detail = getattr(exc, "detail", None) or str(exc)
                failed.append({"id": app.pk, "number": app.number, "detail": str(detail)})
        return Response({"accepted": done, "failed": failed})


class PdfView(ApplicationDetailView):
    http_method_names = ["get", "options"]

    def get(self, request, org_id: int, pk: int):
        from .pdf import render

        app = self.get_app(pk)
        response = HttpResponse(render(app), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="mitgliedsantrag-{app.number}.pdf"'
        return response


class QrView(_Mixin, APIView):
    """QR-Code der Formularadresse (B4), auf Wunsch mit vorgewählter Untereinheit."""

    def get(self, request, org_id: int):
        from reportlab.graphics import renderSVG
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics.shapes import Drawing

        form = services.form_for(self.org)
        url = f"{services.base_url(self.org)}/mitglied-werden/{form.public_key}"
        unit = request.query_params.get("einheit")
        if (
            unit
            and unit.isdigit()
            and Department.objects.filter(organization=self.org, pk=int(unit)).exists()
        ):
            url += f"?einheit={int(unit)}"
        widget = QrCodeWidget(url, barLevel="M")
        x1, y1, x2, y2 = widget.getBounds()
        size = 300
        drawing = Drawing(size, size, transform=[size / (x2 - x1), 0, 0, size / (y2 - y1), 0, 0])
        drawing.add(widget)
        svg = renderSVG.drawToString(drawing)
        response = HttpResponse(svg, content_type="image/svg+xml")
        response["Content-Disposition"] = 'inline; filename="mitglied-werden.svg"'
        return response


class KioskListView(_Mixin, APIView):
    def get(self, request, org_id: int):
        now = timezone.now()
        rows = KioskLink.objects.filter(
            organization=self.org, valid_until__gt=now, revoked_at__isnull=True
        )
        return Response(
            [{"id": k.pk, "label": k.label, "valid_until": k.valid_until} for k in rows]
        )

    @transaction.atomic
    def post(self, request, org_id: int):
        hours = request.data.get("hours", 12)
        if not isinstance(hours, int):
            raise serializers.ValidationError({"hours": gettext("Ungültige Dauer.")})
        link, url = services.create_kiosk(
            self.org, request.user, request.data.get("label", ""), hours
        )
        record(self.org, request.user, "create", link, {"Stand-Link": [None, link.label]})
        return Response(
            {"id": link.pk, "label": link.label, "valid_until": link.valid_until, "url": url},
            status=status.HTTP_201_CREATED,
        )


class KioskDetailView(_Mixin, APIView):
    @transaction.atomic
    def delete(self, request, org_id: int, pk: int):
        link = get_object_or_404(KioskLink, organization=self.org, pk=pk)
        link.revoked_at = timezone.now()
        link.save(update_fields=["revoked_at"])
        record(self.org, request.user, "update", link, {"Stand-Link": [link.label, "beendet"]})
        return Response(status=status.HTTP_204_NO_CONTENT)
