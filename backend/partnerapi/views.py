"""API für andere Programme: ``/api/partner/v1/…`` (docs/api.md, Stufe 1).

Nur lesen, nur mit Schlüssel ``hpk_…``. Die Einheit steht nie in der Adresse; sie ergibt sich
aus dem Schlüssel. Jede Ansicht verlangt genau einen Bereich (``scope``). Die Ausgabeformate
hier sind der Vertrag mit Dritten: In ``v1`` kommen nur Felder hinzu, keines fällt weg.
"""

from __future__ import annotations

import base64
import datetime
import json

from django.conf import settings
from django.http import FileResponse, Http404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from core.ratelimit import bucket, retry_after, too_many
from core.tenancy import org_context, rls_bypass

from . import scopes as sc
from .auth import Problem, bearer, caller_ip, find_access, note_use

API_VERSION = "1"
# Anfragen je Stunde und Zugang; dazu je Minute und Adresse (auch ohne gültigen Schlüssel)
ACCESS_LIMIT = 600
IP_LIMIT = 300
MAX_LIMIT = 200
DEFAULT_LIMIT = 100
# Termine: Vorgabe und größtes Fenster je Abruf
EVENTS_BACK = datetime.timedelta(days=30)
EVENTS_AHEAD = datetime.timedelta(days=365)
EVENTS_WINDOW = datetime.timedelta(days=366 * 2)
MAX_POSTS = 50
CORS_HEADERS = "Authorization, Content-Type"
PROBLEM_TYPE = "application/problem+json"


class PartnerProblemSerializer(serializers.Serializer):
    type = serializers.CharField()
    title = serializers.CharField()
    status = serializers.IntegerField()
    code = serializers.CharField()
    detail = serializers.CharField(required=False)


LIMIT = OpenApiParameter("limit", OpenApiTypes.INT, description="1 bis 200, Vorgabe 100")
CURSOR = OpenApiParameter("cursor", OpenApiTypes.STR, description="``next_cursor`` der Seite davor")
ERRORS = {
    401: PartnerProblemSerializer,
    403: PartnerProblemSerializer,
    429: PartnerProblemSerializer,
}


def _problem(status: int, code: str, title: str, detail: str = "", **extra) -> Response:
    body = {"type": "about:blank", "title": title, "status": status, "code": code, **extra}
    if detail:
        body["detail"] = detail
    return Response(body, status=status, content_type=PROBLEM_TYPE)


