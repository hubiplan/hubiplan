"""Öffentliche Schnittstelle der Anmeldung (Stufe A4), ohne Anmeldung im System.

- ``GET/POST public/registration/<key>/``: Formular mit Rechenaufgabe · abschicken
- ``POST public/registration/confirm/<token>/``: E-Mail-Adresse bestätigen, verbindlich anmelden
- ``GET public/registration/mine/<token>/``: eigene Anmeldung (Link aus der Mail)
- ``GET/POST public/registration/mine/<token>/cancel/``: Stornogebühr ansehen · abmelden
"""

from __future__ import annotations

from django.db import transaction
from django.http import Http404
from django.utils.translation import gettext, override
from rest_framework import serializers
from rest_framework.response import Response

from admission.public_views import _Public
from audit.log import record
from core.ratelimit import too_many, visitor_ip
from core.tenancy import unit_context
from website import contact as spam

from . import notify, public, services
from .models import Registration
from .views import _cancel_label, _quote, registration_data

# Zeilenschutz als zweite Linie (Gesamtaudit 19.11.2026, S-06): Die Ansichten suchen unter
# Umgehung, wer gemeint ist (Schlüssel, Link), und arbeiten dann mit ``unit_context`` streng im
# Bereich dieser Einheit. ``tenant_context`` behielte die Umgehung aus ``_Public.dispatch``.

IP_LIMIT = 10  # Anmeldungen je Stunde und IP
SITE_LIMIT = 120  # Anmeldungen je Stunde und Termin


def _setup(key: str):
    setup = public.setup_by_key(key)
    if setup is None:
        raise Http404
    return setup


class FormView(_Public):
    def get(self, request, key: str):
        setup = _setup(key)
        with override(self.language(request)), unit_context(setup.organization_id):
            data = public.schema(setup, request)
        data["challenge"] = spam.challenge(public.ChallengeKey(setup))
        data["key"] = setup.public_key
        return Response(data)

    def post(self, request, key: str):
        setup = _setup(key)
        language = self.language(request)
        ser = public.SubmitIn(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        if v.get("homepage"):
            return Response({"status": "ok"}, status=201)  # Honigtopf: still verwerfen
        try:
            salt = spam.check_challenge(
                public.ChallengeKey(setup), v.get("challenge", ""), v.get("nonce"), consume=False
            )
        except spam.Rejected as exc:
            return Response({"detail": exc.message, "code": exc.code}, status=exc.status)
        ip = visitor_ip(request)
        if too_many(f"registration:ip:{ip}", IP_LIMIT, 60 * 60) or too_many(
            f"registration:setup:{setup.pk}", SITE_LIMIT, 60 * 60
        ):
            return Response(
                {"detail": gettext("Zu viele Anmeldungen. Bitte später noch einmal versuchen.")},
                status=429,
            )
        data = public.stored(v)
        with override(language), unit_context(setup.organization_id):
            public.check(setup, data, v["privacy_accepted"])
        try:
            spam.consume_challenge(salt)
        except spam.Rejected as exc:
            return Response({"detail": exc.message, "code": exc.code}, status=exc.status)
        try:
            with transaction.atomic(), unit_context(setup.organization_id):
                token = public.submit(setup, data, language)
        except BaseException:
            spam.release_challenge(salt)
            raise
        transaction.on_commit(lambda: spam.finish_challenge(salt))
        pk = setup.pk
        transaction.on_commit(lambda: notify.confirm_email(pk, data, token, language))
        return Response({"status": "ok"}, status=201)


def mine_payload(reg: Registration) -> dict:
    setup = reg.setup
    event = setup.event
    with unit_context(reg.organization_id):
        offer = services.offer_data(setup)
        offer["prices"] = public.guest_prices(offer)
        data = registration_data(reg, full=False)
    # Ersatzperson nur über den Verein (ohne Mitgliederbereich keine Auswahl)
    data["can_substitute"] = False
    return {
        "organization": reg.organization.name,
        "event": {
            "title": event.title,
            "starts_at": event.starts_at,
            "ends_at": event.ends_at,
            "all_day": event.all_day,
            "location": event.location,
            "address": event.address,
        },
        "offer": offer,
        "registration": data,
        "cancel_text": public.cancel_text(setup),
    }


TICKET_IP_LIMIT = 60  # Kartenabrufe je 10 Minuten und Adresse


class ConfirmView(_Public):
    def post(self, request, token: str):
        pending = public.find_pending(token)
        if pending is None:
            raise Http404
        with override(pending.language), unit_context(pending.organization_id):
            reg = public.confirm(pending)
            record(
                reg.organization,
                None,
                "update",
                reg.setup.event,
                {f"Anmeldung {reg.display_number}": [None, "öffentlich angemeldet"]},
            )
        return Response({"token": public.link_token(reg), **mine_payload(reg)})


def _own(token: str) -> Registration:
    reg = public.find_by_link(token)
    if reg is None:
        raise Http404
    return reg


class MineView(_Public):
    def get(self, request, token: str):
        reg = _own(token)
        with override(self.language(request)):
            return Response(mine_payload(reg))


class MineTicketsView(_Public):
    """GET: Eintrittskarten über den Link „Anmeldung ansehen“ (A6)."""

    def get(self, request, token: str):
        from .views import tickets_response

        # Die Karten werden bei jedem Abruf neu gesetzt (PDF): je Adresse begrenzen
        if too_many(f"registration:karten:{visitor_ip(request)}", TICKET_IP_LIMIT, 10 * 60):
            return Response(
                {"detail": gettext("Zu viele Versuche. Bitte später noch einmal.")}, status=429
            )
        reg = _own(token)
        with override(self.language(request)), unit_context(reg.organization_id):
            return tickets_response(reg)


class CancelIn(serializers.Serializer):
    participants = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_null=True, default=None
    )


