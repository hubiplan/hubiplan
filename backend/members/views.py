from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import (
    BILLING_VIEW,
    DATA_EXPORT,
    MEMBERS_EDIT,
    MEMBERS_VIEW,
    ORG_EDIT,
    SETTINGS_VIEW,
)
from accounts import step_up
from audit.log import diff, record, snapshot
from audit.models import AuditEntry
from changes import idempotency
from core.api_base import AuditMixin, OrgScopedMixin
from core.reorder import reorder_response
from organizations.models import Organization
from organizations.terms import fill

from . import services, type_usage
from .listing import filter_members, member_queryset, member_rows
from .models import (
    BillingAddress,
    ContactPerson,
    DepartmentMembership,
    DepartmentRoleHolder,
    FederationMember,
    Gender,
    Membership,
    MembershipPeriod,
    MemberType,
    Person,
    today,
)
from .serializers import (
    AdmitSerializer,
    BillingAddressSerializer,
    ContactPersonSerializer,
    DepartmentMembershipSerializer,
    DepartmentRoleHolderSerializer,
    DuplicateSerializer,
    MemberTypeSerializer,
    MemberUpdateSerializer,
    PeriodSerializer,
    member_detail,
)
from .summary import member_summary
from .update import update_member


class _ClubMixin(OrgScopedMixin):
    """Mitgliedschaften der Einheit selbst: im Verein und, wenn eingeschaltet,
    in der obersten Einheit (eigene Mitglieder des Dachverbands)."""

    allowed_org_types = (Organization.Type.CLUB, Organization.Type.FEDERATION)
    read_permission = MEMBERS_VIEW
    write_permission = MEMBERS_EDIT

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not self.org.keeps_members:
            raise NotFound(fill("{e_Nom} führt keine eigenen Mitglieder.", self.org))

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = getattr(self, "org", None)
        return ctx


class MemberTypeViewSet(_ClubMixin, AuditMixin, viewsets.ModelViewSet):
    """Mitgliedsarten des Vereins (lesen: Mitglieder lesen; ändern: Organisation)."""

    serializer_class = MemberTypeSerializer
    write_permission = ORG_EDIT
    read_permission = (SETTINGS_VIEW, MEMBERS_VIEW, BILLING_VIEW)

    def get_queryset(self):
        return MemberType.objects.filter(organization=self.org)

    def get_create_kwargs(self) -> dict:
        return {"organization": self.org}

    @action(detail=False, methods=["post"])
    def reorder(self, request, *args, **kwargs):
        return reorder_response(
            request, self.org, MemberType.objects.filter(organization=self.org), "sort_order"
        )

    @action(detail=True, methods=["get"])
    def usage(self, request, org_id: int, pk: int):
        """Vorschau: wird die Art gelöscht oder archiviert, und warum?"""
        member_type = self.get_object()
        found = type_usage.usages(member_type)
        return Response(
            {
                "deletable": not found,
                "reasons": [u.text for u in found],
                "is_archived": member_type.is_archived,
            }
        )

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """Löschen, wenn unbenutzt; sonst 409 mit Grund (dann archivieren)."""
        member_type = self.get_object()
        found = type_usage.usages(member_type)
        if found:
            return Response(
                {
                    "detail": gettext(
                        "„{name}“ wird noch verwendet und kann nur archiviert werden."
                    ).format(name=member_type.name),
                    "reasons": [u.text for u in found],
                    "can_archive": not member_type.is_archived,
                },
                status=status.HTTP_409_CONFLICT,
            )
        self.perform_destroy(member_type)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def archive(self, request, org_id: int, pk: int):
        return self._set_archived(True)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def restore(self, request, org_id: int, pk: int):
        return self._set_archived(False)

    def _set_archived(self, archived: bool):
        member_type = self.get_object()
        if member_type.is_archived != archived:
            member_type.is_archived = archived
            member_type.save(update_fields=["is_archived"])
            record(
                self.org,
                self.request.user,
                "update",
                member_type,
                {"archiviert": [not archived, archived]},
            )
        return Response(self.get_serializer(member_type).data)


# --- Mitgliederliste ---


class MemberPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class MemberListView(_ClubMixin, generics.GenericAPIView):
    pagination_class = MemberPagination

    @extend_schema(
        parameters=[
            OpenApiParameter("suche", str),
            OpenApiParameter("status", str, enum=["aktiv", "ehemalig", "alle"]),
            OpenApiParameter("art", int),
            OpenApiParameter("typ", str, enum=["person", "organisation"]),
            OpenApiParameter("geschlecht", str, enum=[*Gender.values, "ohne"]),
            OpenApiParameter("abteilung", int),
            OpenApiParameter("ehrentitel", str, description="Nummer oder „mit“ (beliebiger)"),
            OpenApiParameter("haushalt", str, description="Nummer, „mit“ oder „ohne“"),
            OpenApiParameter("sortierung", str),
        ]
    )
    def get(self, request, org_id: int):
        qs = filter_members(member_queryset(self.org), request.query_params, self.org, lazy=True)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(member_rows(page, self.org))


class DuplicateView(_ClubMixin, APIView):
    read_permission = MEMBERS_EDIT

    def get(self, request, org_id: int):
        params = request.query_params
        if params.get("typ") == "organisation":
            name = (params.get("name") or "").strip()
            found = (
                services.find_duplicates(self.org, name, "", None, organization=True)
                if name
                else []
            )
            return Response(DuplicateSerializer(found, many=True, context={"org": self.org}).data)
        if not params.get("geburtsdatum"):
            # Ohne Geburtsdatum nur eigene Mitglieder gleichen Namens zeigen
            found = services.club_namesakes(
                self.org, params.get("name", ""), params.get("vorname", "")
            )
            return Response(DuplicateSerializer(found, many=True, context={"org": self.org}).data)
        try:
            birth_date = serializers.DateField().to_internal_value(params.get("geburtsdatum"))
        except serializers.ValidationError:
            return Response([])
        found = services.find_duplicates(
            self.org, params.get("name", ""), params.get("vorname", ""), birth_date
        )
        return Response(DuplicateSerializer(found, many=True, context={"org": self.org}).data)


class AdmitView(_ClubMixin, APIView):
    @transaction.atomic
    def post(self, request, org_id: int):
        data = AdmitSerializer(data=request.data, context={"org": self.org})
        data.is_valid(raise_exception=True)
        # Dieselbe Aufnahme erneut gesendet: keine zweite Person anlegen
        claim = idempotency.claim(request, f"members.admit.{self.org.pk}")
        if claim.done:
            membership = get_object_or_404(
                Membership.objects.select_related("person"),
                organization=self.org,
                pk=claim.result.get("membership", 0),
            )
            return Response(member_detail(membership, self.org), status=status.HTTP_200_OK)
        # Vorhandene Person: gemeinsame Anschrift nicht überschreiben (Audit 02.11. GA-S01)
        membership = services.admit(self.org, data.validated_data, keep_contact=True)
        claim.remember({"membership": membership.pk})
        record(
            self.org,
            request.user,
            "create",
            membership,
            {"Mitgliedsart": [None, data.validated_data["member_type"].name]},
            person=membership.person,
        )
        return Response(member_detail(membership, self.org), status=status.HTTP_201_CREATED)


class MemberDetailView(_ClubMixin, APIView):
    def get_membership(self) -> Membership:
        return get_object_or_404(
            Membership.objects.select_related("person"),
            organization=self.org,
            pk=self.kwargs["pk"],
        )

    def get(self, request, org_id: int, pk: int):
        membership = self.get_membership()
        data = member_detail(membership, self.org)
        # Nur beim Aufruf der Akte, nicht bei jedem Speichern (S-03 A3)
        data["summary"] = member_summary(membership, self.org, self.org_permissions)
        return Response(data)

    @transaction.atomic
    def patch(self, request, org_id: int, pk: int):
        # Gesperrt und frisch gelesen: gleichzeitige Änderungen anderer Felder bleiben
        membership = get_object_or_404(
            Membership.objects.select_related("person").select_for_update(),
            organization=self.org,
            pk=self.kwargs["pk"],
        )
        data = MemberUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        if membership.managed_by_id:
            locked = sorted(
                set(data.validated_data)
                & {
                    "last_name",
                    "first_name",
                    "birth_date",
                    "gender",
                    "title",
                    *services.ORGANIZATION_FIELDS,
                    "size",
                    *services.CONTACT_FIELDS,
                }
            )
            if locked:
                raise serializers.ValidationError(
                    {
                        "detail": gettext(
                            "Stammdaten und Kontakt pflegt die ausgegliederte Untereinheit "
                            "auf ihrer "
                            "Instanz. Bitte eine Korrektur vorschlagen."
                        )
                    }
                )
        update_member(self.org, membership, data.validated_data, request.user)
        return Response(member_detail(membership, self.org))


