"""Auslagen in der Verwaltung: Kasse des Vereins (``/api/orgs/<Verein>/expenses/…``) und
Leitung einer Untereinheit (``/api/depts/<Untereinheit>/expenses/…``, sachlich bestätigen).

Rechte: ``expenses.view`` (lesen), ``expenses.edit`` (prüfen, freigeben); Auszahlen braucht
zusätzlich ``finance.edit``. In Untereinheiten heißt ``expenses.edit`` „bestätigen“.
"""

from __future__ import annotations

import datetime

from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import FINANCE_EDIT
from audit.log import record
from changes import idempotency
from core.api_base import OrgScopedMixin
from organizations.models import Organization

from . import services
from .data import claim_data, drf_errors, settings_data
from .models import ExpenseClaim, ExpenseFile, ExpenseSettings

S = ExpenseClaim.Status

# Listen der Kasse
TABS = {
    "review": (S.SUBMITTED, S.CONFIRMED, S.QUESTION),
    "approved": (S.APPROVED,),
    "done": (S.PAID, S.REJECTED, S.WITHDRAWN, S.WAIVED),
}
LIST_LIMIT = 300


def claims_qs(org):
    return (
        ExpenseClaim.objects.filter(organization=org)
        .select_related(
            "organization",
            "membership__person",
            "department",
            "project",
            "advance",
            "booking",
        )
        .prefetch_related("lines__category", "files")
    )


def file_response(row: ExpenseFile, download: bool = False):
    from core.virenscan import ensure_released

    if not row.file:
        raise NotFound()
    ensure_released(row.file)
    xml = row.content_type == "application/xml"
    response = FileResponse(
        row.file.open("rb"),
        content_type=row.content_type,
        as_attachment=xml or download,
        filename=row.name,
    )
    response["Cache-Control"] = "private, max-age=600"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class ExpenseMixin(OrgScopedMixin):
    read_permission = services.VIEW
    write_permission = services.EDIT
    allowed_org_types = (Organization.Type.CLUB,)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not services.enabled(self.org):
            raise NotFound()

    @property
    def can_edit(self) -> bool:
        return services.EDIT in self.org_permissions

    @property
    def can_pay(self) -> bool:
        return self.can_edit and FINANCE_EDIT in self.org_permissions

    def get_claim(self, pk: int) -> ExpenseClaim:
        claim = claims_qs(self.org).filter(pk=pk).exclude(status=S.DRAFT, source="portal").first()
        if claim is None:
            raise NotFound()
        return claim

    def out(self, claim: ExpenseClaim, code=status.HTTP_200_OK) -> Response:
        claim = claims_qs(self.org).prefetch_related("events").get(pk=claim.pk)
        data = claim_data(claim, viewer=self.request.user, full=True, treasury=True)
        data["can_edit"] = self.can_edit
        data["can_pay"] = self.can_pay
        return Response(data, status=code)


