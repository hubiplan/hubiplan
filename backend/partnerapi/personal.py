"""Personendaten in der API für andere Programme (docs/api.md, Stufe 2).

Verbandsmeldung, Mitglieder, Ehrungen und Qualifikationen, nur lesen. Personendaten gibt es
nur, wenn am Zugang ein Empfänger aus den Geschäftspartnern steht und die Rechtsgrundlage
bestätigt ist. Jeder Abruf steht im Abrufprotokoll der Einheit. Nie enthalten: Bankdaten,
Bemerkungen, Fotos, Zusatzfelder, Rollen und Mitgliedschaften nach Ablauf der Löschfrist.
"""

from __future__ import annotations

import datetime

from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from changes import tracking
from core.tenancy import org_context

from . import refs
from . import scopes as sc
from .auth import Problem
from .models import ApiAccess, ReadLog
from .views import (
    CURSOR,
    ERRORS,
    LIMIT,
    PartnerProblemSerializer,
    PartnerView,
    _moment,
    _page,
)

ADULT = 18
FIELD_CONTACT = "contact"
FIELD_MEMBERSHIP = "membership"
FIELD_UNITS = "units"
MEMBER_FIELDS = (FIELD_CONTACT, FIELD_MEMBERSHIP, FIELD_UNITS)

UNIT = OpenApiParameter(
    "unit", OpenApiTypes.UUID, description="nur diese Untereinheit und die darunter"
)
CHANGED = OpenApiParameter(
    "changed_since", OpenApiTypes.DATETIME, description="nur seitdem geänderte Datensätze"
)


def legal_missing() -> Problem:
    return Problem(
        403,
        "legal_basis_missing",
        _("Für Personendaten fehlen Empfänger oder Rechtsgrundlage"),
        _(
            "Die Einheit trägt in HUBIplan unter Einstellungen › API-Zugänge den Empfänger ein "
            "und bestätigt die Rechtsgrundlage."
        ),
    )


def log_read(access: ApiAccess, scope: str, count: int) -> None:
    """Abruf von Personendaten festhalten (leere Antworten nicht)."""
    if count <= 0:
        return
    with tracking.suppress():
        ReadLog.objects.create(
            organization=access.organization, access=access, scope=scope, count=count
        )


def _age(birth: datetime.date, on: datetime.date) -> int:
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def _current(periods, on: datetime.date):
    return next(
        (p for p in periods if p.entry_date <= on and (p.exit_date is None or p.exit_date >= on)),
        None,
    )


