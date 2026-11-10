"""Rückmeldung per Link aus der Mail, ohne Anmeldung (T2).

Jede Mail zu einem Termin mit Zu- und Absagen bekommt je Empfänger einen eigenen
Link. Er gilt nur für diesen Termin und dieses Mitglied und öffnet eine Seite mit
dem Termin, den Anhängen und der Auswahl. Erst „Speichern“ (POST) ändert etwas: Das
bloße Öffnen (Virenscanner im Mailprogramm laden Links vorab) speichert nichts.
"""

from __future__ import annotations

import datetime
import logging

from django.core import signing
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import NotFound, Throttled
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from core import virenscan
from core.ratelimit import client_ip, too_many
from core.tenancy import rls_bypass
from members.models import Membership
from organizations.addresses import base_url
from organizations.imprint import ensure as ensure_imprint

from . import maps, notify, rsvp
from .models import MAX_GUESTS, Event, EventAttachment, EventResponse

logger = logging.getLogger(__name__)

SALT = "events.rsvp-link"
# Nach dem Termin bleibt die Seite noch so lange lesbar
GRACE = datetime.timedelta(days=14)
RATE = (60, 600)  # 60 Aufrufe je 10 Minuten und IP

# Anhänge direkt in der Mail (wie bei Rundschreiben); größere stehen auf der Seite
MAIL_FILES = 5
MAIL_FILE_SIZE = 10 * 1024 * 1024
MAIL_TOTAL_SIZE = 20 * 1024 * 1024


def token(event_id: int, membership_id: int) -> str:
    return signing.dumps({"e": event_id, "m": membership_id}, salt=SALT, compress=True)


def parse(value: str) -> tuple[int, int] | None:
    try:
        data = signing.loads(value, salt=SALT)
    except signing.BadSignature:
        return None
    if not isinstance(data, dict):
        return None
    e, m = data.get("e"), data.get("m")
    if not isinstance(e, int) or not isinstance(m, int):
        return None
    return e, m


def url(event: Event, membership_id: int) -> str:
    return f"{base_url(event.organization)}/rueckmeldung/{token(event.pk, membership_id)}"


def offers_link(event: Event) -> bool:
    """Lohnt ein Rückmeldelink in der Mail?"""
    return event.rsvp_enabled and not event.is_cancelled and not rsvp.deadline_passed(event)


def mail_attachments(event: Event) -> tuple[list[dict], list[str]]:
    """Anhänge des Termins für den Postausgang und die Namen der nicht mitgeschickten."""
    from core import virenscan

    chosen: list[dict] = []
    skipped: list[str] = []
    total = 0
    for att in event.attachments.all():
        too_big = att.size > MAIL_FILE_SIZE or total + att.size > MAIL_TOTAL_SIZE
        if len(chosen) >= MAIL_FILES or too_big:
            skipped.append(att.name)
            continue
        try:
            virenscan.release_ok(
                att.file, att.name, "Anhang eines Termins", key=f"termin-anhang:{att.pk}"
            )
        except Exception:  # Fund, Scanner fehlt: Datei nicht mitschicken
            logger.warning("Terminanhang %s nicht mitgeschickt", att.pk, exc_info=True)
            skipped.append(att.name)
            continue
        total += att.size
        chosen.append(
            {
                "name": att.name,
                "path": att.file.name,
                "size": att.size,
                "content_type": att.content_type or "application/octet-stream",
            }
        )
    return chosen, skipped


# --- Öffentliche Rückmeldeseite ---


class LinkResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=EventResponse.Status.choices)
    guests = serializers.IntegerField(min_value=0, max_value=MAX_GUESTS, default=0)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


def _no_store(response: Response) -> Response:
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