class MineCancelView(_Public):
    def get(self, request, token: str):
        reg = _own(token)
        with override(self.language(request)), unit_context(reg.organization_id):
            return Response(_quote(reg, request.query_params.get("participants")))

    def post(self, request, token: str):
        reg = _own(token)
        if too_many(f"registration:cancel:{reg.pk}", 20, 60 * 60):
            return Response(
                {"detail": gettext("Zu viele Versuche. Bitte später noch einmal.")}, status=429
            )
        ser = CancelIn(data=request.data)
        ser.is_valid(raise_exception=True)
        ids = ser.validated_data["participants"]
        with override(self.language(request)), unit_context(reg.organization_id):
            with transaction.atomic():
                label = _cancel_label(reg, ids)
                services.cancel(reg, by_member=True, participants=ids or None)
                record(
                    reg.organization,
                    None,
                    "update",
                    reg.setup.event,
                    {f"Anmeldung {reg.display_number}": [reg.name, label]},
                )
            reg = _own(token) if reg.access_nonce else reg
            return Response(mine_payload(reg))


# --- Scanpersonal mit Link (A6) ---

SCAN_LIMIT = 600  # Scans je Minute und Link (Bremse gegen Durchprobieren)
CASH_LIMIT = 60  # Barzahlungen je Minute und Link


def _scan_link(token: str):
    from . import scanning

    link = scanning.link_by_token(token)
    if link is None:
        raise Http404
    return link


class ScanIn(serializers.Serializer):
    code = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")
    # Verweis aus der Namenssuche (scanning.ref), keine fortlaufende Nummer
    participant = serializers.CharField(
        max_length=200, required=False, allow_null=True, allow_blank=True, default=None
    )


class ScanView(_Public):
    """``GET public/scan/<token>/``: Station und Termin · ``POST {code}``: Karte prüfen und
    abhaken bzw. Zusatzleistung einlösen."""

    def get(self, request, token: str):
        from . import scanning

        link = _scan_link(token)
        with override(self.language(request)), unit_context(link.organization_id):
            return Response(scanning.page_data(link))

    def post(self, request, token: str):
        from . import scanning

        link = _scan_link(token)
        if too_many(f"registration-scan:{link.pk}", SCAN_LIMIT, 60):
            return Response({"detail": gettext("Zu viele Scans. Bitte kurz warten.")}, status=429)
        ser = ScanIn(data=request.data)
        ser.is_valid(raise_exception=True)
        with (
            override(self.language(request)),
            unit_context(link.organization_id),
            transaction.atomic(),
        ):
            v = ser.validated_data
            return Response(scanning.scan(link, v["code"], participant=v["participant"]))


class ScanSearchView(_Public):
    """``GET public/scan/<token>/search/?q=``: Angemeldete zum Namen, nur wenn der Link die
    Namenssuche erlaubt (Einbuchen ohne Karte nach Ausweisabgleich)."""

    def get(self, request, token: str):
        from . import scanning

        link = _scan_link(token)
        if not link.allow_search:
            raise Http404
        if too_many(f"registration-scan-search:{link.pk}", 120, 60):
            return Response(
                {"detail": gettext("Zu viele Anfragen. Bitte kurz warten.")}, status=429
            )
        with unit_context(link.organization_id):
            hits = scanning.search(link, request.query_params.get("q", "")[:100])
        return Response({"results": hits})


class CashIn(serializers.Serializer):
    participant = serializers.CharField(max_length=200)
    request_key = serializers.UUIDField()
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, default=None
    )


class ScanCashView(_Public):
    """``POST public/scan/<token>/cash/ {participant, request_key, amount?}``: offene
    Teilnahmegebühr bar annehmen (nur Kassen-Links). Ein zweites Senden mit derselben
    ``request_key`` bucht nicht doppelt."""

    def post(self, request, token: str):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from billing.sending import _as_drf

        from . import scanning

        link = _scan_link(token)
        if not link.cash_account_id:
            raise Http404
        if too_many(f"registration-scan-cash:{link.pk}", CASH_LIMIT, 60):
            return Response(
                {"detail": gettext("Zu viele Anfragen. Bitte kurz warten.")}, status=429
            )
        ser = CashIn(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        with override(self.language(request)), unit_context(link.organization_id):
            try:
                with transaction.atomic():
                    return Response(
                        scanning.take_cash(link, v["participant"], v["request_key"], v["amount"])
                    )
            except DjangoValidationError as exc:
                raise _as_drf(exc) from exc