class PersonalView(PartnerView):
    """Ansichten mit Personendaten: zusätzlich Empfänger und Rechtsgrundlage prüfen."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method == "OPTIONS":
            return
        if not self.access.personal_ok:
            raise legal_missing()

    # --- Welche Mitgliedschaften darf der Zugang sehen? ---

    def wanted_unit(self, request):
        from organizations.models import Department

        raw = request.query_params.get("unit")
        if not raw:
            return None
        try:
            unit = Department.objects.filter(
                organization=self.org, uuid=raw, is_active=True
            ).first()
        except (ValueError, TypeError, serializers.DjangoValidationError):
            unit = None
        if unit is None:
            raise Http404
        return unit

    def memberships(self, request, *, status: str = "active", since=None):
        """Mitgliedschaften nach den Grenzen des Zugangs, in fester Reihenfolge. Aufrufer
        steht im Datenbereich der Einheit."""
        from members.models import Membership
        from organizations.tree import subtree_ids

        on = timezone.localdate()
        if self.access.only_active:
            status = "active"
        qs = Membership.objects.filter(organization=self.org, purged_at__isnull=True)
        current = Q(periods__entry_date__lte=on) & (
            Q(periods__exit_date__isnull=True) | Q(periods__exit_date__gte=on)
        )
        if status == "active":
            qs = qs.filter(current)
        elif status == "former":
            qs = qs.exclude(
                pk__in=Membership.objects.filter(current, organization=self.org).values("pk")
            ).filter(periods__exit_date__lt=on)
        for unit in (self.unit, self.wanted_unit(request)):
            if unit is None:
                continue
            qs = qs.filter(
                Q(department_memberships__department_id__in=subtree_ids(unit))
                & Q(department_memberships__valid_from__lte=on)
                & (
                    Q(department_memberships__valid_until__isnull=True)
                    | Q(department_memberships__valid_until__gte=on)
                )
            )
        if since is not None:
            qs = qs.filter(
                Q(updated_at__gte=since)
                | Q(person__updated_at__gte=since)
                | Q(person__contacts__updated_at__gte=since)
            )
        items = list(qs.distinct().order_by("pk").select_related("person"))
        if self.access.adults_only:
            items = [m for m in items if self._adult(m.person, on)]
        return items

    @staticmethod
    def _adult(person, on: datetime.date) -> bool:
        if person.is_organization:
            return True
        # Ohne Geburtsdatum lässt sich die Volljährigkeit nicht belegen: nicht herausgeben
        return bool(person.birth_date) and _age(person.birth_date, on) >= ADULT

    def visible_persons(self, request) -> dict[int, object]:
        """Person → Mitgliedschaft, für Ehrungen und Qualifikationen."""
        return {m.person_id: m for m in self.memberships(request, status="all")}


# --- Verbandsmeldung ---


class PartnerReportCountSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["active", "passive"])
    birth_month = serializers.CharField(allow_blank=True, help_text="JJJJ-MM, leer: unbekannt")
    count = serializers.IntegerField()


class PartnerReportPersonSerializer(serializers.Serializer):
    id = serializers.UUIDField(help_text="Kennung des Mitglieds wie unter /members/")
    last_name = serializers.CharField()
    first_name = serializers.CharField(allow_blank=True)
    birth_date = serializers.DateField(allow_null=True)
    federation_number = serializers.IntegerField(allow_null=True)
    member_type = serializers.CharField()
    active = serializers.BooleanField()
    entry_date = serializers.DateField(allow_null=True)


class PartnerFederationReportSerializer(serializers.Serializer):
    date = serializers.DateField()
    level = serializers.CharField(help_text="a: nur Zahlen, b: namentlich")
    total = serializers.IntegerField()
    counts = PartnerReportCountSerializer(many=True)
    persons = PartnerReportPersonSerializer(many=True, required=False)


class FederationReportView(PartnerView):
    scope = sc.REPORT_READ

    @extend_schema(
        operation_id="federation_report",
        summary="Verbandsmeldung zum Stichtag",
        description=(
            "Mitgliedschaften mit einer Mitgliedsart „an Dachverband melden“ am Stichtag: "
            "Anzahlen nach aktiv, passiv und Geburtsmonat. ``persons`` gibt es nur, wenn die "
            "Einheit am Zugang „namentlich“ gewählt, den Empfänger benannt und die "
            "Rechtsgrundlage bestätigt hat: Name, Vorname, Geburtsdatum, Verbandsnummer, "
            "Mitgliedsart und Eintritt, nie Anschrift oder Kontakt."
        ),
        parameters=[
            OpenApiParameter("date", OpenApiTypes.DATE, description="Stichtag, Vorgabe heute")
        ],
        responses={
            200: PartnerFederationReportSerializer,
            400: PartnerProblemSerializer,
            **ERRORS,
        },
    )
    def get(self, request):
        from django.utils.dateparse import parse_date

        from peering.packet_members import _current as reported

        raw = request.query_params.get("date")
        on = timezone.localdate()
        if raw:
            try:
                on = parse_date(raw)
            except ValueError:
                on = None
            if on is None:
                raise serializers.ValidationError({"date": _("Datum nach ISO 8601 erwartet.")})
        named = self.access.report_level == ApiAccess.ReportLevel.NAMES
        if named and not self.access.personal_ok:
            raise legal_missing()
        with org_context(self.org):
            data = self._report(on, named, reported(self.org, on))
        return Response(PartnerFederationReportSerializer(data).data)

    def _report(self, on, named: bool, rows) -> dict:
        counts: dict[tuple[str, str], int] = {}
        for m, member_type in rows:
            kind = "active" if member_type.active else "passive"
            birth = m.person.birth_date.strftime("%Y-%m") if m.person.birth_date else ""
            counts[(kind, birth)] = counts.get((kind, birth), 0) + 1
        data = {
            "date": on,
            "level": self.access.report_level,
            "total": len(rows),
            "counts": [
                {"kind": kind, "birth_month": birth, "count": n}
                for (kind, birth), n in sorted(counts.items())
            ],
        }
        if named:
            from members.models import FederationMember

            ids = refs.public_ids(self.org, refs.MEMBER, [m.pk for m, _t in rows])
            numbers = dict(
                FederationMember.objects.filter(
                    person_id__in=[m.person_id for m, _t in rows]
                ).values_list("person_id", "member_number")
            )
            persons = []
            for m, member_type in rows:
                period = _current(list(m.periods.all()), on)
                persons.append(
                    {
                        "id": ids[m.pk],
                        "last_name": m.person.last_name,
                        "first_name": m.person.first_name or "",
                        "birth_date": m.person.birth_date,
                        "federation_number": numbers.get(m.person_id),
                        "member_type": member_type.name,
                        "active": member_type.active,
                        "entry_date": period.entry_date if period else None,
                    }
                )
            data["persons"] = persons
            log_read(self.access, self.scope, len(persons))
        return data


# --- Mitglieder ---


class PartnerMemberContactSerializer(serializers.Serializer):
    email = serializers.CharField(allow_blank=True)
    phone = serializers.CharField(allow_blank=True)
    street = serializers.CharField(allow_blank=True)
    postal_code = serializers.CharField(allow_blank=True)
    city = serializers.CharField(allow_blank=True)
    country = serializers.CharField(allow_blank=True)


class PartnerMemberPeriodSerializer(serializers.Serializer):
    entry_date = serializers.DateField()
    exit_date = serializers.DateField(allow_null=True)
    exit_reason = serializers.CharField(
        allow_blank=True, help_text="transfer (Wechsel in anderen Verein) oder other"
    )


class PartnerMemberTypeSerializer(serializers.Serializer):
    name = serializers.CharField()
    active = serializers.BooleanField()
    reported = serializers.BooleanField(help_text="wird an den Dachverband gemeldet")


class PartnerMemberMembershipSerializer(serializers.Serializer):
    entry_date = serializers.DateField(allow_null=True, help_text="erster Eintritt")
    exit_date = serializers.DateField(allow_null=True, help_text="Austritt, sonst null")
    member_type = PartnerMemberTypeSerializer(allow_null=True)
    federation_number = serializers.IntegerField(allow_null=True)
    periods = PartnerMemberPeriodSerializer(many=True)


class PartnerMemberUnitSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    since = serializers.DateField()


class PartnerMemberSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField(help_text="person oder organization")
    last_name = serializers.CharField(help_text="bei Organisationen ihr Name")
    first_name = serializers.CharField(allow_blank=True)
    title = serializers.CharField(allow_blank=True)
    gender = serializers.CharField(allow_blank=True)
    birth_date = serializers.DateField(allow_null=True)
    birth_year = serializers.IntegerField(allow_null=True)
    member_number = serializers.CharField(allow_blank=True)
    status = serializers.ChoiceField(choices=["active", "upcoming", "former"])
    updated_at = serializers.DateTimeField()
    contact = PartnerMemberContactSerializer(
        required=False, help_text="nur mit der Feldgruppe „Kontakt und Anschrift“"
    )
    membership = PartnerMemberMembershipSerializer(
        required=False, help_text="nur mit der Feldgruppe „Mitgliedschaft“"
    )
    units = PartnerMemberUnitSerializer(
        many=True, required=False, help_text="nur mit der Feldgruppe „Untereinheiten“"
    )


class PartnerMemberListSerializer(serializers.Serializer):
    members = PartnerMemberSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


def _member_rows(view: PersonalView, memberships: list) -> list[dict]:
    """Ausgabe je Mitgliedschaft mit den Feldgruppen des Zugangs."""
    from members.models import ExitReason, FederationMember, Membership
    from members.services import contact_for

    if not memberships:
        return []
    on = timezone.localdate()
    groups = set(view.access.member_fields or [])
    org = view.org
    loaded = {
        m.pk: m
        for m in Membership.objects.filter(pk__in=[m.pk for m in memberships])
        .select_related("person")
        .prefetch_related(
            "periods",
            "type_assignments__member_type",
            "department_memberships__department",
            "person__contacts",
        )
    }
    ids = refs.public_ids(org, refs.MEMBER, list(loaded))
    numbers: dict[int, int] = {}
    if FIELD_MEMBERSHIP in groups:
        numbers = dict(
            FederationMember.objects.filter(
                person_id__in=[m.person_id for m in loaded.values()]
            ).values_list("person_id", "member_number")
        )
    rows = []
    for entry in memberships:
        m = loaded.get(entry.pk)
        if m is None:
            continue
        person = m.person
        periods = sorted(m.periods.all(), key=lambda p: p.entry_date)
        current = _current(periods, on)
        if current is not None:
            status = "active"
        elif any(p.entry_date > on for p in periods):
            status = "upcoming"
        else:
            status = "former"
        contact = contact_for(person, org)
        changed = [m.updated_at, person.updated_at]
        if contact is not None:
            changed.append(contact.updated_at)
        birth = person.birth_date
        row = {
            "id": ids[m.pk],
            "kind": person.kind,
            "last_name": person.last_name,
            "first_name": person.first_name or "",
            "title": person.title or "",
            "gender": person.gender or "",
            "birth_date": birth if birth and not person.birth_year_only else None,
            "birth_year": birth.year if birth else None,
            "member_number": m.club_number,
            "status": status,
            "updated_at": max(changed),
        }
        if FIELD_CONTACT in groups:
            row["contact"] = {
                "email": (contact.email if contact else "") or "",
                "phone": (contact.phone if contact else "") or "",
                "street": (contact.street if contact else "") or "",
                "postal_code": contact.postal_code if contact else "",
                "city": contact.city if contact else "",
                "country": contact.country if contact else "",
            }
        if FIELD_MEMBERSHIP in groups:
            types = sorted(m.type_assignments.all(), key=lambda t: t.valid_from)
            assignment = next(
                (
                    t
                    for t in types
                    if t.valid_from <= on and (t.valid_until is None or t.valid_until >= on)
                ),
                types[-1] if types else None,
            )
            last = periods[-1] if periods else None
            row["membership"] = {
                "entry_date": periods[0].entry_date if periods else None,
                "exit_date": last.exit_date if last and current is None else None,
                "member_type": {
                    "name": assignment.member_type.name,
                    "active": assignment.member_type.active,
                    "reported": assignment.member_type.reported,
                }
                if assignment
                else None,
                "federation_number": numbers.get(m.person_id),
                "periods": [
                    {
                        "entry_date": p.entry_date,
                        "exit_date": p.exit_date,
                        # Ausschluss, Streichung und Tod gehen nicht nach außen
                        "exit_reason": ""
                        if not p.exit_date
                        else ("transfer" if p.exit_reason == ExitReason.TRANSFER else "other"),
                    }
                    for p in periods
                ],
            }
        if FIELD_UNITS in groups:
            row["units"] = [
                {"id": d.department.uuid, "name": d.department.name, "since": d.valid_from}
                for d in sorted(m.department_memberships.all(), key=lambda d: d.valid_from)
                if d.valid_from <= on and (d.valid_until is None or d.valid_until >= on)
            ]
        rows.append(row)
    return rows


class MembersView(PersonalView):
    scope = sc.MEMBERS_READ

    @extend_schema(
        operation_id="members",
        summary="Mitglieder",
        description=(
            "Immer: Name, Vorname, Titel, Geschlecht, Geburtsdatum, Mitgliedsnummer und Zustand. "
            "``contact``, ``membership`` und ``units`` nur, wenn die Einheit die Feldgruppe am "
            "Zugang gewählt hat. Die Einheit kann den Zugang auf aktuelle Mitglieder und auf "
            "Volljährige begrenzen. Nie enthalten: Bankdaten, Bemerkungen, Fotos, Zusatzfelder, "
            "Rollen und Mitgliedschaften nach Ablauf der Löschfrist. ``changed_since`` findet "
            "Änderungen an Person, Kontakt und Mitgliedschaft; ein vollständiger Abgleich in "
            "größeren Abständen bleibt sinnvoll."
        ),
        parameters=[
            OpenApiParameter(
                "status",
                OpenApiTypes.STR,
                enum=["active", "former", "all"],
                description="Vorgabe active; former und all nur ohne die Begrenzung am Zugang",
            ),
            UNIT,
            CHANGED,
            LIMIT,
            CURSOR,
        ],
        responses={200: PartnerMemberListSerializer, 400: PartnerProblemSerializer, **ERRORS},
    )
    def get(self, request):
        status = request.query_params.get("status") or "active"
        if status not in ("active", "former", "all"):
            raise serializers.ValidationError({"status": _("active, former oder all erwartet.")})
        with org_context(self.org):
            items = self.memberships(
                request, status=status, since=_moment(request, "changed_since")
            )
            chunk, cursor = _page(items, request)
            rows = _member_rows(self, chunk)
            log_read(self.access, self.scope, len(rows))
        return Response(PartnerMemberListSerializer({"members": rows, "next_cursor": cursor}).data)


class MemberDetailView(PersonalView):
    scope = sc.MEMBERS_READ

    @extend_schema(
        operation_id="member",
        summary="Ein Mitglied",
        description="Wie ein Eintrag der Liste; 404, wenn der Zugang das Mitglied nicht sieht.",
        responses={200: PartnerMemberSerializer, 404: PartnerProblemSerializer, **ERRORS},
    )
    def get(self, request, member_id: str):
        with org_context(self.org):
            pk = refs.resolve(self.org, refs.MEMBER, member_id)
            items = [m for m in self.memberships(request, status="all") if m.pk == pk]
            rows = _member_rows(self, items)
            if not rows:
                raise Http404
            log_read(self.access, self.scope, 1)
        return Response(PartnerMemberSerializer(rows[0]).data)


# --- Ehrungen ---


class PartnerHonorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    member = serializers.UUIDField(help_text="Kennung des Mitglieds wie unter /members/")
    last_name = serializers.CharField()
    first_name = serializers.CharField(allow_blank=True)
    honor = serializers.CharField(help_text="Bezeichnung der Ehrung")
    title = serializers.CharField(allow_blank=True, help_text="besonderer Titel dieser Person")
    valid_from = serializers.DateField()
    valid_until = serializers.DateField(allow_null=True)


class PartnerHonorListSerializer(serializers.Serializer):
    honors = PartnerHonorSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class HonorsView(PersonalView):
    scope = sc.HONORS_READ

    @extend_schema(
        operation_id="honors",
        summary="Verliehene Ehrungen",
        description=(
            "Ehrungen, die die Einheit ihren Mitgliedern verliehen hat, mit Zeitraum. Es gelten "
            "die Begrenzungen des Zugangs (aktuelle Mitglieder, Volljährige, Untereinheit). "
            "Nie enthalten: Bemerkungen und Beitragsfolgen."
        ),
        parameters=[
            OpenApiParameter(
                "current", OpenApiTypes.BOOL, description="nur heute gültige Ehrungen"
            ),
            UNIT,
            LIMIT,
            CURSOR,
        ],
        responses={200: PartnerHonorListSerializer, 400: PartnerProblemSerializer, **ERRORS},
    )
    def get(self, request):
        from members.models import HonoraryTitleAward

        on = timezone.localdate()
        with org_context(self.org):
            visible = self.visible_persons(request)
            qs = HonoraryTitleAward.objects.filter(
                organization=self.org, person_id__in=list(visible)
            )
            if request.query_params.get("current") in ("1", "true"):
                qs = qs.filter(valid_from__lte=on).filter(
                    Q(valid_until__isnull=True) | Q(valid_until__gte=on)
                )
            items = list(qs.select_related("title", "person").order_by("valid_from", "pk"))
            chunk, cursor = _page(items, request)
            ids = refs.public_ids(self.org, refs.HONOR, [a.pk for a in chunk])
            members = refs.public_ids(
                self.org, refs.MEMBER, [visible[a.person_id].pk for a in chunk]
            )
            rows = [
                {
                    "id": ids[a.pk],
                    "member": members[visible[a.person_id].pk],
                    "last_name": a.person.last_name,
                    "first_name": a.person.first_name or "",
                    "honor": a.title.name,
                    "title": a.display_title,
                    "valid_from": a.valid_from,
                    "valid_until": a.valid_until,
                }
                for a in chunk
            ]
            log_read(self.access, self.scope, len(rows))
        return Response(PartnerHonorListSerializer({"honors": rows, "next_cursor": cursor}).data)


# --- Qualifikationen ---


class PartnerQualificationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    member = serializers.UUIDField(help_text="Kennung des Mitglieds wie unter /members/")
    last_name = serializers.CharField()
    first_name = serializers.CharField(allow_blank=True)
    qualification = serializers.CharField(help_text="Bezeichnung der Qualifikation")
    acquired_on = serializers.DateField()
    valid_until = serializers.DateField(allow_null=True)
    updated_at = serializers.DateTimeField()


class PartnerQualificationListSerializer(serializers.Serializer):
    qualifications = PartnerQualificationSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class QualificationsView(PersonalView):
    scope = sc.QUALIFICATIONS_READ

    @extend_schema(
        operation_id="qualifications",
        summary="Qualifikationen",
        description=(
            "Nachweise der Mitglieder mit Erwerb und Gültigkeit. Es gelten die Begrenzungen des "
            "Zugangs (aktuelle Mitglieder, Volljährige, Untereinheit). Nie enthalten: "
            "Bemerkungen und Arten, bei denen nur die Einsicht vermerkt wird (zum Beispiel "
            "das Führungszeugnis)."
        ),
        parameters=[
            OpenApiParameter("valid", OpenApiTypes.BOOL, description="nur heute gültige Nachweise"),
            UNIT,
            CHANGED,
            LIMIT,
            CURSOR,
        ],
        responses={
            200: PartnerQualificationListSerializer,
            400: PartnerProblemSerializer,
            **ERRORS,
        },
    )
    def get(self, request):
        from qualifications.models import Qualification

        on = timezone.localdate()
        with org_context(self.org):
            visible = self.visible_persons(request)
            qs = Qualification.objects.filter(
                organization=self.org, person_id__in=list(visible), kind__inspection_only=False
            )
            if request.query_params.get("valid") in ("1", "true"):
                qs = qs.filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on))
            since = _moment(request, "changed_since")
            if since is not None:
                qs = qs.filter(updated_at__gte=since)
            items = list(qs.select_related("kind", "person").order_by("pk"))
            chunk, cursor = _page(items, request)
            ids = refs.public_ids(self.org, refs.QUALIFICATION, [q.pk for q in chunk])
            members = refs.public_ids(
                self.org, refs.MEMBER, [visible[q.person_id].pk for q in chunk]
            )
            rows = [
                {
                    "id": ids[q.pk],
                    "member": members[visible[q.person_id].pk],
                    "last_name": q.person.last_name,
                    "first_name": q.person.first_name or "",
                    "qualification": q.kind.name,
                    "acquired_on": q.acquired_on,
                    "valid_until": q.valid_until,
                    "updated_at": q.updated_at,
                }
                for q in chunk
            ]
            log_read(self.access, self.scope, len(rows))
        return Response(
            PartnerQualificationListSerializer({"qualifications": rows, "next_cursor": cursor}).data
        )
