"""Schnittstellen der Nextcloud-Anmeldung.

Öffentlich (für die Nextcloud): ``/api/oidc/.well-known/openid-configuration``, ``jwks``,
``token``, ``userinfo``. Für die Seite „Bei der Nextcloud anmelden“ in HUBIplan:
``/api/oidc/authorize/`` (angemeldet, mit CSRF). Einstellungen je Einheit:
``/api/orgs/<id>/nextcloud/``.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils.translation import gettext
from rest_framework import serializers, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import ROLES_MANAGE
from accounts.mfa import encrypt
from audit.log import record
from core.api_base import AuditMixin, OrgScopedMixin
from core.ratelimit import client_ip, too_many

from . import nc_accounts, provider
from .models import USERNAME_RE, Account, Client, parse_usernames

TOKEN_RATE = (60, 60)


def _json(data: dict, status: int = 200) -> JsonResponse:
    response = JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response


class _Public(APIView):
    """Für die Nextcloud (Server oder Browser): ohne Anmeldung, ohne Sitzung, ohne CSRF."""

    authentication_classes: list = []
    permission_classes = [AllowAny]


class DiscoveryView(_Public):
    def get(self, request):
        response = JsonResponse(provider.discovery())
        response["Cache-Control"] = "public, max-age=3600"
        return response


class JwksView(_Public):
    def get(self, request):
        response = JsonResponse(provider.jwks())
        response["Cache-Control"] = "public, max-age=3600"
        return response


def _token_error(exc: provider.TokenError) -> JsonResponse:
    body = {"error": exc.error}
    if exc.description:
        body["error_description"] = exc.description
    response = _json(body, status=exc.status)
    if exc.status == 401:
        basic = exc.error == "invalid_client"
        response["WWW-Authenticate"] = (
            'Basic realm="hubiplan"' if basic else 'Bearer error="invalid_token"'
        )
    return response


class TokenView(_Public):
    """Code einlösen. Aufrufer ist der Server der Nextcloud (Formular, kein JSON)."""

    parser_classes = [FormParser]

    def post(self, request):
        if too_many(f"oidc:token:{client_ip(request)}", *TOKEN_RATE):
            return _json({"error": "slow_down"}, status=429)
        try:
            return _json(provider.token(request._request))
        except provider.TokenError as exc:
            return _token_error(exc)


class UserinfoView(_Public):
    def _answer(self, request):
        if too_many(f"oidc:userinfo:{client_ip(request)}", *TOKEN_RATE):
            return _json({"error": "slow_down"}, status=429)
        try:
            return _json(provider.userinfo(request._request))
        except provider.TokenError as exc:
            return _token_error(exc)

    def get(self, request):
        return self._answer(request)

    def post(self, request):
        return self._answer(request)


class AuthorizeView(APIView):
    """Für die Seite „Bei der Nextcloud anmelden“: Dienst beschreiben bzw. Code ausstellen."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            return Response(provider.describe(request.query_params))
        except provider.AuthorizeError as exc:
            return Response({"detail": exc.message}, status=400)

    def post(self, request):
        if too_many(f"oidc:authorize:{request.user.pk}", 30, 600):
            raise ValidationError({"detail": gettext("Zu viele Versuche. Bitte später erneut.")})
        try:
            return Response({"redirect": provider.authorize(request._request, request.data)})
        except provider.AuthorizeError as exc:
            return Response(
                {"detail": exc.message, "redirect": exc.redirect, "back": exc.back}, status=400
            )


# --- Einstellungen je Einheit ---


def clean_base_url(value: str) -> str:
    parts = urlsplit(str(value or "").strip())
    allow_http = settings.DEBUG and parts.hostname in ("localhost", "127.0.0.1")
    if parts.scheme != "https" and not (parts.scheme == "http" and allow_http):
        raise serializers.ValidationError(gettext("Bitte die Adresse mit https:// angeben."))
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise serializers.ValidationError(
            gettext("Bitte nur die Adresse der Nextcloud angeben, z. B. https://cloud.example.org")
        )
    path = parts.path.rstrip("/")
    if path.endswith("/index.php"):
        path = path[: -len("/index.php")]
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, "", ""))


GROUP_MAX = 64