class ListView(ExpenseMixin, APIView):
    """GET ?ansicht=review|approved|done|unreviewed · POST: von der Kasse für jemanden erfassen."""

    def get(self, request, org_id: int):
        tab = request.query_params.get("ansicht") or "review"
        qs = claims_qs(self.org)
        if tab == "unreviewed":
            qs = qs.filter(self_approved=True, reviewed_at__isnull=True)
        elif tab == "drafts":
            qs = qs.filter(status=S.DRAFT, source=ExpenseClaim.Source.TREASURY)
        elif tab in TABS:
            qs = qs.filter(status__in=TABS[tab])
        else:
            qs = qs.exclude(status=S.DRAFT)
        if (year := request.query_params.get("jahr")) and year.isdigit():
            qs = qs.filter(year=int(year))
        rows = [
            {
                **claim_data(c, viewer=request.user, treasury=True),
                "own": services.is_own(c, request.user),
            }
            for c in qs.order_by("-submitted_at", "-pk")[:LIST_LIMIT]
        ]
        counts = {
            "review": ExpenseClaim.objects.filter(
                organization=self.org, status__in=TABS["review"]
            ).count(),
            "approved": ExpenseClaim.objects.filter(
                organization=self.org, status=S.APPROVED
            ).count(),
            "unreviewed": ExpenseClaim.objects.filter(
                organization=self.org, self_approved=True, reviewed_at__isnull=True
            ).count(),
        }
        return Response(
            {
                "claims": rows,
                "counts": counts,
                "can_edit": self.can_edit,
                "can_pay": self.can_pay,
                "summary": services.liabilities(self.org),
            }
        )

    @transaction.atomic
    def post(self, request, org_id: int):
        from members.models import Membership

        key = idempotency.claim(request, f"expenses.treasury.{self.org.pk}")
        if key.done:
            return self.out(self.get_claim(key.result["id"]))
        data = request.data
        membership = None
        name = ""
        if data.get("membership") not in (None, ""):
            membership = (
                Membership.objects.filter(organization=self.org, pk=data["membership"])
                .select_related("person")
                .first()
            )
            if membership is None:
                raise serializers.ValidationError({"membership": gettext("Unbekanntes Mitglied.")})
        else:
            name = " ".join(str(data.get("name") or "").split())[:200]
            if len(name) < 2:
                raise serializers.ValidationError(
                    {"name": gettext("Bitte ein Mitglied wählen oder einen Namen angeben.")}
                )
        claim = ExpenseClaim.objects.create(
            organization=self.org,
            source=ExpenseClaim.Source.TREASURY,
            membership=membership,
            name=name,
            email=" ".join(str(data.get("email") or "").split())[:254],
            created_by=request.user,
        )
        with drf_errors():
            services.apply_changes(claim, data, treasury=True)
        services.log(claim, "created", request.user, gettext("von der Kasse erfasst"))
        key.remember({"id": claim.pk})
        return self.out(claim, status.HTTP_201_CREATED)


class DetailView(ExpenseMixin, APIView):
    """GET · PATCH: Kategorien der Positionen (Prüfung) oder Entwurf der Kasse ändern."""

    def get(self, request, org_id: int, pk: int):
        return self.out(self.get_claim(pk))

    @transaction.atomic
    def patch(self, request, org_id: int, pk: int):
        claim = self.get_claim(pk)
        claim = ExpenseClaim.objects.select_for_update().get(pk=claim.pk)
        version = request.data.get("version")
        if version not in (None, "") and str(version) != str(claim.version):
            raise serializers.ValidationError(
                gettext("Die Auslage wurde inzwischen geändert. Bitte neu laden.")
            )
        if claim.source == ExpenseClaim.Source.TREASURY and claim.status in (S.DRAFT, S.QUESTION):
            with drf_errors():
                services.apply_changes(claim, request.data, treasury=True)
        elif claim.status in (*services.IN_REVIEW, S.APPROVED, S.QUESTION):
            categories = request.data.get("categories") or {}
            if not isinstance(categories, dict):
                raise serializers.ValidationError({"categories": gettext("Ungültige Angabe.")})
            from finance.models import Category

            for line in claim.lines.all():
                value = categories.get(str(line.pk))
                if value in (None, ""):
                    continue
                cat = Category.objects.filter(organization=self.org, pk=value).first()
                if cat is None or not cat.allows("expense"):
                    raise serializers.ValidationError(
                        {"categories": gettext("Unbekannte Kategorie.")}
                    )
                line.category = cat
                line.save(update_fields=["category"])
            if "department" in request.data:
                with drf_errors():
                    claim.department = services._department(self.org, request.data["department"])
            if "project" in request.data:
                with drf_errors():
                    claim.project = services._project(self.org, request.data["project"])
            claim.version += 1
            claim.save()
        else:
            raise serializers.ValidationError(gettext("Diese Auslage lässt sich nicht ändern."))
        return self.out(claim)


