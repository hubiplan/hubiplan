"""Auslagen im Mitgliederbereich und in der App (``/api/portal/<Zugang>/expenses/…``).

Das Mitglied sieht nur die eigenen Anträge. Entwürfe aus der App kommen mit der Kopfzeile
``Idempotency-Key``: Ein ohne Netz gespeicherter Antrag, der später zweimal gesendet wird,
entsteht nur einmal.
"""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from changes import idempotency
from core.tenancy import scope_of, set_rls, user_view

from . import services
from .data import claim_data, drf_errors
from .models import ExpenseClaim, ExpenseFile
from .views import claims_qs, file_response

S = ExpenseClaim.Status


def form_data(request) -> dict:
    """Angaben als dict; bei mehrteiligen Formularen (App mit Foto) kommen Positionen und
    Bankverbindung als JSON-Text."""
    import json

    data = {k: request.data.get(k) for k in request.data.keys() if k != "file"}
    for field in ("lines", "payee"):
        if isinstance(data.get(field), str):
            try:
                data[field] = json.loads(data[field]) if data[field] else None
            except ValueError as exc:
                raise serializers.ValidationError({field: gettext("Ungültige Angabe.")}) from exc
    return data


def portal_access(user, access_id):
    from portal.views import _portal_access

    with user_view(user.pk):
        access = _portal_access(user, access_id)
    set_rls(access.organization_id, user.pk, scope_id=scope_of(access.organization_id))
    if not services.enabled(access.organization):
        raise NotFound()
    if access.contact_person_id is not None:
        # Ansprechpartner einer Organisation: keine eigenen Auslagen
        raise NotFound()
    return access


def options(access) -> dict:
    from finance.models import Category, Project
    from organizations.models import Department

    org = access.organization
    cfg = services.settings_for(org)
    membership = access.membership
    advances = [
        {"id": a.pk, "number": a.number, "amount": str(a.payout_amount), "purpose": a.purpose}
        for a in ExpenseClaim.objects.filter(
            organization=org,
            membership=membership,
            kind=ExpenseClaim.Kind.ADVANCE,
            status=S.PAID,
        )
        if getattr(a, "settlement", None) is None
        or a.settlement.status in (S.REJECTED, S.WITHDRAWN)
    ]
    return {
        "may_submit": services.may_submit(org, membership),
        "mileage_enabled": cfg.mileage_enabled,
        "km_rate": str(cfg.km_rate),
        "advances_enabled": cfg.advances_enabled,
        "waiver_enabled": bool(cfg.waiver_basis and cfg.waiver_basis_date)
        and "donations" in (org.enabled_modules or []),
        "payee": services.suggested_payee(org, membership),
        "departments": [
            {"id": d.pk, "name": d.name}
            for d in Department.objects.filter(organization=org, is_active=True).order_by(
                "sort_order", "name"
            )
        ],
        "projects": [
            {"id": p.pk, "name": p.name}
            for p in Project.objects.filter(organization=org)
            .exclude(status=Project.Status.DONE)
            .order_by("name")[:100]
        ],
        "categories": [
            {"id": c.pk, "name": c.name}
            for c in Category.objects.filter(
                organization=org, is_active=True, kind__in=("expense", "both")
            ).order_by("name")
        ],
        "open_advances": advances,
    }


class MemberMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.access = portal_access(request.user, kwargs["access_id"])
        self.org = self.access.organization

    def mine(self):
        return claims_qs(self.org).filter(membership_id=self.access.membership_id)

    def get_claim(self, pk: int) -> ExpenseClaim:
        claim = self.mine().filter(pk=pk).first()
        if claim is None:
            raise NotFound()
        return claim

    def out(self, claim: ExpenseClaim, code=status.HTTP_200_OK) -> Response:
        claim = claims_qs(self.org).prefetch_related("events").get(pk=claim.pk)
        data = claim_data(claim, viewer=self.request.user, full=True, member=True)
        # Interne Bemerkungen der Kasse (Hinweise, Budget) sieht das Mitglied nicht
        return Response(data, status=code)

    def ensure_submit(self):
        if not services.may_submit(self.org, self.access.membership):
            raise PermissionDenied(
                gettext("Auslagen melden hier nur Personen mit Amt oder Rolle im Verein.")
            )


