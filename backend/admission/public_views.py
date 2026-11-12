"""Öffentliche Schnittstelle des Online-Antrags (ohne Anmeldung).

- ``GET/POST public/join/<key>/``: Aufbau mit Rechenaufgabe · Antrag einreichen
- ``GET public/join/application/<token>/``: Stand des eigenen Antrags
- ``POST …/confirm/``, ``…/withdraw/``, ``…/sign/``, ``GET …/pdf/``
- ``GET/POST public/join/kiosk/<token>/``: Stand-Modus ohne E-Mail-Bestätigung (B5)
"""

from __future__ import annotations

from django.db import transaction
from django.http import Http404, HttpResponse
from django.utils.translation import gettext, override
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.i18n import normalize
from core.ratelimit import too_many, visitor_ip
from core.tenancy import rls_bypass, tenant_context
from website import contact as spam

from . import public, services
from .models import Application, ApplicationForm

IP_LIMIT = 5  # Anträge je Stunde und IP
SITE_LIMIT = 60  # Anträge je Stunde und Verein


class _Public(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def dispatch(self, request, *args, **kwargs):
        with rls_bypass():
            return super().dispatch(request, *args, **kwargs)

    def options(self, request, *args, **kwargs):
        response = Response(status=204)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type"
        response["Access-Control-Max-Age"] = "600"
        return response

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["Access-Control-Allow-Origin"] = "*"
        response["X-Robots-Tag"] = "noindex"
        return response

    def language(self, request) -> str:
        return normalize(request.query_params.get("lang") or request.data.get("language"))


def active_form(key: str) -> ApplicationForm:
    form = (
        ApplicationForm.objects.select_related("organization").filter(public_key=key).first()
        if key and len(key) <= 40
        else None
    )
    if form is None or not form.enabled or not form.organization.is_active:
        raise Http404
    if not form.organization.keeps_members:
        raise Http404
    return form


def form_payload(form: ApplicationForm, request, language: str) -> dict:
    with override(language):
        data = public.schema(form, language, request, request.query_params.get("einheit", ""))
    data["challenge"] = spam.challenge(public.ChallengeKey(form))
    data["key"] = form.public_key
    return data


class FormView(_Public):
    def get(self, request, key: str):
        form = active_form(key)
        return Response(form_payload(form, request, self.language(request)))

    def post(self, request, key: str):
        form = active_form(key)
        language = self.language(request)
        ser = public.SubmitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        if v.get("homepage"):
            return Response({"status": "ok"}, status=201)  # Honigtopf: still verwerfen
        try:
            salt = spam.check_challenge(
                public.ChallengeKey(form), v.get("challenge", ""), v.get("nonce"), consume=False
            )
        except spam.Rejected as exc:
            return Response({"detail": exc.message, "code": exc.code}, status=exc.status)
        ip = visitor_ip(request)
        if too_many(f"join:ip:{ip}", IP_LIMIT, 60 * 60) or too_many(
            f"join:org:{form.organization_id}", SITE_LIMIT, 60 * 60
        ):
            return Response(
                {"detail": gettext("Zu viele Anträge. Bitte später noch einmal versuchen.")},
                status=429,
            )
        with override(language):
            clean = public.clean_submission(form, v)
        try:
            spam.consume_challenge(salt)
        except spam.Rejected as exc:
            return Response({"detail": exc.message, "code": exc.code}, status=exc.status)
        try:
            with transaction.atomic(), tenant_context(form.organization_id):
                services.create(form, clean)
        except BaseException:
            spam.release_challenge(salt)
            raise
        transaction.on_commit(lambda: spam.finish_challenge(salt))
        return Response({"status": "ok"}, status=201)


def own_application(token: str) -> Application:
    app = services.find(token)
    if app is None:
        raise Http404
    return app


def status_payload(app: Application, token: str) -> dict:
    form = services.form_for(app.organization)
    with override(app.language):
        return {
            "number": app.number,
            "status": app.status,
            "status_label": str(Application.Status(app.status).label),
            "organization": app.organization.name,
            "name": app.display_name,
            "language": app.language,
            "summary": services.summary_lines(app),
            "signed": bool(app.signature),
            "signature_required": form.signature == ApplicationForm.Signature.REQUIRED,
            "can_withdraw": app.status not in Application.DONE_STATES,
            "can_sign": app.status in ("unconfirmed", "unsigned"),
        }


class ApplicationStatusView(_Public):
    def get(self, request, token: str):
        app = own_application(token)
        return Response(status_payload(app, token))


class ConfirmView(_Public):
    def post(self, request, token: str):
        app = own_application(token)
        with tenant_context(app.organization_id):
            services.confirm(app, token)
        return Response(status_payload(app, token))


class WithdrawView(_Public):
    def post(self, request, token: str):
        app = own_application(token)
        with tenant_context(app.organization_id):
            services.withdraw(app)
        return Response(status_payload(app, token))


class SignView(_Public):
    def post(self, request, token: str):
        app = own_application(token)
        with tenant_context(app.organization_id):
            services.sign(app, request.data.get("signature"))
        return Response(status_payload(app, token))


class PdfView(_Public):
    def get(self, request, token: str):
        from .pdf import render

        app = own_application(token)
        if app.status == Application.Status.UNCONFIRMED:
            raise Http404
        with tenant_context(app.organization_id):
            data = render(app)
        response = HttpResponse(data, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="mitgliedsantrag-{app.number}.pdf"'
        return response


class KioskView(_Public):
    """Stand-Modus: Gerät mit zeitlich begrenztem Link, keine E-Mail-Bestätigung."""

    def link(self, token: str):
        link = services.find_kiosk(token)
        if link is None:
            raise Http404
        form = (
            ApplicationForm.objects.select_related("organization")
            .filter(organization_id=link.organization_id)
            .first()
        )
        if form is None or not form.enabled:
            raise Http404
        return link, form

    def get(self, request, token: str):
        link, form = self.link(token)
        language = self.language(request)
        with override(language):
            data = public.schema(form, language, request, request.query_params.get("einheit", ""))
        data["kiosk"] = link.label
        data["valid_until"] = link.valid_until
        return Response(data)

    def post(self, request, token: str):
        link, form = self.link(token)
        language = self.language(request)
        ser = public.SubmitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if too_many(f"join:kiosk:{link.pk}", 200, 60 * 60):
            return Response({"detail": gettext("Zu viele Anträge.")}, status=429)
        with override(language):
            clean = public.clean_submission(form, ser.validated_data, kiosk=True)
        with transaction.atomic(), tenant_context(form.organization_id):
            app, _token = services.create(form, clean, source="kiosk", kiosk=link)
        # Auf dem Gerät bleibt nichts lesbar: nur die Nummer zurück
        return Response({"status": "ok", "number": app.number}, status=201)