class ActionView(ExpenseMixin, APIView):
    """POST <Auslage>/<Schritt>/: submit, ask, approve, reject, pay, waive."""

    def post(self, request, org_id: int, pk: int, action: str):
        claim = self.get_claim(pk)
        user = request.user
        data = request.data
        version = data.get("version")
        with drf_errors(), transaction.atomic():
            if action == "submit":
                if claim.source != ExpenseClaim.Source.TREASURY:
                    raise PermissionDenied()
                claim = services.submit(claim, user, treasury=True)
            elif action == "ask":
                claim = services.ask(claim, user, data.get("text"), version)
            elif action == "approve":
                claim = services.approve(
                    claim,
                    user,
                    amount=data.get("amount"),
                    reason=data.get("reason") or "",
                    version=version,
                )
            elif action == "reject":
                claim = services.reject(claim, user, data.get("reason"), version)
            elif action == "pay":
                if not self.can_pay:
                    raise PermissionDenied(
                        gettext("Zum Auszahlen fehlt das Recht, die Kasse zu führen.")
                    )
                from finance.models import Account

                key = idempotency.claim(request, f"expenses.pay.{self.org.pk}.{pk}", required=True)
                if key.done:
                    return self.out(claim)
                account = Account.objects.filter(
                    organization=self.org, pk=data.get("account"), is_active=True
                ).first()
                day = data.get("date")
                if day:
                    try:
                        day = datetime.date.fromisoformat(str(day))
                    except ValueError as exc:
                        raise serializers.ValidationError(
                            {"date": gettext("Bitte ein gültiges Datum angeben.")}
                        ) from exc
                claim = services.pay(
                    claim,
                    user,
                    account=account,
                    date=day or None,
                    categories=data.get("categories") or {},
                    version=version,
                )
                key.remember({"id": claim.pk})
            else:
                raise NotFound()
        return self.out(claim)


class ReviewView(ExpenseMixin, APIView):
    """POST {ids}: selbst freigegebene Auslagen nachträglich sichten (zweite Person)."""

    def post(self, request, org_id: int):
        ids = [int(i) for i in request.data.get("ids") or [] if str(i).isdigit()]
        claims = list(
            ExpenseClaim.objects.filter(organization=self.org, pk__in=ids, self_approved=True)
        )
        with drf_errors():
            done = services.review(claims, request.user)
        if claims and not done:
            raise serializers.ValidationError(
                gettext("Eigene Auslagen sichtet bitte eine andere Person.")
            )
        return Response({"reviewed": done})


class FilesView(ExpenseMixin, APIView):
    """POST: Beleg ergänzen (Entwürfe und Rückfragen der Kasse)."""

    virus_quarantine = True

    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        claim = self.get_claim(pk)
        if claim.source != ExpenseClaim.Source.TREASURY or claim.status not in (
            S.DRAFT,
            S.QUESTION,
        ):
            raise serializers.ValidationError(
                gettext("Belege ergänzt das Mitglied über eine Rückfrage.")
            )
        with drf_errors():
            services.add_file(claim, request.FILES.get("file"), request.user)
        services.log(claim, "file", request.user)
        return self.out(claim, status.HTTP_201_CREATED)


class FileView(ExpenseMixin, APIView):
    def get(self, request, org_id: int, pk: int, file_id: int):
        claim = self.get_claim(pk)
        row = get_object_or_404(ExpenseFile, claim=claim, pk=file_id)
        return file_response(row, request.query_params.get("download") == "1")