class ClientSerializer(serializers.ModelSerializer):
    redirect_uri = serializers.SerializerMethodField()
    discovery_url = serializers.SerializerMethodField()
    # Nur schreiben; die Antwort sagt nur, ob eines gespeichert ist
    service_password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, trim_whitespace=True
    )
    has_service_password = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "id",
            "name",
            "base_url",
            "client_id",
            "audience",
            "require_mfa",
            "groups_board",
            "groups_roles",
            "groups_units",
            "groups_members",
            "usernames",
            "manage_accounts",
            "service_user",
            "service_password",
            "has_service_password",
            "account_group",
            "sync_error",
            "synced_at",
            "is_active",
            "created_at",
            "last_used_at",
            "redirect_uri",
            "discovery_url",
        ]
        read_only_fields = ["client_id", "created_at", "last_used_at", "sync_error", "synced_at"]

    def get_has_service_password(self, obj) -> bool:
        return bool(obj.service_password)

    def validate_service_user(self, value):
        value = str(value or "").strip()
        if value and not USERNAME_RE.match(value.lower()):
            raise serializers.ValidationError(gettext("Bitte den Benutzernamen des Dienstkontos."))
        return value

    def validate_service_password(self, value):
        # Leer heißt: das gespeicherte behalten
        return encrypt(value) if value else None

    def validate_account_group(self, value):
        value = " ".join(str(value or "").split())
        if len(value) > GROUP_MAX:
            raise serializers.ValidationError(gettext("Höchstens 64 Zeichen."))
        return value

    def get_redirect_uri(self, obj) -> str:
        return obj.redirect_uris[0]

    def get_discovery_url(self, obj) -> str:
        return f"{provider.issuer()}/.well-known/openid-configuration"

    def validate_base_url(self, value):
        return clean_base_url(value)

    def validate_usernames(self, value):
        lines = parse_usernames(value)
        bad = [f"{email} = {name}" for email, name, error in lines if error]
        if bad:
            raise serializers.ValidationError(
                gettext(
                    "Bitte je Zeile „E-Mail = Benutzername“ (Benutzername nur Kleinbuchstaben, "
                    "Ziffern, Punkt, Bindestrich, Unterstrich, @). Fehlerhaft: {lines}"
                ).format(lines="; ".join(bad[:3]))
            )
        names = [name for _e, name, _x in lines]
        emails = [email for email, _n, _x in lines]
        double = sorted(
            {n for n in names if names.count(n) > 1} | {e for e in emails if emails.count(e) > 1}
        )
        if double:
            raise serializers.ValidationError(
                gettext("Doppelt eingetragen: {items}").format(items=", ".join(double[:3]))
            )
        return "\n".join(f"{email} = {name}" for email, name, _x in lines)

    def validate(self, attrs):
        org = self.context["org"]
        if attrs.get("audience") == Client.Audience.MEMBERS and org.type != "club":
            raise serializers.ValidationError(
                {"audience": gettext("Mitgliederzugänge gibt es nur bei Vereinen.")}
            )
        if attrs.get("service_password", "") is None:
            attrs.pop("service_password")
        inst = self.instance
        manage = attrs.get("manage_accounts", inst.manage_accounts if inst else False)
        if manage:
            user = attrs.get("service_user", inst.service_user if inst else "")
            password = attrs.get("service_password", inst.service_password if inst else "")
            group = attrs.get("account_group", inst.account_group if inst else "")
            if not user or not password or not group:
                raise serializers.ValidationError(
                    {
                        "manage_accounts": gettext(
                            "Dafür braucht es Dienstkonto, App-Passwort und Gruppe."
                        )
                    }
                )
        return attrs


class AccountSerializer(serializers.ModelSerializer):
    email = serializers.CharField(source="user.email", read_only=True)
    name = serializers.SerializerMethodField()
    planned = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = [
            "id",
            "nc_user",
            "email",
            "name",
            "first_login_at",
            "last_login_at",
            "disabled_by_hubiplan",
            "changed_at",
            "error",
            "planned",
        ]

    def get_name(self, obj) -> str:
        return obj.user.get_full_name() or obj.user.email

    def get_planned(self, obj) -> str:
        return self.context.get("planned", {}).get(obj.pk, "")


class ClientViewSet(OrgScopedMixin, AuditMixin, viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    read_permission = ROLES_MANAGE
    write_permission = ROLES_MANAGE
    allowed_org_types = ("club", "federation")

    def get_queryset(self):
        return Client.objects.filter(organization=self.org)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = getattr(self, "org", None)
        return ctx

    def get_create_kwargs(self) -> dict:
        draft = Client()
        self._secret = draft.set_secret()
        return {
            "organization": self.org,
            "created_by": self.request.user,
            "secret_hash": draft.secret_hash,
        }

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        # Das Geheimnis gibt es nur in dieser Antwort; gespeichert ist nur die Prüfsumme
        response.data["client_secret"] = self._secret
        return response

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def secret(self, request, *args, **kwargs):
        """Neues Geheimnis (das alte gilt sofort nicht mehr)."""
        client = self.get_object()
        secret = client.set_secret()
        client.save(update_fields=["secret_hash", "updated_at"])
        record(self.org, request.user, "update", client, {"Geheimnis": ["…", "neu"]})
        data = dict(self.get_serializer(client).data)
        data["client_secret"] = secret
        return Response(data)

    @action(detail=True, methods=["get"])
    def accounts(self, request, *args, **kwargs):
        """Konten über HUBIplan, mit dem, was der nächste Abgleich täte (Probelauf)."""
        client = self.get_object()
        plans = nc_accounts.plan(client)
        planned = {p.account.pk: p.action for p in plans}
        items = sorted((p.account for p in plans), key=lambda a: a.nc_user)
        return Response(AccountSerializer(items, many=True, context={"planned": planned}).data)

    @action(detail=True, methods=["post"])
    def check(self, request, *args, **kwargs):
        """Dienstkonto bei der Nextcloud prüfen."""
        client = self.get_object()
        try:
            name = nc_accounts.check_connection(client)
        except nc_accounts.NextcloudError as exc:
            return Response({"ok": False, "detail": str(exc)}, status=400)
        return Response({"ok": True, "detail": gettext("Verbunden als {name}.").format(name=name)})

    @action(detail=True, methods=["post"])
    def sync(self, request, *args, **kwargs):
        """Abgleich jetzt ausführen (auch nach einem Halt: mit ``confirm`` ohne Obergrenze)."""
        client = self.get_object()
        if not client.manage_accounts:
            raise ValidationError({"detail": gettext("„Konten automatisch deaktivieren“ ist aus.")})
        result = nc_accounts.sync(client, confirmed=bool(request.data.get("confirm")))
        client.refresh_from_db()
        return Response({"result": result, "client": self.get_serializer(client).data})
