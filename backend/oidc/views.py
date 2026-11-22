"""Schnittstellen der Nextcloud-Anmeldung.

Öffentlich (für die Nextcloud): ``/api/oidc/.well-known/openid-configuration``, ``jwks``,
``token``, ``userinfo``. Für die Seite „Bei der Nextcloud anmelden“ in HUBIplan:
``/api/oidc/authorize/`` (angemeldet, mit CSRF), für „Von der Nextcloud abgemeldet“:
``/api/oidc/end-session/`` (auch ohne Anmeldung). Einstellungen je Einheit:
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
from accounts import step_up
from accounts.mfa import encrypt
from audit.log import record
from core.api_base import AuditMixin, OrgScopedMixin
from core.ratelimit import TooMany, client_ip, too_many

from . import nc_accounts, nc_calendars, nc_groups, provider
from .models import USERNAME_RE, Account, Client, clean_groups, parse_usernames

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
        key = f"oidc:authorize:{request.user.pk}"
        if too_many(key, 30, 600):
            raise TooMany(key)
        try:
            return Response({"redirect": provider.authorize(request._request, request.data)})
        except provider.ConfirmNeeded as exc:
            return Response({"confirm": True, "name": exc.name}, status=409)
        except provider.AuthorizeError as exc:
            return Response(
                {"detail": exc.message, "redirect": exc.redirect, "back": exc.back}, status=400
            )


class EndSessionView(APIView):
    """Für die Seite „Von der Nextcloud abgemeldet“ (Ziel von ``end_session_endpoint``)."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        key = f"oidc:end-session:{client_ip(request)}"
        if too_many(key, 30, 600):
            raise TooMany(key)
        return Response(provider.end_session(request._request, request.data))


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
    role_choices = serializers.SerializerMethodField()
    # Gesamtaudit 15.11., AUTH-07: gespeicherte Zeilen auf gesperrte Konten (werden nie
    # zugeordnet); die Ansicht zeigt sie, gelöscht wird nichts
    blocked_usernames = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "id",
            "name",
            "base_url",
            "client_id",
            "audience",
            "require_mfa",
            "require_pkce",
            "groups_board",
            "groups_roles",
            "groups_units",
            "groups_members",
            "usernames",
            "role_groups",
            "role_choices",
            "blocked_usernames",
            "manage_accounts",
            "service_user",
            "service_password",
            "has_service_password",
            "account_group",
            "sync_error",
            "synced_at",
            "calendar_members",
            "calendar_members_group",
            "calendar_board",
            "calendar_board_group",
            "calendar_error",
            "calendar_synced_at",
            "sync_groups",
            "sync_groups_list",
            "groups_error",
            "groups_synced_at",
            "files_enabled",
            "files_root",
            "files_board_group",
            "files_finance_group",
            "files_members_group",
            "files_retention",
            "files_source",
            "files_error",
            "talk_enabled",
            "talk_keep_days",
            "is_active",
            "created_at",
            "last_used_at",
            "redirect_uri",
            "discovery_url",
        ]
        read_only_fields = [
            "client_id",
            "created_at",
            "last_used_at",
            "sync_error",
            "synced_at",
            "calendar_error",
            "calendar_synced_at",
            "groups_error",
            "groups_synced_at",
            "files_error",
        ]

    def get_has_service_password(self, obj) -> bool:
        return bool(obj.service_password)

    def get_blocked_usernames(self, obj) -> list[str]:
        return [
            f"{email} = {name}"
            for email, name, error in parse_usernames(obj.usernames, obj.blocked_usernames())
            if error == "blocked"
        ]

    def validate_service_user(self, value):
        value = str(value or "").strip()
        if value and not USERNAME_RE.match(value.lower()):
            raise serializers.ValidationError(gettext("Bitte den Benutzernamen des Dienstkontos."))
        return value

    def validate_service_password(self, value):
        # Leer heißt: das gespeicherte behalten
        return encrypt(value, purpose="nextcloud") if value else None

    def validate_account_group(self, value):
        value = " ".join(str(value or "").split())
        if len(value) > GROUP_MAX:
            raise serializers.ValidationError(gettext("Höchstens 64 Zeichen."))
        return value

    def validate_sync_groups_list(self, value):
        groups = clean_groups(value)
        if any(len(g) > GROUP_MAX for g in groups):
            raise serializers.ValidationError(gettext("Höchstens 64 Zeichen je Gruppe."))
        if any(g.casefold() == "admin" for g in groups):
            raise serializers.ValidationError(
                gettext("Die Administratorgruppe gleicht HUBIplan nie ab.")
            )
        text = ", ".join(groups)
        if len(text) > 500:
            raise serializers.ValidationError(gettext("Höchstens 500 Zeichen."))
        return text

    def _folder(self, value, field: str) -> str:
        from .nc_files import FilesError, clean_segments

        try:
            return "/".join(clean_segments(value))
        except FilesError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_files_root(self, value):
        value = self._folder(value, "files_root")
        return value or "HUBIplan"

    def validate_talk_keep_days(self, value):
        if value is None or not 0 <= value <= 90:
            raise serializers.ValidationError(gettext("Bitte 0 bis 90 Tage angeben."))
        return value

    def validate_files_source(self, value):
        return self._folder(value, "files_source")

    def validate_files_board_group(self, value):
        return self.validate_account_group(value)

    def validate_files_finance_group(self, value):
        return self.validate_account_group(value)

    def validate_files_members_group(self, value):
        return self.validate_account_group(value)

    def validate_files_retention(self, value):
        from .models import FileItem

        if not isinstance(value, dict):
            raise serializers.ValidationError(gettext("Ungültige Fristen."))
        out = {}
        for key, years in value.items():
            if key not in FileItem.Category.values or years in (None, ""):
                continue
            try:
                years = int(years)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(gettext("Ungültige Fristen.")) from exc
            if not 0 <= years <= 100:
                raise serializers.ValidationError(gettext("Frist zwischen 0 und 100 Jahren."))
            out[key] = years
        return out

    def validate_calendar_members_group(self, value):
        return self.validate_account_group(value)

    def validate_calendar_board_group(self, value):
        return self.validate_account_group(value)

    def get_redirect_uri(self, obj) -> str:
        return obj.redirect_uris[0]

    def get_discovery_url(self, obj) -> str:
        return f"{provider.issuer()}/.well-known/openid-configuration"

    def validate_base_url(self, value):
        return clean_base_url(value)

    def validate_usernames(self, value):
        service = str(self.initial_data.get("service_user") or "").strip().lower()
        if not service and self.instance is not None:
            service = (self.instance.service_user or "").strip().lower()
        lines = parse_usernames(value, {service} if service else frozenset())
        blocked = [f"{email} = {name}" for email, name, error in lines if error == "blocked"]
        if blocked:
            raise serializers.ValidationError(
                gettext(
                    "Verwaltungs- und Dienstkonten der Nextcloud lassen sich nicht zuordnen "
                    "(admin, root, administrator, das Dienstkonto). Bitte entfernen: {lines}"
                ).format(lines="; ".join(blocked[:3]))
            )
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

    def _roles(self) -> list:
        from access.models import Role

        org = self.context["org"]
        return list(
            Role.all_objects.filter(organization=org)
            .select_related("department")
            .order_by("department__name", "position", "name")
        )

    def get_role_choices(self, obj) -> list[dict]:
        """Alle Rollen der Einheit (auch Ämter in Untereinheiten) für die Zuordnungstabelle."""
        return [
            {
                "id": role.pk,
                "name": role.name,
                "unit": role.department.name if role.department_id else "",
                "is_board": role.is_board,
            }
            for role in self._roles()
        ]

    def validate_role_groups(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(gettext("Bitte je Rolle eine Liste von Gruppen."))
        known = {str(role.pk) for role in self._roles()}
        out: dict[str, list[str]] = {}
        for key, groups in value.items():
            key = str(key)
            if key not in known:
                # Gelöschte oder fremde Rolle: Eintrag fällt weg
                continue
            if not isinstance(groups, list | str):
                raise serializers.ValidationError(gettext("Bitte je Rolle eine Liste von Gruppen."))
            groups = clean_groups(groups)
            if any(len(g) > GROUP_MAX for g in groups):
                raise serializers.ValidationError(
                    gettext("Gruppennamen höchstens 64 Zeichen: {groups}").format(
                        groups=", ".join(g for g in groups if len(g) > GROUP_MAX)[:120]
                    )
                )
            if groups:
                out[key] = groups
        return out

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
        if attrs.get("sync_groups", inst.sync_groups if inst else False):
            user = attrs.get("service_user", inst.service_user if inst else "")
            password = attrs.get("service_password", inst.service_password if inst else "")
            group = attrs.get("account_group", inst.account_group if inst else "")
            if not user or not password or not group:
                raise serializers.ValidationError(
                    {
                        "sync_groups": gettext(
                            "Dafür braucht es Dienstkonto, App-Passwort und die Gruppe der "
                            "Konten über HUBIplan."
                        )
                    }
                )
        if attrs.get("talk_enabled", inst.talk_enabled if inst else False):
            user = attrs.get("service_user", inst.service_user if inst else "")
            password = attrs.get("service_password", inst.service_password if inst else "")
            if not user or not password:
                raise serializers.ValidationError(
                    {
                        "talk_enabled": gettext(
                            "Für Videoräume braucht es Dienstkonto und App-Passwort."
                        )
                    }
                )
        files = attrs.get("files_enabled", inst.files_enabled if inst else False) or attrs.get(
            "files_source", inst.files_source if inst else ""
        )
        if files:
            user = attrs.get("service_user", inst.service_user if inst else "")
            password = attrs.get("service_password", inst.service_password if inst else "")
            if not user or not password:
                raise serializers.ValidationError(
                    {
                        "files_enabled": gettext(
                            "Für Dateien braucht es Dienstkonto und App-Passwort."
                        )
                    }
                )
        calendars = any(
            attrs.get(name, getattr(inst, name) if inst else False)
            for name in ("calendar_members", "calendar_board")
        )
        if calendars:
            user = attrs.get("service_user", inst.service_user if inst else "")
            password = attrs.get("service_password", inst.service_password if inst else "")
            if not user or not password:
                raise serializers.ValidationError(
                    {
                        "calendar_members": gettext(
                            "Für die Kalender braucht es Dienstkonto und App-Passwort."
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


def _pairs(text: str) -> list[tuple[str, str]]:
    """Zuordnungen „E-Mail = Benutzername“ zeilenweise normalisiert, ohne Reihenfolge."""
    return sorted((email, name) for email, name, _x in parse_usernames(text))


def _groups(value, known: set[str]) -> dict[str, list[str]]:
    """Gruppen je Rolle bereinigt: nur bekannte Rollen, ohne leere Einträge."""
    out = {}
    for key, groups in (value or {}).items():
        groups = clean_groups(groups) if isinstance(groups, list | str) else []
        if str(key) in known and groups:
            out[str(key)] = sorted(groups)
    return out


# Ändert sich eines davon, gleicht HUBIplan die Gruppen gleich ab (mit Obergrenze)
GROUP_FIELDS = (
    "sync_groups",
    "sync_groups_list",
    "account_group",
    "role_groups",
    "groups_board",
    "groups_roles",
    "groups_units",
    "groups_members",
    "audience",
    "is_active",
)

CALENDAR_FIELDS = (
    "calendar_members",
    "calendar_members_group",
    "calendar_board",
    "calendar_board_group",
    "is_active",
)


def mapping_changed(client: Client, serializer: ClientSerializer) -> bool:
    """Ändert die Anfrage Benutzernamen oder Gruppen der Rollen wirklich? Dazu zählt, wer die
    Vorstandstermine in der Nextcloud sieht (Kalender an oder andere Gruppe)."""
    data = serializer.validated_data
    if "calendar_board" in data and data["calendar_board"] and not client.calendar_board:
        return True
    # Wer die abgelegten Dateien sieht (Ablage einschalten, andere Gruppe) und was HUBIplan aus der
    # Nextcloud lesen darf (Ordner zum Übernehmen)
    if "files_enabled" in data and data["files_enabled"] and not client.files_enabled:
        return True
    for name in ("files_board_group", "files_finance_group", "files_members_group", "files_source"):
        if name in data and data[name] != getattr(client, name):
            return True
    # Gruppenabgleich einschalten oder seine Liste ändern bestimmt, wer welche Gruppe hat
    if "sync_groups" in data and data["sync_groups"] and not client.sync_groups:
        return True
    if "sync_groups_list" in data and clean_groups(data["sync_groups_list"]) != clean_groups(
        client.sync_groups_list
    ):
        return True
    if (
        "calendar_board_group" in data
        and client.calendar_board
        and data["calendar_board_group"] != client.calendar_board_group
    ):
        return True
    if "usernames" in data and _pairs(data["usernames"]) != _pairs(client.usernames):
        return True
    if "role_groups" in data:
        known = {str(role.pk) for role in serializer._roles()}
        return _groups(data["role_groups"], known) != _groups(client.role_groups, known)
    return False


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

    def update(self, request, *args, **kwargs):
        # Gesamtaudit 15.11., AUTH-07: Zuordnungen zu Nextcloud-Konten und -Gruppen bestimmen,
        # wer dort was darf; Änderungen nur mit frischer Bestätigung und mit Hinweis. Die Seite
        # schickt beim Speichern alle Felder mit: Bestätigung nur, wenn sich eine Zuordnung
        # gegenüber dem gespeicherten Stand wirklich ändert.
        client = self.get_object()
        before = {"usernames": client.usernames, "role_groups": client.role_groups}
        calendars_before = {name: getattr(client, name) for name in CALENDAR_FIELDS}
        groups_before = {name: getattr(client, name) for name in GROUP_FIELDS}
        serializer = self.get_serializer(
            client, data=request.data, partial=kwargs.get("partial", False)
        )
        serializer.is_valid(raise_exception=True)
        if mapping_changed(client, serializer):
            step_up.require(request)
        self.perform_update(serializer)
        response = Response(serializer.data)
        client.refresh_from_db()
        changed = [k for k, v in before.items() if getattr(client, k) != v]
        if changed:
            notify_role_managers(self.org, client, request.user, changed)
        if any(getattr(client, k) != v for k, v in calendars_before.items()):
            _sync_calendars_later(
                client,
                {
                    nc_calendars.Kind.MEMBERS: calendars_before["calendar_members_group"],
                    nc_calendars.Kind.BOARD: calendars_before["calendar_board_group"],
                },
            )
        if client.sync_groups and any(getattr(client, k) != v for k, v in groups_before.items()):
            _sync_groups_later(client)
        return response

    def perform_create(self, serializer):
        super().perform_create(serializer)
        if nc_calendars.wanted_kinds(serializer.instance):
            _sync_calendars_later(serializer.instance)

    def perform_destroy(self, instance):
        # Kalender in der Nextcloud nicht verwaist zurücklassen (bestmöglich)
        for kind in instance.calendar_items.values_list("kind", flat=True).distinct():
            try:
                nc_calendars.delete_calendar(instance, kind)
            except nc_calendars.CalendarError:
                pass
        super().perform_destroy(instance)

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

    @action(detail=True, methods=["get", "post"], url_path="groups")
    def groups(self, request, *args, **kwargs):
        """GET: Soll und Ist der abgeglichenen Gruppen je Konto (fragt die Nextcloud).
        POST: Gruppen jetzt abgleichen (mit ``confirm`` ohne Obergrenze)."""
        client = self.get_object()
        if not client.managed_groups():
            raise ValidationError(
                {"detail": gettext("Es ist keine Gruppe für den Abgleich eingetragen.")}
            )
        if request.method == "POST":
            if not client.sync_groups:
                raise ValidationError({"detail": gettext("„Gruppen laufend abgleichen“ ist aus.")})
            result = nc_groups.sync(client, confirmed=bool(request.data.get("confirm")))
            client.refresh_from_db()
            return Response({"result": result, "client": self.get_serializer(client).data})
        plans = sorted(nc_groups.plan(client), key=lambda p: p.account.nc_user)
        return Response(
            {
                "managed": client.managed_groups(),
                "missing_admin": nc_groups.missing_admin(client),
                "accounts": [
                    {
                        "id": p.account.pk,
                        "nc_user": p.account.nc_user,
                        "email": p.account.user.email,
                        "name": p.account.user.get_full_name() or p.account.user.email,
                        "current": p.current,
                        "add": p.add,
                        "remove": p.remove,
                        "error": p.note if p.missing else p.error,
                        "missing": p.missing,
                    }
                    for p in plans
                ],
            }
        )

    @action(detail=True, methods=["post"], url_path="calendars")
    def calendars(self, request, *args, **kwargs):
        """Kalender jetzt abgleichen (Termine in die Nextcloud schreiben)."""
        client = self.get_object()
        if not nc_calendars.wanted_kinds(client) and not client.calendar_items.exists():
            raise ValidationError({"detail": gettext("Es ist kein Kalender eingeschaltet.")})
        # Unter rls_bypass: Termine des Dachverbands gehören auch hinein
        result = nc_calendars.sync_client(client.pk)
        client.refresh_from_db()
        return Response({"result": result, "client": self.get_serializer(client).data})


def _sync_groups_later(client: Client) -> None:
    from .tasks import sync_client_groups

    pk = client.pk
    transaction.on_commit(lambda: sync_client_groups.delay(pk))


def _sync_calendars_later(client: Client, unshare: dict | None = None) -> None:
    from .tasks import sync_client_calendars

    pk = client.pk
    transaction.on_commit(lambda: sync_client_calendars.delay(pk, unshare))


def notify_role_managers(org, client, actor, changed: list[str]) -> None:
    """Hinweis an alle mit „Rollen verwalten“, wenn sich Zuordnungen zur Nextcloud ändern."""
    from django.db import transaction
    from django.utils.translation import gettext as _

    from access.models import RoleAssignment
    from access.permissions import permissions_in
    from core.i18n import language_of, user_language
    from outbox.mail import send as send_mail

    users = {
        a.user
        for a in RoleAssignment.objects.filter(organization=org, user__isnull=False)
        .active()
        .select_related("user")
    }
    recipients = [u for u in users if u.is_active and ROLES_MANAGE in permissions_in(u, org)]
    from django.utils.translation import gettext_noop

    labels = {
        "usernames": gettext_noop("bisherige Benutzernamen"),
        "role_groups": gettext_noop("Gruppen für Rollen"),
    }

    def send() -> None:
        for user in recipients:
            with language_of(user):
                body = _(
                    "Hallo,\n\nbei {org} hat {who} für „{name}“ geändert: {what}.\n\n"
                    "Diese Zuordnungen bestimmen, welche Konten und Gruppen in der Nextcloud "
                    "jemand bekommt. War das nicht abgesprochen, prüft bitte unter Einstellungen "
                    "› Nextcloud.\n"
                ).format(
                    org=org.name,
                    who=actor.get_full_name() or actor.email,
                    name=client.name,
                    what=", ".join(_(labels[k]) for k in changed),
                )
                subject = _("Nextcloud-Zuordnung geändert")
            send_mail(
                [user.email],
                subject,
                body,
                kind="sicherheit",
                fail_silently=True,
                language=user_language(user),
            )

    transaction.on_commit(send)