class SettingsView(ExpenseMixin, APIView):
    """Einstellungen des Moduls; ändern mit ``expenses.edit`` und ``finance.edit``."""

    def get(self, request, org_id: int):
        from organizations.models import Department

        cfg = services.settings_for(self.org)
        return Response(
            {
                **settings_data(cfg),
                "can_edit": self.can_pay,
                "donations_enabled": "donations" in (self.org.enabled_modules or []),
                "departments": [
                    {"id": d.pk, "name": d.name}
                    for d in Department.objects.filter(organization=self.org, is_active=True)
                ],
            }
        )

    @transaction.atomic
    def patch(self, request, org_id: int):
        if not self.can_pay:
            raise PermissionDenied()
        cfg = services.settings_for(self.org, lock=True)
        before = settings_data(cfg)
        data = request.data
        with drf_errors():
            if "submitters" in data:
                if data["submitters"] not in ExpenseSettings.Submitters.values:
                    raise serializers.ValidationError({"submitters": gettext("Ungültig.")})
                cfg.submitters = data["submitters"]
            for field in ("self_limit", "km_rate"):
                if field in data:
                    value = services.money(data[field])
                    if value < 0 or value > services.MAX_AMOUNT:
                        raise serializers.ValidationError({field: gettext("Ungültiger Betrag.")})
                    setattr(cfg, field, value)
            if "second_from" in data:
                value = data["second_from"]
                cfg.second_from = None if value in (None, "") else services.money(value)
                if cfg.second_from is not None and cfg.second_from <= 0:
                    raise serializers.ValidationError(
                        {"second_from": gettext("Ungültiger Betrag.")}
                    )
            if "hint_months" in data:
                try:
                    months = int(data["hint_months"])
                except (TypeError, ValueError) as exc:
                    raise serializers.ValidationError(
                        {"hint_months": gettext("Ungültig.")}
                    ) from exc
                if not 0 <= months <= 36:
                    raise serializers.ValidationError({"hint_months": gettext("0 bis 36 Monate.")})
                cfg.hint_months = months
            if "confirm_departments" in data:
                from organizations.models import Department

                ids = [int(i) for i in data["confirm_departments"] or [] if str(i).isdigit()]
                valid = set(
                    Department.objects.filter(organization=self.org, pk__in=ids).values_list(
                        "pk", flat=True
                    )
                )
                cfg.confirm_departments = sorted(valid)
            for field in ("mileage_enabled", "advances_enabled", "links_enabled"):
                if field in data:
                    setattr(cfg, field, bool(data[field]))
            if "waiver_basis" in data:
                cfg.waiver_basis = " ".join(str(data["waiver_basis"] or "").split())[:300]
            if "waiver_basis_date" in data:
                cfg.waiver_basis_date = services._date(
                    data["waiver_basis_date"], "waiver_basis_date"
                )
                if cfg.waiver_basis_date and cfg.waiver_basis_date > timezone.localdate():
                    raise serializers.ValidationError(
                        {"waiver_basis_date": gettext("Das Datum liegt in der Zukunft.")}
                    )
            if bool(cfg.waiver_basis) != bool(cfg.waiver_basis_date):
                raise serializers.ValidationError(
                    {
                        "waiver_basis": gettext(
                            "Für Spenden statt Erstattung bitte Grundlage und Datum angeben."
                        )
                    }
                )
        cfg.save()
        after = settings_data(cfg)
        changes = {k: [str(before[k]), str(after[k])] for k in after if before[k] != after[k]}
        if changes:
            record(self.org, request.user, "update", cfg, changes)
        return self.get(request, org_id)


class OptionsView(ExpenseMixin, APIView):
    """Auswahllisten: Mitglieder (für „für jemanden erfassen“), Kategorien, Konten."""

    def get(self, request, org_id: int):
        from finance.models import Account, Category

        return Response(
            {
                "categories": [
                    {"id": c.pk, "name": c.name}
                    for c in Category.objects.filter(
                        organization=self.org, is_active=True, kind__in=("expense", "both")
                    ).order_by("name")
                ],
                "accounts": [
                    {"id": a.pk, "name": a.name, "kind": a.kind}
                    for a in Account.objects.filter(organization=self.org, is_active=True)
                ],
            }
        )


# --- Untereinheit: sachlich bestätigen (A4) ---


class DeptMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        from portal.services import department_contexts

        ctx = department_contexts(request.user).get(int(kwargs["dept_id"]))
        if ctx is None:
            raise NotFound()
        if not services.enabled(ctx.club) or services.VIEW not in ctx.permissions:
            raise NotFound()
        if (
            request.method not in ("GET", "HEAD", "OPTIONS")
            and services.EDIT not in ctx.permissions
        ):
            raise PermissionDenied(gettext("Dafür fehlt dir die Berechtigung."))
        from core.tenancy import scope_of, set_rls

        self.ctx = ctx
        self.org = ctx.club
        self.dept = ctx.department
        set_rls(self.org.pk, request.user.pk, scope_id=scope_of(self.org.pk))
        from organizations.tree import UnitTree

        self.dept_ids = set(UnitTree.of(self.org.pk).subtree(self.dept.pk))

    def visible(self):
        return claims_qs(self.org).filter(department_id__in=self.dept_ids).exclude(status=S.DRAFT)

    def get_claim(self, pk: int) -> ExpenseClaim:
        claim = self.visible().filter(pk=pk).first()
        if claim is None:
            raise NotFound()
        return claim

    def out(self, claim):
        claim = claims_qs(self.org).prefetch_related("events").get(pk=claim.pk)
        data = claim_data(claim, viewer=self.request.user, full=True)
        unit = services.confirm_unit(claim)
        data["needs_confirm"] = services.needs_confirm(claim)
        data["confirm_unit"] = unit.name if unit else ""
        data["can_confirm"] = (
            services.EDIT in self.ctx.permissions
            and claim.status == S.SUBMITTED
            and unit is not None
            and unit.pk in self.dept_ids
            and not services.is_own(claim, self.request.user)
        )
        data["own"] = services.is_own(claim, self.request.user)
        return Response(data)


