"""Schnittstelle Zahler und Familien-/Firmenbeitrag (Konzept Familien, Haushalte und
Firmen, H2/H3). Rechte wie bei Beiträgen (``billing.view``/``billing.edit``).

- ``billing/households/<id>/payer/``  GET, PUT (Zahler), DELETE (kein Zahler mehr)
- ``billing/household-fee-rules/``    GET beide Regeln (Familie, Firma), PUT eine Regel
"""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import diff, record, snapshot
from members.models import Household, Membership
from organizations.models import Organization

from .models import BusinessPartner, HouseholdFeeRule, HouseholdPayer, Mandate
from .serializers import MandateSerializer
from .views import BillingMixin


class HouseholdPayerSerializer(serializers.ModelSerializer):
    membership_name = serializers.SerializerMethodField()
    partner_name = serializers.CharField(source="partner.name", read_only=True, default="")

    class Meta:
        model = HouseholdPayer
        fields = [
            "kind",
            "membership",
            "membership_name",
            "partner",
            "partner_name",
            "name",
            "attention",
            "street",
            "postal_code",
            "city",
            "country",
            "email",
            "order_reference",
            "leitweg_id",
        ]
        extra_kwargs = {
            "membership": {"queryset": Membership.objects.all(), "required": False},
            "partner": {"queryset": BusinessPartner.objects.all(), "required": False},
        }

    def get_membership_name(self, obj) -> str:
        if obj.membership_id is None:
            return ""
        return obj.membership.person.display_name

    def validate(self, attrs):
        org = self.context["org"]
        kind = attrs.get("kind")
        membership = attrs.get("membership")
        partner = attrs.get("partner")
        if membership is not None and membership.organization_id != org.pk:
            raise serializers.ValidationError({"membership": gettext("Unbekanntes Mitglied.")})
        if partner is not None and partner.organization_id != org.pk:
            raise serializers.ValidationError({"partner": gettext("Unbekannter Geschäftspartner.")})
        if kind in (HouseholdPayer.Kind.MEMBER, HouseholdPayer.Kind.ORGANIZATION):
            if membership is None:
                raise serializers.ValidationError(
                    {"membership": gettext("Bitte ein Mitglied wählen.")}
                )
            is_org = membership.person.is_organization
            if is_org != (kind == HouseholdPayer.Kind.ORGANIZATION):
                raise serializers.ValidationError(
                    {
                        "membership": gettext(
                            "Für eine Organisation bitte „Organisationsmitglied“ wählen, "
                            "sonst „Mitglied“."
                        )
                    }
                )
            attrs["partner"] = None
        elif kind == HouseholdPayer.Kind.PARTNER:
            if partner is None:
                raise serializers.ValidationError(
                    {"partner": gettext("Bitte einen Geschäftspartner wählen.")}
                )
            attrs["membership"] = None
        else:
            if not (attrs.get("name") or "").strip():
                raise serializers.ValidationError({"name": gettext("Bitte einen Namen angeben.")})
            attrs["membership"] = None
            attrs["partner"] = None
        return attrs


class HouseholdFeeRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = HouseholdFeeRule
        fields = [
            "kind",
            "mode",
            "amount",
            "min_persons",
            "adult_required",
            "second_percent",
            "third_percent",
        ]

    def validate(self, attrs):
        mode = attrs.get("mode", HouseholdFeeRule.Mode.NONE)
        if mode in (HouseholdFeeRule.Mode.CAP, HouseholdFeeRule.Mode.FLAT):
            amount = attrs.get("amount")
            if amount is None or amount <= 0:
                raise serializers.ValidationError(
                    {"amount": gettext("Bitte einen Betrag größer als 0 angeben.")}
                )
        for key in ("second_percent", "third_percent"):
            value = attrs.get(key)
            if value is not None and not (0 <= value <= 100):
                raise serializers.ValidationError(
                    {key: gettext("Bitte einen Wert zwischen 0 und 100 angeben.")}
                )
        if mode == HouseholdFeeRule.Mode.STAGGER and not (
            attrs.get("second_percent") or attrs.get("third_percent")
        ):
            raise serializers.ValidationError(
                {"second_percent": gettext("Bitte mindestens eine Ermäßigung angeben.")}
            )
        return attrs