class _MemberChildMixin(_ClubMixin):
    """Unterobjekte einer Mitgliedschaft (Zeiträume, Abteilungen, Rollen)."""

    child_model = None

    def get_membership(self) -> Membership:
        return get_object_or_404(Membership, organization=self.org, pk=self.kwargs["member_pk"])

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "org", None) is not None:
            ctx["membership"] = self.get_membership()
        return ctx

    def get_queryset(self):
        return self.child_model.objects.filter(
            organization=self.org, membership_id=self.kwargs["member_pk"]
        )

    def perform_create(self, serializer):
        membership = self.get_membership()
        instance = serializer.save(organization=self.org, membership=membership)
        record(
            self.org,
            self.request.user,
            "create",
            instance,
            diff({}, snapshot(instance)),
            person=membership.person,
        )

    def perform_update(self, serializer):
        before = snapshot(serializer.instance)
        instance = serializer.save()
        changes = diff(before, snapshot(instance))
        if changes:
            record(
                self.org,
                self.request.user,
                "update",
                instance,
                changes,
                person=instance.membership.person,
            )

    def perform_destroy(self, instance):
        record(
            self.org,
            self.request.user,
            "delete",
            instance,
            diff(snapshot(instance), {}),
            person=instance.membership.person,
        )
        instance.delete()


class PeriodViewSet(_MemberChildMixin, viewsets.ModelViewSet):
    """Zeiträume nachtragen (Altdaten) und korrigieren."""

    serializer_class = PeriodSerializer
    child_model = MembershipPeriod
    http_method_names = ["get", "post", "patch", "delete", "options", "head"]

    @transaction.atomic
    def perform_create(self, serializer):
        # Person sperren wie die Fach-Workflows: zwei Nachträge gleichzeitig prüfen nicht
        # beide gegen denselben alten Stand (Audit 31.10. M31-04, M31-R01)
        membership = self.get_membership()
        Person.objects.select_for_update().filter(pk=membership.person_id).first()
        Membership.objects.select_for_update().filter(pk=membership.pk).first()
        fresh = self.get_serializer(data=self.request.data)
        fresh.is_valid(raise_exception=True)
        super().perform_create(fresh)

    def perform_destroy(self, instance):
        if instance.membership.periods.count() <= 1:
            raise serializers.ValidationError(
                gettext("Der einzige Zeitraum kann nicht gelöscht werden.")
            )
        super().perform_destroy(instance)


class DepartmentMembershipViewSet(_MemberChildMixin, viewsets.ModelViewSet):
    serializer_class = DepartmentMembershipSerializer
    child_model = DepartmentMembership
    http_method_names = ["get", "post", "patch", "delete", "options", "head"]


class DepartmentRoleHolderViewSet(_MemberChildMixin, viewsets.ModelViewSet):
    # Mitgliederdatenpflege allein darf keine wirksamen Verwaltungsrollen vergeben.
    write_permission = "roles.edit"
    serializer_class = DepartmentRoleHolderSerializer
    child_model = DepartmentRoleHolder
    http_method_names = ["get", "post", "patch", "delete", "options", "head"]

    def perform_create(self, serializer):
        from access.terms import end_unit_predecessors

        if self.get_membership().person.is_organization:
            raise serializers.ValidationError(
                {"role": gettext("Ein Amt hat immer ein Mensch, keine Organisation.")}
            )
        end_previous = serializer.validated_data.get("end_previous", False)
        super().perform_create(serializer)
        holder = serializer.instance
        holder._ended = (
            end_unit_predecessors(holder, self.org, self.request.user) if end_previous else []
        )