class DeptListView(DeptMixin, APIView):
    def get(self, request, dept_id: int):
        rows = []
        waiting = 0
        for claim in self.visible().order_by("-submitted_at", "-pk")[:LIST_LIMIT]:
            row = claim_data(claim)
            unit = services.confirm_unit(claim)
            row["needs_confirm"] = (
                claim.status == S.SUBMITTED and unit is not None and unit.pk in self.dept_ids
            )
            waiting += int(row["needs_confirm"])
            rows.append(row)
        return Response(
            {
                "claims": rows,
                "waiting": waiting,
                "can_confirm": services.EDIT in self.ctx.permissions,
            }
        )


class DeptDetailView(DeptMixin, APIView):
    def get(self, request, dept_id: int, pk: int):
        return self.out(self.get_claim(pk))


class DeptActionView(DeptMixin, APIView):
    def post(self, request, dept_id: int, pk: int, action: str):
        claim = self.get_claim(pk)
        with drf_errors(), transaction.atomic():
            if action == "confirm":
                claim = services.confirm(
                    claim, request.user, self.dept_ids, request.data.get("version")
                )
            elif action == "ask":
                unit = services.confirm_unit(claim)
                if unit is None or unit.pk not in self.dept_ids:
                    raise PermissionDenied()
                claim = services.ask(
                    claim, request.user, request.data.get("text"), request.data.get("version")
                )
            else:
                raise NotFound()
        return self.out(claim)


class DeptFileView(DeptMixin, APIView):
    def get(self, request, dept_id: int, pk: int, file_id: int):
        claim = self.get_claim(pk)
        row = get_object_or_404(ExpenseFile, claim=claim, pk=file_id)
        return file_response(row, request.query_params.get("download") == "1")


def review_tasks(org, perms: set[str]) -> list[dict]:
    """Offene Aufgaben für die Startseite und die Finanzen-Übersicht."""
    if services.EDIT not in perms or not services.enabled(org):
        return []
    items = []
    review = (
        ExpenseClaim.objects.filter(organization=org, status__in=(S.SUBMITTED, S.CONFIRMED))
        .select_related("membership__person", "department")
        .prefetch_related("lines")
        .order_by("submitted_at")[:20]
    )
    for claim in review:
        if services.needs_confirm(claim):
            continue
        items.append(
            {
                "kind": "expense",
                "kind_label": gettext("Auslage prüfen"),
                "title": services.person_name(claim),
                "detail": (
                    f"{claim.number} · {services.comma(claim.total)} € · {claim.purpose[:60]}"
                ),
                "created_at": claim.submitted_at,
                "link": f"/finanzen/auslagen/{claim.pk}",
                "ref": claim.pk,
            }
        )
    approved = ExpenseClaim.objects.filter(organization=org, status=S.APPROVED).count()
    if approved and FINANCE_EDIT in perms:
        items.append(
            {
                "kind": "expense_pay",
                "kind_label": gettext("Auslagen auszahlen"),
                "title": gettext("{n} freigegeben").format(n=approved),
                "detail": gettext("Freigegebene Auslagen warten auf die Auszahlung"),
                "created_at": timezone.now(),
                "link": "/finanzen/auslagen?ansicht=approved",
            }
        )
    unreviewed = ExpenseClaim.objects.filter(
        Q(organization=org, self_approved=True, reviewed_at__isnull=True)
    ).count()
    if unreviewed:
        items.append(
            {
                "kind": "expense_review",
                "kind_label": gettext("Auslagen sichten"),
                "title": gettext("{n} selbst freigegeben").format(n=unreviewed),
                "detail": gettext("Eigene Auslagen der Kasse nachträglich sichten"),
                "created_at": timezone.now(),
                "link": "/finanzen/auslagen?ansicht=unreviewed",
            }
        )
    return items