class ListView(MemberMixin, APIView):
    """GET: eigene Auslagen und Auswahllisten · POST: neue Auslage (Entwurf)."""

    def get(self, request, access_id: int):
        rows = [
            claim_data(c, member=True) for c in self.mine().order_by("-created_at", "-pk")[:200]
        ]
        return Response({"claims": rows, "options": options(self.access)})

    @transaction.atomic
    def post(self, request, access_id: int):
        self.ensure_submit()
        key = idempotency.claim(request, f"expenses.portal.{self.access.pk}")
        if key.done:
            return self.out(self.get_claim(key.result["id"]))
        source = (
            ExpenseClaim.Source.APP
            if type(request.auth).__name__ == "Device" or request.data.get("source") == "app"
            else ExpenseClaim.Source.PORTAL
        )
        claim = ExpenseClaim.objects.create(
            organization=self.org,
            membership=self.access.membership,
            user=request.user,
            source=source,
            created_by=request.user,
        )
        data = form_data(request)
        if not data.get("payee") and data.get("payout", "bank") == "bank":
            data = {**data, "payee": services.suggested_payee(self.org, self.access.membership)}
        with drf_errors():
            services.apply_changes(claim, data)
            # Ein Schritt aus der App: Belege gleich mit, auf Wunsch sofort einreichen
            for upload in request.FILES.getlist("file"):
                services.add_file(claim, upload, request.user)
        services.log(claim, "created", request.user)
        if str(request.data.get("submit") or "").lower() in ("1", "true", "yes"):
            with drf_errors():
                services.submit(claim, request.user)
        key.remember({"id": claim.pk})
        return self.out(claim, status.HTTP_201_CREATED)


class DetailView(MemberMixin, APIView):
    def get(self, request, access_id: int, pk: int):
        return self.out(self.get_claim(pk))

    @transaction.atomic
    def patch(self, request, access_id: int, pk: int):
        claim = self.get_claim(pk)
        claim = ExpenseClaim.objects.select_for_update().get(pk=claim.pk)
        if claim.status not in services.OPEN_FOR_MEMBER:
            raise serializers.ValidationError(
                gettext("Eingereichte Auslagen ändert nur eine Rückfrage der Kasse.")
            )
        version = request.data.get("version")
        if version not in (None, "") and str(version) != str(claim.version):
            raise serializers.ValidationError(
                gettext("Die Auslage wurde inzwischen geändert. Bitte neu laden.")
            )
        with drf_errors():
            services.apply_changes(claim, form_data(request))
        claim.version += 1
        claim.save(update_fields=["version", "updated_at"])
        return self.out(claim)

    @transaction.atomic
    def delete(self, request, access_id: int, pk: int):
        claim = self.get_claim(pk)
        if claim.status != S.DRAFT or claim.number:
            raise serializers.ValidationError(gettext("Nur Entwürfe lassen sich löschen."))
        from core.files import delete_on_commit

        for row in claim.files.all():
            if row.file:
                delete_on_commit(row.file)
        claim.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActionView(MemberMixin, APIView):
    """POST <Auslage>/submit|withdraw|answer|waive/."""

    def post(self, request, access_id: int, pk: int, action: str):
        claim = self.get_claim(pk)
        with drf_errors(), transaction.atomic():
            if action == "submit":
                self.ensure_submit()
                claim = services.submit(claim, request.user)
            elif action == "answer":
                claim = services.answer(claim, request.user, request.data.get("text"))
            elif action == "withdraw":
                claim = services.withdraw(claim, request.user)
                if not ExpenseClaim.objects.filter(pk=pk).exists():
                    return Response(status=status.HTTP_204_NO_CONTENT)
            elif action == "waive":
                claim = services.waive(claim, request.user)
            else:
                raise NotFound()
        return self.out(claim)


class FilesView(MemberMixin, APIView):
    """POST: Beleg hinzufügen (Entwurf oder Rückfrage)."""

    virus_quarantine = True

    @transaction.atomic
    def post(self, request, access_id: int, pk: int):
        claim = self.get_claim(pk)
        if claim.status not in services.OPEN_FOR_MEMBER:
            raise serializers.ValidationError(
                gettext("Belege lassen sich nur bei Entwürfen und Rückfragen ergänzen.")
            )
        with drf_errors():
            services.add_file(claim, request.FILES.get("file"), request.user)
        if claim.status == S.QUESTION:
            services.log(claim, "file", request.user)
        return self.out(claim, status.HTTP_201_CREATED)


class FileView(MemberMixin, APIView):
    def get(self, request, access_id: int, pk: int, file_id: int):
        claim = self.get_claim(pk)
        row = get_object_or_404(ExpenseFile, claim=claim, pk=file_id)
        return file_response(row, request.query_params.get("download") == "1")

    @transaction.atomic
    def delete(self, request, access_id: int, pk: int, file_id: int):
        claim = self.get_claim(pk)
        row = get_object_or_404(ExpenseFile, claim=claim, pk=file_id)
        # Nach dem Einreichen bleiben Belege (nur ergänzen, nie löschen)
        if claim.status != S.DRAFT or claim.number:
            raise serializers.ValidationError(
                gettext("Nach dem Einreichen lassen sich Belege nur noch ergänzen.")
            )
        from core.files import delete_on_commit

        if row.file:
            delete_on_commit(row.file)
        row.delete()
        return self.out(claim)


def has_open(access) -> int:
    """Anträge mit Rückfrage (Hinweis im Mitgliederbereich und in der App)."""
    return ExpenseClaim.objects.filter(
        organization_id=access.organization_id,
        membership_id=access.membership_id,
        status=S.QUESTION,
    ).count()
