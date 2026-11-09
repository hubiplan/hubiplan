"""Live-Vorgabe: Dirigent oder Stabführer schickt allen Geräten das nächste Stück.

Die App fragt, solange das Notenpult offen ist, alle paar Sekunden nach (``GET``). Die
Vorgabe liegt nur im Cache (bis Tagesende, höchstens 12 Stunden), nicht in der Datenbank:
Sie ist ein Zuruf, kein Vereinsdatum.
"""

from __future__ import annotations

import re
import time

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from access.permissions import permissions_in
from core.api_base import AuditMixin, OrgScopedMixin
from core.tenancy import tenant_context
from portal.views import _portal_access

from .models import Arrangement, MusicLeader
from .practice_portal import own_musician, visible_folders
from .views import ScopedSerializer

TARGET = re.compile(r"^(folder|performance|rehearsal)-(\d{1,12})$")
MAX_SECONDS = 12 * 3600
MIN_GAP = 1.0  # Sekunden zwischen zwei Vorgaben derselben Mappe


def _cache_key(org_id: int, target: str) -> str:
    return f"noten-live:{org_id}:{target}"


def _seconds_left() -> int:
    now = timezone.localtime()
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return max(60, min(MAX_SECONDS, int((end - now).total_seconds())))


def display(musician) -> str:
    if musician.membership_id:
        person = getattr(musician.membership, "person", None)
        if person is not None and person.display_name:
            return person.display_name
    return musician.name or gettext("Leitung")


def target_of(access, musician, target: str):
    """(Art, ID), wenn der Musiker diese Mappe bzw. diesen Termin sehen darf."""
    match = TARGET.match(target or "")
    if not match:
        raise NotFound()
    kind, pk = match.group(1), int(match.group(2))
    if kind == "folder":
        ok = visible_folders(access, musician).filter(pk=pk).exists()
    elif kind == "performance":
        ok = musician.assignment_set.exclude(status="declined").filter(performance_id=pk).exists()
    else:
        ok = musician.rehearsalinvitation_set.filter(active=True, rehearsal_id=pk).exists()
    if not ok:
        raise NotFound()
    return kind, pk


def can_lead(user, access, musician, kind: str, pk: int) -> bool:
    if "music.edit" in permissions_in(user, access.organization):
        return True
    return MusicLeader.objects.filter(musician=musician, **{f"{kind}_id": pk}).exists()


def leading(user, access, musician) -> set[str]:
    """Alle Ziele, für die dieses Konto Stücke vorgeben darf (für die Mappenliste)."""
    rows = MusicLeader.objects.filter(musician=musician)
    out = set()
    for r in rows:
        if r.folder_id:
            out.add(f"folder-{r.folder_id}")
        elif r.performance_id:
            out.add(f"performance-{r.performance_id}")
        elif r.rehearsal_id:
            out.add(f"rehearsal-{r.rehearsal_id}")
    return out


class OwnLive(APIView):
    def get(self, request, access_id, target):
        access = _portal_access(request.user, access_id)
        with tenant_context(access.organization_id, request.user.pk):
            musician = own_musician(access)
            if not musician:
                raise NotFound()
            kind, pk = target_of(access, musician, target)
            return Response(
                {
                    "cue": cache.get(_cache_key(access.organization_id, target)),
                    "can_send": can_lead(request.user, access, musician, kind, pk),
                    "poll_seconds": 2,
                }
            )

    def post(self, request, access_id, target):
        access = _portal_access(request.user, access_id)
        with tenant_context(access.organization_id, request.user.pk):
            musician = own_musician(access)
            if not musician:
                raise NotFound()
            kind, pk = target_of(access, musician, target)
            if not can_lead(request.user, access, musician, kind, pk):
                raise PermissionDenied()
            arrangement_id = serializers.IntegerField(min_value=1).run_validation(
                request.data.get("arrangement")
            )
            number = serializers.CharField(
                max_length=20, required=False, allow_blank=True
            ).run_validation(request.data.get("number", ""))
            arrangement = (
                Arrangement.objects.filter(
                    organization=access.organization, pk=arrangement_id, active=True
                )
                .select_related("piece")
                .first()
            )
            if arrangement is None:
                raise serializers.ValidationError(
                    {"arrangement": gettext("Dieses Stück gibt es nicht.")}
                )
            key = _cache_key(access.organization_id, target)
            previous = cache.get(key)
            now = time.time()
            if previous and now - previous["seq"] / 1000 < MIN_GAP:
                raise serializers.ValidationError(gettext("Bitte einen Moment warten."))
            cue = {
                "seq": int(now * 1000),
                "arrangement": arrangement.pk,
                "number": number.strip(),
                "title": arrangement.piece.title,
                "sender": display(musician),
                "sent_at": timezone.now().isoformat(),
            }
            cache.set(key, cue, _seconds_left())
            return Response({"cue": cue})


# --- Verwaltung: wer leitet ---


class MusicLeaderSerializer(ScopedSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = MusicLeader
        fields = ["id", "musician", "folder", "performance", "rehearsal", "name"]

    def get_name(self, row) -> str:
        return display(row.musician)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        targets = [k for k in ("folder", "performance", "rehearsal") if attrs.get(k)]
        if len(targets) != 1:
            raise serializers.ValidationError(
                gettext("Bitte genau eine Mappe, einen Auftritt oder eine Probe angeben.")
            )
        if MusicLeader.objects.filter(
            musician=attrs["musician"], **{targets[0]: attrs[targets[0]]}
        ).exists():
            raise serializers.ValidationError(gettext("Diese Leitung ist schon eingetragen."))
        return attrs


class MusicLeaderViewSet(OrgScopedMixin, AuditMixin, viewsets.ModelViewSet):
    serializer_class = MusicLeaderSerializer
    read_permission = ("music.view", "scores.view")
    write_permission = ("music.edit", "scores.edit")
    allowed_org_types = ("club", "federation")
    pagination_class = None
    http_method_names = ["get", "post", "delete", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if "music" not in self.org.enabled_modules:
            raise NotFound()

    def get_queryset(self):
        qs = MusicLeader.objects.filter(organization=self.org).select_related(
            "musician__membership__person"
        )
        params = self.request.query_params
        for key in ("folder", "performance", "rehearsal"):
            if params.get(key, "").isdigit():
                qs = qs.filter(Q(**{f"{key}_id": int(params[key])}))
        return qs.order_by("pk")

    def get_create_kwargs(self):
        return {"organization": self.org}