class PartnerView(APIView):
    """Gemeinsame Prüfung: Schlüssel, Grenzen, Bereich; danach Zeilensicherheit der Einheit."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    # Bereich, den die Ansicht verlangt (None: jeder gültige Zugang)
    scope: str | None = None

    def options(self, request, *args, **kwargs):
        """Vorabfrage des Browsers (CORS) kommt ohne Schlüssel; die eigentliche Anfrage
        bekommt die Freigabe nur, wenn der Zugang „aus fremden Webseiten aufrufbar“ ist."""
        response = Response(status=204)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response["Access-Control-Allow-Headers"] = CORS_HEADERS
        response["Access-Control-Max-Age"] = "600"
        return response

    def initial(self, request, *args, **kwargs):
        if not settings.PARTNER_API_ENABLED:
            raise Http404
        super().initial(request, *args, **kwargs)
        if request.method == "OPTIONS":
            return
        ip = caller_ip(request)
        ip_key = f"partnerapi:ip:{bucket(ip)}"
        if too_many(ip_key, IP_LIMIT, 60):
            raise _TooMany(retry_after(ip_key))
        access = find_access(bearer(request), ip)
        access_key = f"partnerapi:access:{access.pk}"
        if too_many(access_key, ACCESS_LIMIT, 3600):
            raise _TooMany(retry_after(access_key))
        if self.scope and self.scope not in self.granted(access):
            raise Problem(
                403,
                "missing_scope",
                _("Diesem API-Zugang fehlt der Bereich"),
                _("Nötig ist der Bereich „{scope}“.").format(scope=self.scope),
                scope=self.scope,
            )
        note_use(access, ip)
        self.access = access
        self.org = access.organization
        self.unit = access.unit if access.unit_id else None

    @staticmethod
    def granted(access) -> set[str]:
        """Gewählte Bereiche, soweit die Einheit sie heute noch vergeben könnte (Modul an)."""
        return set(sc.clean(access.scopes or [], access.organization, access.unit))

    def handle_exception(self, exc):
        if isinstance(exc, Problem):
            response = _problem(exc.status, exc.code, exc.title, exc.detail, **exc.extra)
            if exc.status == 401:
                response["WWW-Authenticate"] = 'Bearer realm="HUBIplan API"'
            return response
        if isinstance(exc, _TooMany):
            response = _problem(
                429,
                "too_many_requests",
                _("Zu viele Anfragen"),
                _("Bitte später erneut versuchen."),
            )
            if exc.wait:
                response["Retry-After"] = str(exc.wait)
            return response
        if isinstance(exc, Http404):
            return _problem(404, "not_found", _("Nicht gefunden"))
        if isinstance(exc, serializers.ValidationError):
            return _problem(
                400,
                "invalid_request",
                _("Ungültige Anfrage"),
                json.dumps(exc.detail, default=str, ensure_ascii=False),
            )
        if isinstance(exc, APIException):
            return _problem(exc.status_code, exc.default_code, str(exc.detail))
        return super().handle_exception(exc)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        access = getattr(self, "access", None)
        if access is not None and access.embeddable:
            response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Headers"] = CORS_HEADERS
        return response

    # --- Hilfen ---

    def site(self, request):
        """Die öffentliche Webseite der Einheit, sonst None. „Veröffentlicht“ heißt für diese
        Schnittstelle: steht auf der öffentlichen Webseite."""
        from website import services
        from website.models import Website
        from website.public import SiteView

        if self.unit is not None or not services.module_enabled(self.org):
            return None
        website = services.website_of(self.org)
        if website is None or services.effective_state(website) != Website.State.PUBLIC:
            return None
        return SiteView(website, request.build_absolute_uri("/"))


class _TooMany(Exception):
    def __init__(self, wait: int | None):
        super().__init__("too many requests")
        self.wait = wait


def _limit(request, default: int = DEFAULT_LIMIT, maximum: int = MAX_LIMIT) -> int:
    raw = request.query_params.get("limit")
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise serializers.ValidationError({"limit": _("Zahl erwartet.")}) from exc
    return max(1, min(value, maximum))


def _offset(request) -> int:
    """Der Cursor ist undurchsichtig; heute steht darin die Position in der Liste."""
    raw = request.query_params.get("cursor")
    if not raw:
        return 0
    try:
        return max(0, int(base64.urlsafe_b64decode(raw.encode() + b"==").decode()))
    except (ValueError, UnicodeDecodeError) as exc:
        raise serializers.ValidationError({"cursor": _("Unbekannter Cursor.")}) from exc


def _page(items: list, request, default: int = DEFAULT_LIMIT) -> tuple[list, str | None]:
    limit, start = _limit(request, default), _offset(request)
    chunk = items[start : start + limit]
    more = start + limit < len(items)
    cursor = base64.urlsafe_b64encode(str(start + limit).encode()).decode().rstrip("=")
    return chunk, cursor if more else None


def _moment(request, name: str) -> datetime.datetime | None:
    raw = request.query_params.get(name)
    if not raw:
        return None
    value = parse_datetime(raw)
    if value is None:
        day = parse_date(raw)
        if day is None:
            raise serializers.ValidationError({name: _("Datum oder Zeit nach ISO 8601 erwartet.")})
        value = datetime.datetime.combine(day, datetime.time.min)
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    return value


# --- Selbstauskunft ---


class PartnerScopeSerializer(serializers.Serializer):
    scope = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()


class PartnerUnitRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    type = serializers.CharField(help_text="federation, club oder unit")


class PartnerLimitsSerializer(serializers.Serializer):
    requests_per_hour = serializers.IntegerField()
    max_page_size = serializers.IntegerField()


class PartnerAccessInfoSerializer(serializers.Serializer):
    name = serializers.CharField()
    scopes = PartnerScopeSerializer(many=True)
    expires_at = serializers.DateTimeField()
    embeddable = serializers.BooleanField()
    limits = PartnerLimitsSerializer()


class PartnerInfoSerializer(serializers.Serializer):
    product = serializers.CharField()
    api_version = serializers.CharField()
    version = serializers.CharField()
    unit = PartnerUnitRefSerializer()
    access = PartnerAccessInfoSerializer()


class InfoView(PartnerView):
    @extend_schema(
        operation_id="info",
        summary="Selbstauskunft des Zugangs",
        description="Einheit, Bereiche, Ablaufdatum und Grenzen des benutzten API-Zugangs.",
        responses={200: PartnerInfoSerializer, **ERRORS},
    )
    def get(self, request):
        from core.version import running_version

        unit = self.access.scope_unit
        data = {
            "product": "HUBIplan",
            "api_version": API_VERSION,
            "version": running_version(),
            "unit": {"id": unit.uuid, "name": unit.name, "type": unit.type},
            "access": {
                "name": self.access.name,
                "scopes": sc.describe(self.granted(self.access)),
                "expires_at": self.access.expires_at,
                "embeddable": self.access.embeddable,
                "limits": {"requests_per_hour": ACCESS_LIMIT, "max_page_size": MAX_LIMIT},
            },
        }
        return Response(PartnerInfoSerializer(data).data)


# --- Einheit ---


class PartnerUnitSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.CharField(help_text="federation, club oder unit")
    name = serializers.CharField()
    short_name = serializers.CharField(allow_blank=True)
    founding_year = serializers.IntegerField(allow_null=True)
    street = serializers.CharField(allow_blank=True)
    postal_code = serializers.CharField(allow_blank=True)
    city = serializers.CharField(allow_blank=True)
    country = serializers.CharField(allow_blank=True)
    website = serializers.CharField(allow_blank=True)
    contact_email = serializers.CharField(allow_blank=True)
    contact_phone = serializers.CharField(allow_blank=True)
    logo_url = serializers.CharField(allow_null=True)
    updated_at = serializers.DateTimeField(allow_null=True)


class UnitView(PartnerView):
    """Name, Anschrift, Kontakt und Logo der Einheit des Zugangs (bei einem Zugang für eine
    Untereinheit: dieser Untereinheit)."""

    scope = sc.UNIT_READ

    @extend_schema(
        operation_id="unit",
        summary="Stammdaten der Einheit",
        responses={200: PartnerUnitSerializer, **ERRORS},
    )
    def get(self, request):
        from organizations.serializers import effective_contact

        unit = self.access.scope_unit
        with org_context(self.org):
            contact = effective_contact(unit) if self.unit is None else {}
        data = {
            "id": unit.uuid,
            "type": unit.type,
            "name": unit.name,
            "short_name": unit.short_name,
            "founding_year": unit.founding_year,
            "street": unit.street,
            "postal_code": unit.postal_code,
            "city": unit.city,
            "country": unit.country,
            "website": unit.website,
            "contact_email": contact.get("email") or "",
            "contact_phone": contact.get("phone") or "",
            "logo_url": request.build_absolute_uri("/api/partner/v1/unit/logo")
            if unit.logo
            else None,
            "updated_at": getattr(unit, "updated_at", None),
        }
        return Response(PartnerUnitSerializer(data).data)


class UnitLogoView(PartnerView):
    """Logo der Einheit als Bilddatei; 404, wenn keines hinterlegt ist."""

    scope = sc.UNIT_READ

    @extend_schema(
        operation_id="unit_logo",
        summary="Logo der Einheit",
        responses={(200, "image/*"): OpenApiTypes.BINARY, 404: PartnerProblemSerializer, **ERRORS},
    )
    def get(self, request):
        import mimetypes

        logo = self.access.scope_unit.logo
        if not logo:
            raise Http404
        ctype = mimetypes.guess_type(logo.name)[0] or "application/octet-stream"
        if not ctype.startswith("image/") or ctype == "image/svg+xml":
            ctype = "application/octet-stream"
        response = FileResponse(logo.open("rb"), content_type=ctype)
        response["Content-Disposition"] = "inline"
        return response


class PartnerSubUnitSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    parent = serializers.UUIDField(allow_null=True)
    name = serializers.CharField()
    short_name = serializers.CharField(allow_blank=True)
    founding_year = serializers.IntegerField(allow_null=True)
    website = serializers.CharField(allow_blank=True)


class PartnerSubUnitListSerializer(serializers.Serializer):
    units = PartnerSubUnitSerializer(many=True)


def _subunits(access):
    """Aktive Untereinheiten unter der Einheit des Zugangs, in Baumreihenfolge."""
    from organizations.models import Department
    from organizations.tree import subtree_ids

    qs = Department.objects.filter(organization=access.organization, is_active=True)
    if access.unit_id:
        qs = qs.filter(pk__in=subtree_ids(access.unit)).exclude(pk=access.unit_id)
    return list(qs.order_by("sort_order", "name", "pk"))


class SubUnitsView(PartnerView):
    scope = sc.UNIT_READ

    @extend_schema(
        operation_id="units",
        summary="Untereinheiten als Baum",
        description=(
            "Alle aktiven Untereinheiten unter der Einheit des Zugangs. ``parent`` ist die "
            "Kennung der Einheit direkt darüber, ``null`` direkt unter der Einheit des Zugangs."
        ),
        responses={200: PartnerSubUnitListSerializer, **ERRORS},
    )
    def get(self, request):
        top = self.access.scope_unit
        with org_context(self.org):
            units = _subunits(self.access)
            ids = {u.pk: u.uuid for u in units}
            rows = [
                {
                    "id": u.uuid,
                    "parent": None if u.parent_id == top.pk else ids.get(u.parent_id),
                    "name": u.name,
                    "short_name": u.short_name,
                    "founding_year": u.founding_year,
                    "website": u.website,
                }
                for u in units
            ]
        return Response(PartnerSubUnitListSerializer({"units": rows}).data)


# --- Termine ---


class PartnerCategorySerializer(serializers.Serializer):
    name = serializers.CharField()
    color = serializers.CharField()


class PartnerEventSerializer(serializers.Serializer):
    id = serializers.CharField(help_text="Kennung des Einzeltermins (bei Serien je Wiederholung)")
    event_id = serializers.CharField(help_text="Kennung des Termins bzw. der Serie")
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    all_day = serializers.BooleanField()
    hide_end_time = serializers.BooleanField()
    location = serializers.CharField(allow_blank=True)
    address = serializers.CharField(allow_blank=True)
    category = PartnerCategorySerializer(allow_null=True)
    visibility = serializers.ChoiceField(choices=["public", "members"])
    unit = serializers.UUIDField(allow_null=True, help_text="Untereinheit, sonst null")
    is_cancelled = serializers.BooleanField()
    note = serializers.CharField(allow_blank=True)
    recurring = serializers.BooleanField()
    updated_at = serializers.DateTimeField()


class PartnerEventListSerializer(serializers.Serializer):
    events = PartnerEventSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class EventsView(PartnerView):
    scope = sc.EVENTS_READ

    @extend_schema(
        operation_id="events",
        summary="Termine",
        description=(
            "Eigene Termine der Einheit und ihrer Untereinheiten als Einzeltermine, Serien "
            "aufgelöst, nach Beginn sortiert. Ohne den Bereich „termine.mitglieder“ nur "
            "öffentliche Termine. Nie enthalten: Termine „nur Vorstand“, Zu- und Absagen, "
            "Teilnehmende, Anhänge, übernommene fremde Termine."
        ),
        parameters=[
            OpenApiParameter("from", OpenApiTypes.DATETIME, description="Vorgabe: vor 30 Tagen"),
            OpenApiParameter("to", OpenApiTypes.DATETIME, description="Vorgabe: in 365 Tagen"),
            OpenApiParameter(
                "unit", OpenApiTypes.UUID, description="nur diese Untereinheit und die darunter"
            ),
            OpenApiParameter(
                "changed_since",
                OpenApiTypes.DATETIME,
                description="nur Termine, die seitdem geändert wurden",
            ),
            LIMIT,
            OpenApiParameter(
                "cursor", OpenApiTypes.STR, description="``next_cursor`` der Seite davor"
            ),
        ],
        responses={200: PartnerEventListSerializer, 400: PartnerProblemSerializer, **ERRORS},
    )
    def get(self, request):
        from events.models import Event
        from events.recurrence import in_window, occurrences
        from organizations.models import Department
        from organizations.tree import subtree_ids

        now = timezone.now()
        start = _moment(request, "from") or now - EVENTS_BACK
        end = _moment(request, "to") or now + EVENTS_AHEAD
        if end <= start:
            raise serializers.ValidationError({"to": _("Muss nach „from“ liegen.")})
        if end - start > EVENTS_WINDOW:
            raise serializers.ValidationError({"to": _("Höchstens zwei Jahre je Abruf.")})
        visible = [Event.Visibility.PUBLIC]
        if sc.EVENTS_MEMBERS in self.granted(self.access):
            visible.append(Event.Visibility.MEMBERS)
        with org_context(self.org):
            qs = Event.objects.filter(
                organization=self.org,
                visibility__in=visible,
                remote_uid="",
                external_source__isnull=True,
                source_stale=False,
            )
            if self.unit is not None:
                qs = qs.filter(department_id__in=subtree_ids(self.unit))
            wanted = request.query_params.get("unit")
            if wanted:
                try:
                    unit = Department.objects.filter(
                        organization=self.org, uuid=wanted, is_active=True
                    ).first()
                except (ValueError, TypeError, serializers.DjangoValidationError):
                    unit = None
                if unit is None:
                    raise Http404
                qs = qs.filter(department_id__in=subtree_ids(unit))
            since = _moment(request, "changed_since")
            if since is not None:
                qs = qs.filter(updated_at__gte=since)
            items = occurrences(
                in_window(qs, start, end).select_related("category", "department"), start, end
            )
            items.sort(key=lambda o: (o.starts_at, o.event.pk))
            chunk, cursor = _page(items, request)
            rows = [
                {
                    "id": o.key,
                    "event_id": str(o.event.pk),
                    "title": o.event.title,
                    "description": o.event.description,
                    "starts_at": o.starts_at,
                    "ends_at": o.ends_at,
                    "all_day": o.event.all_day,
                    "hide_end_time": o.event.hide_end_time,
                    "location": o.event.location,
                    "address": o.event.address,
                    "category": {"name": o.event.category.name, "color": o.event.category.color}
                    if o.event.category_id
                    else None,
                    "visibility": o.event.visibility,
                    "unit": o.event.department.uuid if o.event.department_id else None,
                    "is_cancelled": o.is_cancelled,
                    "note": o.note,
                    "recurring": o.event.repeat != Event.Repeat.NONE,
                    "updated_at": o.event.updated_at,
                }
                for o in chunk
            ]
        return Response(PartnerEventListSerializer({"events": rows, "next_cursor": cursor}).data)


# --- Mitgliederzahlen ---


class PartnerCensusRowSerializer(serializers.Serializer):
    label = serializers.CharField()
    counts = serializers.ListField(child=serializers.IntegerField())
    total = serializers.IntegerField()


class PartnerCensusGroupSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    organizations = serializers.IntegerField()
    rows = PartnerCensusRowSerializer(many=True)
    genders = serializers.ListField(child=serializers.IntegerField())
    total = serializers.IntegerField()


class PartnerCensusSerializer(serializers.Serializer):
    date = serializers.DateField()
    ages = serializers.ChoiceField(choices=["sport", "jugend", "zehn"])
    counting = serializers.ChoiceField(choices=["stichtag", "jahrgang"])
    gender_labels = serializers.ListField(child=serializers.CharField())
    total = serializers.IntegerField(help_text="Mitgliedschaften am Stichtag")
    persons = serializers.IntegerField()
    organizations = serializers.IntegerField(help_text="Mitglieder, die keine Personen sind")
    rows = PartnerCensusRowSerializer(many=True, help_text="je Altersgruppe: Anzahl je Geschlecht")
    genders = serializers.ListField(child=serializers.IntegerField())
    groups_title = serializers.CharField(allow_blank=True)
    groups = PartnerCensusGroupSerializer(many=True)


class CensusView(PartnerView):
    scope = sc.STATISTICS_READ

    @extend_schema(
        operation_id="statistics_census",
        summary="Mitgliederzahlen zum Stichtag",
        description=(
            "Anzahlen nach Altersgruppe und Geschlecht, dazu je Untereinheit bzw. Verein. "
            "Nur Zahlen, keine Personen und keine Wohnorte. ``counts`` und ``genders`` folgen "
            "der Reihenfolge von ``gender_labels``."
        ),
        parameters=[
            OpenApiParameter("date", OpenApiTypes.DATE, description="Stichtag, Vorgabe heute"),
            OpenApiParameter(
                "ages",
                OpenApiTypes.STR,
                enum=["sport", "jugend", "zehn"],
                description="Altersgruppen",
            ),
            OpenApiParameter(
                "counting",
                OpenApiTypes.STR,
                enum=["stichtag", "jahrgang"],
                description="Alter am Stichtag oder nach Jahrgang",
            ),
        ],
        responses={200: PartnerCensusSerializer, 400: PartnerProblemSerializer, **ERRORS},
    )
    def get(self, request):
        from members import census, statistics
        from organizations.models import Department, Organization

        params = {
            "stichtag": request.query_params.get("date") or "",
            "alter": request.query_params.get("ages") or "",
            "zaehlung": request.query_params.get("counting") or "",
        }
        with org_context(self.org):
            if self.unit is not None:
                src = statistics.department_source(Department.objects.get(pk=self.unit.pk))
            elif self.org.type == Organization.Type.FEDERATION:
                src = statistics.federation_source(self.org)
            else:
                src = statistics.club_source(self.org)
            data = census.census(src, params)
        out = {
            "date": data["stichtag"],
            "ages": data["alter"],
            "counting": data["zaehlung"],
            "gender_labels": data["gender_labels"],
            "total": data["total"],
            "persons": data["persons"],
            "organizations": data["organizations"],
            "rows": data["rows"],
            "genders": data["genders"],
            "groups_title": str(data["groups_title"] or ""),
            "groups": [{**g, "id": str(g["id"])} for g in data["groups"]],
        }
        return Response(PartnerCensusSerializer(out).data)


# --- Vorstand ---


class PartnerHolderSerializer(serializers.Serializer):
    name = serializers.CharField()


class PartnerBoardRoleSerializer(serializers.Serializer):
    role = serializers.CharField()
    email = serializers.CharField(allow_blank=True)
    holders = PartnerHolderSerializer(many=True)


class PartnerBoardSerializer(serializers.Serializer):
    names_published = serializers.BooleanField(
        help_text="Namen stehen nur dabei, wenn die Webseite der Einheit öffentlich ist"
    )
    roles = PartnerBoardRoleSerializer(many=True)


class BoardView(PartnerView):
    scope = sc.BOARD_READ

    @extend_schema(
        operation_id="board",
        summary="Vorstand und Ämter",
        description=(
            "Rollen mit „auf der Webseite zeigen“ und ihre Funktionsadresse. Namen der "
            "Amtsinhaber nur, soweit sie auf der öffentlichen Webseite der Einheit stehen "
            "(Einwilligung der Person)."
        ),
        responses={200: PartnerBoardSerializer, **ERRORS},
    )
    def get(self, request):
        from access.models import Role

        site = self.site(request)
        roles = []
        if site is not None and site.site.block_on("board"):
            with rls_bypass():
                for entry in site.board():
                    roles.append(
                        {
                            "role": entry.get("role") or entry.get("name") or "",
                            "email": entry.get("email") or "",
                            "holders": [
                                {"name": h["name"]}
                                for h in entry.get("holders", [])
                                if h.get("name")
                            ],
                        }
                    )
            published = True
        else:
            with org_context(self.org):
                for r in Role.objects.filter(
                    organization=self.org, department__isnull=True, on_website=True
                ).order_by("position", "name"):
                    roles.append({"role": r.name, "email": r.contact_email or "", "holders": []})
            published = False
        return Response(PartnerBoardSerializer({"names_published": published, "roles": roles}).data)


# --- Ergebnisse ---


class PartnerCompetitionSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    date = serializers.DateField()
    occasion = serializers.CharField(allow_blank=True)
    discipline = serializers.CharField(allow_blank=True)
    location = serializers.CharField(allow_blank=True)
    own = serializers.BooleanField(help_text="von der Einheit selbst ausgerichtet")
    organizer = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    final = serializers.BooleanField()


class PartnerCompetitionListSerializer(serializers.Serializer):
    published = serializers.BooleanField(
        help_text="false: Die Einheit veröffentlicht keine Ergebnisse auf ihrer Webseite"
    )
    competitions = PartnerCompetitionSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class PartnerResultRowSerializer(serializers.Serializer):
    place = serializers.IntegerField(allow_null=True)
    name = serializers.CharField(allow_blank=True)
    value = serializers.CharField(allow_blank=True)
    prize = serializers.BooleanField()
    unit = serializers.CharField(required=False, allow_blank=True)
    club = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)
    out_of_competition = serializers.BooleanField(required=False)


class PartnerScoringSerializer(serializers.Serializer):
    name = serializers.CharField()
    kind = serializers.CharField()
    unit_label = serializers.CharField(allow_blank=True)
    field = serializers.IntegerField(allow_null=True, help_text="Größe des Teilnehmerfelds")
    complete = serializers.BooleanField(help_text="false: nur die Preisplätze")
    rows = PartnerResultRowSerializer(many=True)


class PartnerTitleSerializer(serializers.Serializer):
    title = serializers.CharField(allow_blank=True)
    name = serializers.CharField(allow_blank=True)


class PartnerCompetitionDetailSerializer(PartnerCompetitionSerializer):
    description = serializers.CharField(allow_blank=True)
    scorings = PartnerScoringSerializer(many=True)
    titles = PartnerTitleSerializer(many=True)


def _competition(summary: dict) -> dict:
    keys = ("id", "title", "date", "occasion", "discipline", "location", "own", "organizer")
    return {
        **{k: summary.get(k) for k in keys},
        "status": summary["status"],
        "final": summary["final"],
    }


class ResultsView(PartnerView):
    scope = sc.RESULTS_READ

    @extend_schema(
        operation_id="results",
        summary="Veröffentlichte Wettbewerbe",
        description=(
            "Wettbewerbe, die auf der öffentlichen Webseite der Einheit stehen, neueste zuerst."
        ),
        parameters=[
            LIMIT,
            OpenApiParameter(
                "cursor", OpenApiTypes.STR, description="``next_cursor`` der Seite davor"
            ),
        ],
        responses={200: PartnerCompetitionListSerializer, 400: PartnerProblemSerializer, **ERRORS},
    )
    def get(self, request):
        from website import results

        site = self.site(request)
        rows, cursor, on = [], None, False
        if site is not None:
            with rls_bypass():
                on = results.enabled(site)
                if on:
                    chunk, cursor = _page(results.published(site), request)
                    rows = [_competition(results.summary(site, c)) for c in chunk]
        data = {"published": on, "competitions": rows, "next_cursor": cursor}
        return Response(PartnerCompetitionListSerializer(data).data)


class ResultDetailView(PartnerView):
    scope = sc.RESULTS_READ

    @extend_schema(
        operation_id="result",
        summary="Rangliste eines Wettbewerbs",
        description=(
            "Wertungen im selben Umfang wie auf der Webseite der Einheit: Namen nur mit "
            "Einwilligung, je nach Einstellung nur Einheiten und Mannschaften oder nur die "
            "Preisplätze."
        ),
        responses={
            200: PartnerCompetitionDetailSerializer,
            404: PartnerProblemSerializer,
            **ERRORS,
        },
    )
    def get(self, request, competition_id: str):
        from website import results

        site = self.site(request)
        if site is None:
            raise Http404
        with rls_bypass():
            comp = results.find(site, competition_id) if results.enabled(site) else None
            if comp is None:
                raise Http404
            detail = results.detail(site, comp)
        data = {
            **_competition(detail),
            "description": detail.get("description") or "",
            "scorings": [
                {
                    "name": s["name"],
                    "kind": s["kind"],
                    "unit_label": s.get("unit_label") or "",
                    "field": s.get("field"),
                    "complete": s["complete"],
                    "rows": [
                        {
                            **{
                                k: r[k]
                                for k in ("unit", "club", "note", "out_of_competition")
                                if r.get(k)
                            },
                            "place": r.get("place"),
                            "name": r.get("name") or "",
                            "value": r.get("value") or "",
                            "prize": bool(r.get("prize")),
                        }
                        for r in s["rows"]
                    ],
                }
                for s in detail["scorings"]
            ],
            "titles": [
                {"title": t.get("title") or "", "name": t.get("name") or ""}
                for t in detail["titles"]
            ],
        }
        return Response(PartnerCompetitionDetailSerializer(data).data)


# --- Beiträge ---


class PartnerPostImageSerializer(serializers.Serializer):
    url = serializers.CharField()
    small_url = serializers.CharField()
    width = serializers.IntegerField(allow_null=True)
    height = serializers.IntegerField(allow_null=True)


class PartnerPostSerializer(serializers.Serializer):
    id = serializers.CharField()
    kind = serializers.CharField(help_text="instagram oder facebook")
    account = serializers.CharField(allow_blank=True)
    text = serializers.CharField(allow_blank=True)
    published_at = serializers.DateTimeField()
    permalink = serializers.CharField(allow_null=True)
    images = PartnerPostImageSerializer(many=True)


class PartnerPostListSerializer(serializers.Serializer):
    published = serializers.BooleanField(
        help_text="false: Die Einheit zeigt keine Beiträge auf ihrer Webseite"
    )
    posts = PartnerPostSerializer(many=True)


class NewsView(PartnerView):
    scope = sc.NEWS_READ

    @extend_schema(
        operation_id="news",
        summary="Beiträge",
        description=(
            "Neueste Beiträge aus den eigenen Kanälen der Einheit, soweit sie auf ihrer "
            "öffentlichen Webseite stehen. Bilder liefert die HUBIplan-Instanz aus."
        ),
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="1 bis 50, Vorgabe 12")
        ],
        responses={200: PartnerPostListSerializer, 400: PartnerProblemSerializer, **ERRORS},
    )
    def get(self, request):
        site = self.site(request)
        on = site is not None and site.site.block_on("posts")
        posts = []
        if on:
            with rls_bypass():
                for p in site.posts(None, None, _limit(request, 12, MAX_POSTS)):
                    posts.append(
                        {
                            "id": p["id"],
                            "kind": p["kind"],
                            "account": p.get("account") or "",
                            "text": p.get("text") or "",
                            "published_at": p["published_at"],
                            "permalink": p.get("permalink"),
                            "images": [
                                {
                                    "url": i["url"],
                                    "small_url": i["small_url"],
                                    "width": i.get("width"),
                                    "height": i.get("height"),
                                }
                                for i in p.get("images", [])
                            ],
                        }
                    )
        return Response(PartnerPostListSerializer({"published": on, "posts": posts}).data)


# --- Dokumente ---


class PartnerDocumentSerializer(serializers.Serializer):
    id = serializers.CharField()
    section = serializers.ChoiceField(choices=["documents", "press"])
    title = serializers.CharField()
    source = serializers.CharField(allow_blank=True)
    date = serializers.DateField(allow_null=True)
    kind = serializers.ChoiceField(choices=["pdf", "image"])
    url = serializers.CharField()
    preview_url = serializers.CharField(allow_null=True)
    size = serializers.IntegerField(allow_null=True)


class PartnerDocumentListSerializer(serializers.Serializer):
    published = serializers.BooleanField(
        help_text="false: Die Einheit veröffentlicht keine Dokumente auf ihrer Webseite"
    )
    documents = PartnerDocumentSerializer(many=True)


class DocumentsView(PartnerView):
    scope = sc.DOCUMENTS_READ

    @extend_schema(
        operation_id="documents",
        summary="Öffentliche Dokumente",
        description=(
            "Dokumente und Presseberichte, die auf der öffentlichen Webseite der Einheit "
            "stehen. ``url`` ist die öffentliche Adresse der Datei."
        ),
        responses={200: PartnerDocumentListSerializer, **ERRORS},
    )
    def get(self, request):
        from website import documents

        site = self.site(request)
        rows = []
        on = False
        if site is not None:
            with rls_bypass():
                for section, block in (("documents", "statutes"), ("press", "press")):
                    if not site.site.block_on(block):
                        continue
                    on = True
                    for d in documents.public_list(site, section):
                        rows.append({**d, "section": section})
        return Response(PartnerDocumentListSerializer({"published": on, "documents": rows}).data)