class HouseholdPayerView(BillingMixin, APIView):
    """Zahler eines Haushalts bzw. einer Firma, mit seinen Mandaten."""

    allowed_org_types = (Organization.Type.CLUB,)

    def _household(self, pk: int) -> Household:
        return get_object_or_404(Household, organization=self.org, pk=pk)

    def _data(self, household: Household) -> dict:
        payer = HouseholdPayer.objects.filter(household=household).first()
        mandates = Mandate.objects.filter(organization=self.org, household=household).order_by(
            "-signed_on", "-pk"
        )
        if payer is not None and payer.membership_id:
            # Zahlendes Mitglied: dessen eigene Mandate gelten
            mandates = Mandate.objects.filter(
                organization=self.org, membership_id=payer.membership_id
            ).order_by("-signed_on", "-pk")
        return {
            "household": household.pk,
            "payer": HouseholdPayerSerializer(payer).data if payer else None,
            "mandates": MandateSerializer(
                mandates.select_related("membership__person", "club", "household"), many=True
            ).data,
        }

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, org_id: int, pk: int):
        return Response(self._data(self._household(pk)))

    @extend_schema(request=HouseholdPayerSerializer, responses={200: OpenApiTypes.OBJECT})
    @transaction.atomic
    def put(self, request, org_id: int, pk: int):
        household = self._household(pk)
        payer = HouseholdPayer.objects.filter(household=household).first()
        ser = HouseholdPayerSerializer(payer, data=request.data, context={"org": self.org})
        ser.is_valid(raise_exception=True)
        before = snapshot(payer) if payer else {}
        payer = ser.save(organization=self.org, household=household)
        record(
            self.org,
            request.user,
            "update" if before else "create",
            payer,
            diff(before, snapshot(payer)),
        )
        return Response(self._data(household))

    @extend_schema(responses={204: None})
    @transaction.atomic
    def delete(self, request, org_id: int, pk: int):
        household = self._household(pk)
        payer = HouseholdPayer.objects.filter(household=household).first()
        if payer is not None:
            record(self.org, request.user, "delete", payer, diff(snapshot(payer), {}))
            payer.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class HouseholdFeeRulesView(BillingMixin, APIView):
    """Familien- und Firmenbeitrag (je eine Regel)."""

    allowed_org_types = (Organization.Type.CLUB,)

    def _data(self) -> list[dict]:
        rules = {r.kind: r for r in HouseholdFeeRule.objects.filter(organization=self.org)}
        result = []
        for kind in Household.Kind.values:
            rule = rules.get(kind)
            if rule is not None:
                result.append(HouseholdFeeRuleSerializer(rule).data)
                continue
            result.append(
                {
                    "kind": kind,
                    "mode": HouseholdFeeRule.Mode.NONE,
                    "amount": None,
                    "min_persons": 2,
                    "adult_required": False,
                    "second_percent": "0.00",
                    "third_percent": "0.00",
                }
            )
        return result

    @extend_schema(responses={200: HouseholdFeeRuleSerializer(many=True)})
    def get(self, request, org_id: int):
        return Response(self._data())

    @extend_schema(
        request=HouseholdFeeRuleSerializer, responses={200: HouseholdFeeRuleSerializer(many=True)}
    )
    @transaction.atomic
    def put(self, request, org_id: int):
        kind = request.data.get("kind") if isinstance(request.data, dict) else None
        if kind not in Household.Kind.values:
            raise serializers.ValidationError({"kind": gettext("Bitte Familie oder Firma wählen.")})
        rule = HouseholdFeeRule.objects.filter(organization=self.org, kind=kind).first()
        ser = HouseholdFeeRuleSerializer(rule, data=request.data, context={"org": self.org})
        ser.is_valid(raise_exception=True)
        before = snapshot(rule) if rule else {}
        rule = ser.save(organization=self.org)
        record(
            self.org,
            request.user,
            "update" if before else "create",
            rule,
            diff(before, snapshot(rule)),
        )
        return Response(self._data())