class ContactPersonViewSet(_MemberChildMixin, viewsets.ModelViewSet):
    """Ansprechpartner eines Organisationsmitglieds (J2). Entfernen löscht die Zeile
    samt Kontaktangaben; eingefrorene Namen in Belegen bleiben (Konzept J-9)."""

    serializer_class = ContactPersonSerializer
    child_model = ContactPerson
    http_method_names = ["get", "post", "patch", "delete", "options", "head"]

    def get_queryset(self):
        return super().get_queryset().select_related("person")

    def _check_organization(self, membership):
        """Organisationen: Ansprechpartner. Personen: Erziehungsberechtigte, solange das
        Mitglied minderjährig ist (H4) oder schon welche hat (Online-Antrag B3)."""
        from .guardians import is_minor

        person = membership.person
        if person.is_organization:
            return
        if not is_minor(person) and not membership.contact_persons.exists():
            raise serializers.ValidationError(
                {
                    "detail": gettext(
                        "Erziehungsberechtigte gibt es nur bei minderjährigen Mitgliedern "
                        "(mit Geburtsdatum)."
                    )
                }
            )

    @staticmethod
    def _one_primary(instance):
        """Genau ein Hauptansprechpartner: der zuletzt gewählte bzw. der erste."""
        others = ContactPerson.objects.filter(membership_id=instance.membership_id).exclude(
            pk=instance.pk
        )
        if instance.is_primary:
            others.filter(is_primary=True).update(is_primary=False)
        elif not others.filter(is_primary=True).exists():
            instance.is_primary = True
            instance.save(update_fields=["is_primary"])

    @transaction.atomic
    def perform_create(self, serializer):
        membership = self.get_membership()
        self._check_organization(membership)
        Membership.objects.select_for_update().filter(pk=membership.pk).first()
        if serializer.validated_data.get("is_primary"):
            ContactPerson.objects.filter(membership=membership, is_primary=True).update(
                is_primary=False
            )
        super().perform_create(serializer)
        if not membership.person.is_organization:
            serializer.instance.is_guardian = True
            serializer.instance.save(update_fields=["is_guardian"])
        self._one_primary(serializer.instance)

    @transaction.atomic
    def perform_update(self, serializer):
        Membership.objects.select_for_update().filter(pk=serializer.instance.membership_id).first()
        if serializer.validated_data.get("is_primary"):
            ContactPerson.objects.filter(
                membership_id=serializer.instance.membership_id, is_primary=True
            ).exclude(pk=serializer.instance.pk).update(is_primary=False)
        super().perform_update(serializer)
        self._one_primary(serializer.instance)

    @transaction.atomic
    def perform_destroy(self, instance):
        membership_id, was_primary = instance.membership_id, instance.is_primary
        super().perform_destroy(instance)
        if was_primary:
            nxt = ContactPerson.objects.filter(membership_id=membership_id).order_by("pk").first()
            if nxt is not None:
                nxt.is_primary = True
                nxt.save(update_fields=["is_primary"])


class FederationEntrySerializer(serializers.Serializer):
    manual_entry_date = serializers.DateField(allow_null=True)


class BillingAddressView(_ClubMixin, APIView):
    """Abweichende Rechnungsanschrift einer Mitgliedschaft setzen oder entfernen (J3)."""

    @transaction.atomic
    def put(self, request, org_id: int, pk: int):
        membership = get_object_or_404(
            Membership.objects.select_related("person").select_for_update(),
            organization=self.org,
            pk=pk,
        )
        instance = BillingAddress.objects.filter(membership=membership).first()
        before = snapshot(instance) if instance else {}
        data = BillingAddressSerializer(instance, data=request.data, partial=instance is not None)
        data.is_valid(raise_exception=True)
        saved = data.save(organization=self.org, membership=membership)
        record(
            self.org,
            request.user,
            "update" if instance else "create",
            saved,
            diff(before, snapshot(saved)),
            person=membership.person,
        )
        return Response(member_detail(membership, self.org))

    @transaction.atomic
    def delete(self, request, org_id: int, pk: int):
        membership = get_object_or_404(
            Membership.objects.select_related("person"), organization=self.org, pk=pk
        )
        instance = BillingAddress.objects.filter(membership=membership).first()
        if instance is not None:
            record(
                self.org,
                request.user,
                "delete",
                instance,
                diff(snapshot(instance), {}),
                person=membership.person,
            )
            instance.delete()
            membership = Membership.objects.select_related("person").get(pk=membership.pk)
        return Response(member_detail(membership, self.org))


class FederationEntryView(_ClubMixin, APIView):
    """Eintritt in den Dachverband von Hand setzen (Altdaten)."""

    def patch(self, request, org_id: int, pk: int):
        membership = get_object_or_404(Membership, organization=self.org, pk=pk)
        fm = FederationMember.objects.filter(person=membership.person).first()
        if fm is None:
            raise serializers.ValidationError(
                gettext("Die Person ist (noch) kein Verbandsmitglied.")
            )
        data = FederationEntrySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        before = snapshot(fm)
        fm.manual_entry_date = data.validated_data["manual_entry_date"]
        fm.save()
        record(
            self.org,
            request.user,
            "update",
            fm,
            diff(before, snapshot(fm)),
            person=membership.person,
        )
        return Response(member_detail(membership, self.org))