class _LinkBase(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def resolve(self, request, value: str, *, lock: bool = False) -> tuple[Event, Membership]:
        if too_many(f"rsvp-link:{client_ip(request)}", RATE[0], RATE[1]):
            raise Throttled(detail=gettext("Zu viele Aufrufe. Bitte später erneut."))
        ids = parse(value)
        invalid = gettext("Dieser Link ist ungültig oder abgelaufen.")
        if ids is None:
            raise NotFound(invalid)
        event_id, membership_id = ids
        with rls_bypass():
            if lock:
                Event.objects.select_for_update().filter(pk=event_id).values_list("pk").first()
            event = (
                Event.objects.select_related("organization", "department")
                .filter(pk=event_id)
                .first()
            )
            if (
                event is None
                or not event.rsvp_enabled
                or event.ends_at + GRACE < timezone.now()
                or not rsvp.is_invited(event, membership_id)
            ):
                raise NotFound(invalid)
            membership = Membership.objects.select_related("person", "organization").get(
                pk=membership_id
            )
        return event, membership

    def data(self, value: str, event: Event, membership: Membership) -> dict:
        with rls_bypass():
            mine = event.responses.filter(membership=membership).first()
            allowed, reason = rsvp.member_can_respond(event)
            s = rsvp.summary(event)
            attachments = [
                {
                    "id": a.pk,
                    "name": a.name,
                    "size": a.size,
                    "url": f"/api/public/rsvp/{value}/attachments/{a.pk}/",
                }
                for a in event.attachments.all()
            ]
            imprint_key = ensure_imprint(event.organization).public_key
        owner = event.department.name if event.department_id else event.organization.name
        return {
            "club": event.organization.name,
            "owner": owner,
            "imprint_key": imprint_key,
            "first_name": membership.person.first_name,
            "event": {
                "title": event.title,
                "starts_at": event.starts_at,
                "ends_at": event.ends_at,
                "all_day": event.all_day,
                "when": notify.when(event),
                "location": event.location,
                "address": event.address,
                "directions": event.directions,
                "map_links": maps.for_event(event),
                "description": event.description,
                "is_cancelled": event.is_cancelled,
                "cancel_note": event.cancel_note if event.is_cancelled else "",
            },
            "attachments": attachments,
            "rsvp": {
                "deadline": event.rsvp_deadline,
                "capacity": event.rsvp_capacity,
                "free": max(0, event.rsvp_capacity - s.persons) if event.rsvp_capacity else None,
                "guests_allowed": event.rsvp_guests,
                "max_guests": MAX_GUESTS,
                "maybe_allowed": event.rsvp_maybe,
                "note_allowed": event.rsvp_note,
                "note_question": event.rsvp_note_question if event.rsvp_note else "",
                "can_respond": allowed,
                "reason": gettext(reason) if reason else "",
                "mine": (
                    {"status": mine.status, "guests": mine.guests, "note": mine.note}
                    if mine
                    else None
                ),
            },
        }


class PublicRsvpView(_LinkBase):
    """GET: Termin und eigene Rückmeldung · POST: Rückmeldung speichern."""

    def get(self, request, token: str):
        event, membership = self.resolve(request, token)
        return _no_store(Response(self.data(token, event, membership)))

    @transaction.atomic
    def post(self, request, token: str):
        event, membership = self.resolve(request, token, lock=True)
        allowed, reason = rsvp.member_can_respond(event)
        if not allowed:
            fallback = gettext("Für diesen Termin gibt es keine Rückmeldung.")
            raise serializers.ValidationError(gettext(reason) if reason else fallback)
        data = LinkResponseSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        with rls_bypass():
            note = rsvp.check_options(event, v["status"], v["note"])
            response, before = rsvp.save_response(
                event,
                membership,
                status=v["status"],
                guests=v["guests"],
                note=note,
                source=EventResponse.Source.LINK,
                user=None,
            )
            record(
                event.organization,
                None,
                "update",
                event,
                {
                    f"Rückmeldung {membership.person} (Mail-Link)": [
                        rsvp.response_label(EventResponse(**before)) if before else None,
                        rsvp.response_label(response),
                    ]
                },
            )
        return _no_store(Response(self.data(token, event, membership)))


class PublicRsvpAttachmentView(_LinkBase):
    def get(self, request, token: str, att_id: int):
        event, _ = self.resolve(request, token)
        with rls_bypass():
            att = get_object_or_404(EventAttachment, event=event, pk=att_id)
            # Noch nicht geprüft oder Fund: gesperrt (Gesamtaudit 10.11., Fachfrage 2)
            virenscan.ensure_released(att.file)
            try:
                handle = att.file.open("rb")
            except FileNotFoundError as exc:
                raise Http404 from exc
        response = FileResponse(
            handle,
            content_type=att.content_type,
            as_attachment=request.query_params.get("download") == "1",
            filename=att.name,
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Robots-Tag"] = "noindex, nofollow"
        response["Referrer-Policy"] = "no-referrer"
        return response
