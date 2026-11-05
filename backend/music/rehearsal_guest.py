"""One revocable guest invitation for one original rehearsal occurrence."""

import datetime
import hashlib
import hmac
import re
import uuid

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from changes import idempotency
from core.tenancy import rls_bypass, tenant_context
from organizations.imprint import ensure as ensure_imprint

from . import guest_scores
from .availability import Availability, interval
from .guest import GuestAccessView, GuestThrottle, NoStore, token_hash
from .models import Musician, RehearsalGuestAccess, RehearsalInvitation
from .practice import occurrence, save_response, visible_events
from .practice_programs import program_for, with_programs


def token(access):
    for key in [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]:
        value = (
            f"music-rehearsal-guest-v1:{access.organization_id}:{access.invitation_id}:"
            f"{access.original_start.isoformat()}:{access.nonce}"
        )
        candidate = hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()
        if not access.token_hash or hmac.compare_digest(token_hash(candidate), access.token_hash):
            return candidate
    raise NotFound()


def active(access):
    row = access.invitation
    return (
        not access.revoked_at
        and access.expires_at > timezone.now()
        and row.active
        and row.musician.active
        and not row.musician.membership_id
        and {"music", "events"} <= set(row.organization.enabled_modules)
    )


def metadata(view, row, access):
    valid = bool(access and active(access))
    return {
        "active": valid,
        "has_email": False,
        "expires_at": access.expires_at if access else None,
        "url": f"{settings.FRONTEND_URL.rstrip('/')}/musik-gast#probe-{token(access)}"
        if valid
        else "",
        "scores": guest_scores.choices(view, access) if access else [],
    }


class RehearsalGuestAccessView(GuestAccessView):
    def row(self, pk, lock=False):
        if not {"music", "events"} <= set(self.org.enabled_modules):
            raise NotFound()
        rows = RehearsalInvitation.objects.select_related(
            "rehearsal__event", "musician", "organization"
        )
        if lock:
            rows = rows.select_for_update(of=("self",))
        row = get_object_or_404(
            rows,
            organization=self.org,
            pk=pk,
            active=True,
            rehearsal__event__in=visible_events(self),
            musician__membership=None,
        )
        if lock:
            Musician.objects.select_for_update().get(pk=row.musician_id)
        return row

    def original(self, request):
        raw = (
            request.query_params.get("original_start")
            if request.method == "GET"
            else request.data.get("original_start")
        )
        return serializers.DateTimeField().run_validation(raw).astimezone(datetime.UTC)

    def get(self, request, org_id, pk):
        row = self.row(pk)
        access = RehearsalGuestAccess.objects.filter(
            invitation=row, original_start=self.original(request)
        ).first()
        return Response(metadata(self, row, access))

    @transaction.atomic
    def post(self, request, org_id, pk):
        row = self.row(pk, lock=True)
        original = self.original(request)
        action = serializers.ChoiceField(
            choices=["create", "rotate", "revoke", "share"]
        ).run_validation(request.data.get("action"))
        key = idempotency.claim(
            request,
            "music.rg."
            + hashlib.sha256(f"{self.org.pk}:{pk}:{original.isoformat()}".encode()).hexdigest()[
                :40
            ],
            required=True,
        )
        access = RehearsalGuestAccess.objects.filter(
            invitation=row, original_start=original
        ).first()
        if key.done:
            return Response(metadata(self, row, access))
        if action == "revoke":
            if access:
                access.revoked_at = timezone.now()
                access.save(update_fields=["revoked_at"])
        elif action == "share":
            if not access or not active(access):
                raise NotFound()
            guest_scores.save(self, access, request.data.get("scores"))
        else:
            o = occurrence(row.rehearsal.event, original)
            if not o or o.is_cancelled or o.ends_at <= timezone.now() or not row.musician.active:
                raise serializers.ValidationError(
                    gettext("Für diesen Gast kann kein Zugang erstellt werden.")
                )
            if not access:
                access = RehearsalGuestAccess(
                    organization=self.org,
                    invitation=row,
                    original_start=original,
                    created_by=request.user,
                )
            if not access.pk or action == "rotate" or not active(access):
                access.nonce = uuid.uuid4()
                access.token_hash = ""
                access.token_hash = token_hash(token(access))
                access.revoked_at = None
                access.score_shares = []
                access.expires_at = min(
                    timezone.now() + datetime.timedelta(days=180),
                    o.ends_at + datetime.timedelta(days=7),
                )
            access.save()
        key.remember({"access": access.pk if access else None})
        record(self.org, request.user, "update", row, {"Proben-Gastzugang": [None, action]})
        return Response(metadata(self, row, access))


class GuestRehearsalView(NoStore, APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [GuestThrottle]

    def access_id(self, request):
        auth = request.headers.get("Authorization", "")
        value = auth.removeprefix("Bearer ")
        if not auth.startswith("Bearer ") or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise NotFound()
        with rls_bypass():
            row = (
                RehearsalGuestAccess.objects.filter(token_hash=token_hash(value))
                .values_list("pk", "organization_id")
                .first()
            )
        if not row:
            raise NotFound()
        return row, value

    def access(self, pk, value):
        access = get_object_or_404(
            RehearsalGuestAccess.objects.select_related(
                "invitation__musician", "invitation__organization", "invitation__rehearsal__event"
            ),
            pk=pk,
        )
        if not active(access) or not hmac.compare_digest(access.token_hash, token_hash(value)):
            raise NotFound()
        return access

    def get(self, request):
        (pk, org), value = self.access_id(request)
        with tenant_context(org):
            access = self.access(pk, value)
            row = access.invitation
            rehearsal = with_programs(type(row.rehearsal).objects.filter(pk=row.rehearsal_id)).get()
            o = occurrence(rehearsal.event, access.original_start)
            if not o:
                raise NotFound()
            if "score" in request.query_params:
                return guest_scores.download(
                    request,
                    access,
                    serializers.IntegerField(min_value=1).run_validation(
                        request.query_params["score"]
                    ),
                )
            response = row.responses.filter(original_start=access.original_start).first()
            program = program_for(rehearsal, access.original_start)
            return Response(
                {
                    "kind": "rehearsal",
                    "title": rehearsal.event.title,
                    "organization": row.organization.name,
                    "imprint_key": ensure_imprint(row.organization).public_key,
                    "starts_at": o.starts_at,
                    "ends_at": o.ends_at,
                    "location": rehearsal.event.location,
                    "status": response.status if response else "pending",
                    "cancelled": o.is_cancelled,
                    "can_respond": not o.is_cancelled and o.starts_at > timezone.now(),
                    "availability": Availability(
                        row.organization,
                        [row.musician],
                        rehearsal.event,
                        *interval(rehearsal.event, o.starts_at, o.ends_at),
                    ).reasons(row.musician),
                    "notes": program["focus"],
                    "instrument": "",
                    "register": "",
                    "formation": "",
                    "program": [
                        {"title": item["title"], "kind": "piece", "duration_seconds": 0}
                        for item in program["items"]
                    ],
                    "scores": guest_scores.descriptions(access),
                }
            )

    @transaction.atomic
    def post(self, request):
        (pk, org), value = self.access_id(request)
        with tenant_context(org):
            access = self.access(pk, value)
            row = RehearsalInvitation.objects.select_for_update().get(pk=access.invitation_id)
            Musician.objects.select_for_update().get(pk=row.musician_id)
            access = self.access(pk, value)
            save_response(
                row,
                {"original_start": access.original_start, "status": request.data.get("status")},
                None,
            )
            return Response({"ok": True})