class MemberHistoryView(_ClubMixin, APIView):
    """Reiter „Verlauf“: Änderungen an dieser Person in diesem Verein."""

    def get(self, request, org_id: int, pk: int):
        membership = get_object_or_404(Membership, organization=self.org, pk=pk)
        entries = AuditEntry.objects.filter(organization=self.org, person_id=membership.person_id)[
            :100
        ]
        from access.views import AuditEntrySerializer, change_set_map

        entries = list(entries)
        context = {"org": self.org, "change_sets": change_set_map(entries)}
        return Response(AuditEntrySerializer(entries, many=True, context=context).data)


class MemberDisclosureView(_ClubMixin, APIView):
    """Auskunft für dieses Mitglied als ZIP (Art. 15 DSGVO, Fachfrage 7 vom 31.10.b)."""

    read_permission = DATA_EXPORT

    def get(self, request, org_id: int, pk: int):
        from django.http import HttpResponse

        from .auskunft import build

        membership = get_object_or_404(
            Membership.objects.select_related("person"), organization=self.org, pk=pk
        )
        content = build(membership, self.org)
        record(
            self.org,
            request.user,
            "view",
            membership,
            {"Auskunft": [None, "als ZIP erstellt"]},
            person=membership.person,
        )
        name = f"auskunft-{membership.pk}-{timezone.localdate():%Y-%m-%d}.zip"
        response = HttpResponse(content, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response


class MemberHistoryErasureView(_ClubMixin, APIView):
    """Auf Wunsch des ehemaligen Mitglieds auch den Namen aus Chronik, Würden, Ehrungen und
    Wettbewerben entfernen (Fachfrage FQ12). Nur nach dem Löschen der Mitgliedsdaten."""

    write_permission = MEMBERS_EDIT

    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        step_up.require(request)
        from rest_framework.exceptions import ValidationError

        from .workflows import erase_history

        membership = get_object_or_404(
            Membership.objects.select_related("person", "organization").select_for_update(),
            organization=self.org,
            pk=pk,
        )
        if membership.purged_at is None:
            raise ValidationError(
                {
                    "detail": gettext(
                        "Erst die Daten des ehemaligen Mitglieds löschen, dann den Namen aus "
                        "der Chronik."
                    )
                }
            )
        counts = erase_history(membership)
        record(
            self.org,
            request.user,
            "update",
            membership,
            {"Chronik und Ehrungen": [None, "Name auf Wunsch entfernt"]},
            person=membership.person,
        )
        membership.refresh_from_db()
        return Response({**member_detail(membership, self.org), "erased": counts})


class MemberErasureView(_ClubMixin, APIView):
    """Löschung auf Verlangen eines ehemaligen Mitglieds vor Ablauf der Löschfrist.

    Wie nach der Frist: nur Name, Geburtsjahr und Zeiträume bleiben; Rechnungen und
    Buchungen bleiben wegen der Aufbewahrungspflicht. Steht danach auf der Löschliste."""

    write_permission = MEMBERS_EDIT

    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        step_up.require(request)
        from rest_framework.exceptions import ValidationError

        from .workflows import purge_due_date, purge_membership

        membership = get_object_or_404(
            Membership.objects.select_related("person", "organization").select_for_update(),
            organization=self.org,
            pk=pk,
        )
        last = membership.periods.order_by("-exit_date").first()
        if (
            purge_due_date(membership) is None
            or last is None
            or last.exit_date is None
            or last.exit_date > today()
        ):
            raise ValidationError(
                {
                    "detail": gettext(
                        "Löschen geht nur bei ehemaligen Mitgliedern nach dem Austritt."
                    )
                }
            )
        purge_membership(membership, after_deadline=True)
        # Nach dem Löschen protokollieren (das Löschen leert ältere Einträge zur Person)
        record(
            self.org,
            request.user,
            "delete",
            membership,
            {"Daten": [None, "auf Verlangen gelöscht"]},
            person=membership.person,
        )
        membership.refresh_from_db()
        return Response(member_detail(membership, self.org))
