"""Auslagen über einen persönlichen Link einreichen, ohne Zugang (A6).

Die Kasse stellt den Link für eine Person aus (Helfer, Elternteil, Mitglied ohne Konto). Er
gilt höchstens 90 Tage, ist widerrufbar und zeigt nur die über ihn eingereichten Anträge.
Gespeichert wird nur die Prüfsumme des Geheimnisses.
"""

from __future__ import annotations

import datetime
import hashlib
import secrets

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from core.ratelimit import TooMany, client_ip, too_many
from core.tenancy import rls_bypass

from . import services
from .data import claim_data, drf_errors
from .models import ExpenseClaim, ExpenseLink
from .portal import form_data
from .views import ExpenseMixin

MAX_DAYS = 90
RATE = (60, 600)
UPLOAD_RATE = (20, 3600)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def link_url(org, token: str) -> str:
    from organizations.addresses import base_url

    return f"{base_url(org)}/auslage/{token}"


def link_data(link: ExpenseLink) -> dict:
    return {
        "id": link.pk,
        "name": link.name,
        "email": link.email,
        "membership": link.membership_id,
        "valid_until": link.valid_until,
        "revoked": bool(link.revoked_at),
        "used_at": link.used_at,
        "created_at": link.created_at,
    }


class LinksView(ExpenseMixin, APIView):
    """Kasse: Links ansehen, ausstellen (Adresse nur einmal in der Antwort), widerrufen."""

    def check(self):
        cfg = services.settings_for(self.org)
        if not cfg.links_enabled:
            raise serializers.ValidationError(
                gettext("Links für Personen ohne Zugang sind nicht eingeschaltet.")
            )

    def get(self, request, org_id: int):
        rows = ExpenseLink.objects.filter(organization=self.org).order_by("-created_at")[:200]
        return Response({"links": [link_data(r) for r in rows]})

    @transaction.atomic
    def post(self, request, org_id: int):
        from members.models import Membership

        self.check()
        name = " ".join(str(request.data.get("name") or "").split())[:200]
        if len(name) < 2:
            raise serializers.ValidationError({"name": gettext("Bitte den Namen angeben.")})
        try:
            days = int(request.data.get("days") or 30)
        except (TypeError, ValueError):
            days = 30
        days = max(1, min(MAX_DAYS, days))
        membership = None
        if request.data.get("membership") not in (None, ""):
            membership = Membership.objects.filter(
                organization=self.org, pk=request.data["membership"]
            ).first()
        token = secrets.token_urlsafe(24)
        link = ExpenseLink.objects.create(
            organization=self.org,
            name=name,
            email=" ".join(str(request.data.get("email") or "").split())[:254],
            membership=membership,
            token_hash=digest(token),
            valid_until=timezone.localdate() + datetime.timedelta(days=days),
            created_by=request.user,
        )
        record(self.org, request.user, "create", link, {"Auslagen-Link": [None, name]})
        return Response(
            {**link_data(link), "url": link_url(self.org, token)}, status=status.HTTP_201_CREATED
        )


class LinkDetailView(ExpenseMixin, APIView):
    def delete(self, request, org_id: int, pk: int):
        link = ExpenseLink.objects.filter(organization=self.org, pk=pk).first()
        if link is None:
            raise NotFound()
        if not link.revoked_at:
            link.revoked_at = timezone.now()
            link.save(update_fields=["revoked_at"])
            record(
                self.org,
                request.user,
                "update",
                link,
                {"Auslagen-Link widerrufen": [None, link.name]},
            )
        return Response(link_data(link))


def _no_store(response: Response) -> Response:
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


class PublicLinkView(APIView):
    """GET: Angaben zum Link und eigene Anträge · POST (mehrteilig): Auslage einreichen."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def resolve(self, request, token: str, *, lock: bool = False) -> ExpenseLink:
        key = f"expense-link:{client_ip(request)}"
        if too_many(key, RATE[0], RATE[1]):
            raise TooMany(key, "aufrufe")
        invalid = gettext("Dieser Link ist ungültig oder abgelaufen.")
        with rls_bypass():
            qs = ExpenseLink.objects.select_related("organization")
            if lock:
                qs = qs.select_for_update(of=("self",))
            link = qs.filter(token_hash=digest(token or "")).first()
            if (
                link is None
                or link.revoked_at
                or link.valid_until < timezone.localdate()
                or not services.enabled(link.organization)
                or not services.settings_for(link.organization).links_enabled
            ):
                raise NotFound(invalid)
        return link

    def data(self, link: ExpenseLink) -> dict:
        from organizations.imprint import ensure as ensure_imprint

        with rls_bypass():
            claims = ExpenseClaim.objects.filter(organization=link.organization, link=link)
            rows = [claim_data(c) for c in claims.prefetch_related("lines")]
            for row in rows:
                row.pop("payee", None)
            imprint_key = ensure_imprint(link.organization).public_key
            cfg = services.settings_for(link.organization)
        return {
            "club": link.organization.name,
            "imprint_key": imprint_key,
            "name": link.name,
            "valid_until": link.valid_until,
            "mileage_enabled": cfg.mileage_enabled,
            "km_rate": str(cfg.km_rate),
            "claims": rows,
        }

    def get(self, request, token: str):
        return _no_store(Response(self.data(self.resolve(request, token))))

    @transaction.atomic
    def post(self, request, token: str):
        link = self.resolve(request, token, lock=True)
        key = f"expense-link-upload:{link.pk}"
        if too_many(key, UPLOAD_RATE[0], UPLOAD_RATE[1]):
            raise TooMany(key, "versuche")
        data = form_data(request)
        data.pop("advance", None)
        data.pop("project", None)
        with rls_bypass(), drf_errors():
            org = link.organization
            claim = ExpenseClaim.objects.create(
                organization=org,
                source=ExpenseClaim.Source.LINK,
                membership=link.membership,
                name=link.name,
                email=link.email,
                link=link,
            )
            if data.get("kind") == ExpenseClaim.Kind.ADVANCE:
                data["kind"] = ExpenseClaim.Kind.EXPENSE
            services.apply_changes(claim, data)
            for upload in request.FILES.getlist("file"):
                services.add_file(claim, upload, None)
            services.log(claim, "created", None, gettext("über persönlichen Link"), who=link.name)
            services.submit(claim, None)
            link.used_at = timezone.now()
            link.save(update_fields=["used_at"])
        return _no_store(Response(self.data(link), status=status.HTTP_201_CREATED))
