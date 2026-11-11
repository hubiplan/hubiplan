"""Geschäftspartner: Liste, Akte, Ansprechpartner, Zusammenführen, Excel (Konzept P1).

Recht: ``partners.view``/``partners.edit``. Wer Kasse oder Beiträge führt, darf die Liste
weiter lesen und pflegen (Rechnungen und Eingang brauchen sie). Bank, Standardkategorie,
Zahlungsziel und Künstlerkennzeichen sieht und ändert nur, wer Kassen- oder Beitragsrechte
hat (GP-3).
"""

from __future__ import annotations

import io

from django.db import transaction
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from access.catalog import (
    BILLING_EDIT,
    BILLING_VIEW,
    FINANCE_EDIT,
    FINANCE_VIEW,
    PARTNERS_EDIT,
    PARTNERS_VIEW,
)
from audit.log import diff, record, snapshot
from core.api_base import AuditMixin, OrgScopedMixin

from .models import BusinessPartner, PartnerContact
from .sepa import iban_valid

ORG_TYPES = ("club", "federation", "unit")
MONEY_VIEW = {FINANCE_VIEW, BILLING_VIEW}
MONEY_EDIT = {FINANCE_EDIT, BILLING_EDIT}
MONEY_FIELDS = ("bank", "default_category", "payment_terms_days", "artist")


class PartnerDetailsSerializer(serializers.Serializer):
    """Angaben wie bei der E-Rechnung, aber nur der Name ist Pflicht. Für eine Rechnung
    prüft ``einvoice_schema.PartySerializer`` später vollständig."""

    name = serializers.CharField(max_length=200)
    street = serializers.CharField(max_length=200, allow_blank=True, default="")
    postcode = serializers.CharField(max_length=20, allow_blank=True, default="")
    city = serializers.CharField(max_length=100, allow_blank=True, default="")
    country = serializers.RegexField(r"^[A-Z]{2}$", default="DE")
    email = serializers.EmailField(allow_blank=True, default="")
    phone = serializers.CharField(max_length=50, allow_blank=True, default="")
    website = serializers.URLField(max_length=300, allow_blank=True, default="")
    vat_id = serializers.CharField(max_length=40, allow_blank=True, default="")
    tax_number = serializers.CharField(max_length=40, allow_blank=True, default="")
    contact = serializers.CharField(max_length=100, allow_blank=True, default="")
    identifier = serializers.CharField(max_length=100, allow_blank=True, default="")
    leitweg_id = serializers.CharField(max_length=100, allow_blank=True, default="")
    endpoint_id = serializers.CharField(max_length=100, allow_blank=True, default="")
    endpoint_scheme = serializers.RegexField(r"^(EM|[0-9]{4})$", default="EM")

    def validate(self, attrs):
        if attrs.get("endpoint_scheme", "EM") != "EM" and not attrs.get("endpoint_id"):
            raise serializers.ValidationError(gettext("Bitte die elektronische Adresse angeben."))
        if attrs.get("endpoint_scheme", "EM") == "EM" and attrs.get("endpoint_id"):
            serializers.EmailField().run_validation(attrs["endpoint_id"])
        attrs["vat_id"] = attrs.get("vat_id", "").replace(" ", "").upper()
        return attrs


class BankSerializer(serializers.Serializer):
    iban = serializers.CharField(max_length=42, allow_blank=True, default="")
    bic = serializers.CharField(max_length=11, allow_blank=True, default="")
    holder = serializers.CharField(max_length=200, allow_blank=True, default="")

    def validate_iban(self, value):
        value = value.replace(" ", "").upper()
        if value and not iban_valid(value):
            raise serializers.ValidationError(gettext("Die IBAN ist ungültig."))
        return value

    def validate_bic(self, value):
        return value.replace(" ", "").upper()


class PartnerContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnerContact
        fields = [
            "id",
            "last_name",
            "first_name",
            "function",
            "email",
            "phone",
            "is_primary",
            "receives_invoices",
            "receives_mail",
            "notes",
        ]


def can_see_money(perms) -> bool:
    return bool(MONEY_VIEW & set(perms))


def can_edit_money(perms) -> bool:
    return bool(MONEY_EDIT & set(perms))


class PartnerSerializer(serializers.ModelSerializer):
    details = PartnerDetailsSerializer()
    bank = BankSerializer(required=False)
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=BusinessPartner.Role.choices),
        required=False,
        max_length=len(BusinessPartner.Role.choices),
    )
    contacts = PartnerContactSerializer(many=True, read_only=True)
    unit_name = serializers.SerializerMethodField()
    membership_name = serializers.SerializerMethodField()

    class Meta:
        model = BusinessPartner
        fields = [
            "id",
            "name",
            "kind",
            "roles",
            "number",
            "unit",
            "unit_name",
            "membership",
            "membership_name",
            "details",
            "bank",
            "our_customer_number",
            "default_category",
            "payment_terms_days",
            "artist",
            "notes",
            "website_consent",
            "website_url",
            "is_customer",
            "is_supplier",
            "is_active",
            "contacts",
            "updated_at",
        ]
        read_only_fields = ["id", "name", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        view = self.context.get("view")
        perms = getattr(view, "org_permissions", set())
        if not can_see_money(perms):
            for field in MONEY_FIELDS:
                self.fields.pop(field, None)
        elif not can_edit_money(perms):
            for field in MONEY_FIELDS:
                self.fields[field].read_only = True

    def get_unit_name(self, obj) -> str:
        return obj.unit.name if obj.unit_id else ""

    def get_membership_name(self, obj) -> str:
        if not obj.membership_id:
            return ""
        person = obj.membership.person
        return " ".join(p for p in (person.first_name, person.last_name) if p)

    def validate_roles(self, value):
        return sorted(set(value))

    def validate_unit(self, unit):
        org = self.context["view"].org
        if unit and unit.pk != org.pk and unit.organization_id != org.pk:
            raise serializers.ValidationError(gettext("Diese Einheit gehört nicht hierher."))
        return unit

    def validate_membership(self, membership):
        org = self.context["view"].org
        if membership and membership.organization_id != org.pk:
            raise serializers.ValidationError(gettext("Unbekannte Mitgliedschaft."))
        return membership

    def validate_default_category(self, category):
        org = self.context["view"].org
        if category and category.organization_id != org.pk:
            raise serializers.ValidationError(gettext("Unbekannte Kategorie."))
        return category

    def validate(self, attrs):
        if "details" in attrs:
            previous = self.instance.details if self.instance else {}
            details = PartnerDetailsSerializer(data={**previous, **attrs["details"]})
            details.is_valid(raise_exception=True)
            attrs["details"] = details.validated_data
            attrs["name"] = attrs["details"]["name"]
        elif not self.instance:
            raise serializers.ValidationError({"details": gettext("Bitte den Namen angeben.")})
        if "bank" in attrs:
            before = (self.instance.bank if self.instance else {}) or {}
            bank = dict(attrs["bank"])
            if bank.get("iban") != before.get("iban"):
                user = self.context["request"].user
                bank["changed_at"] = timezone.now().isoformat()
                bank["changed_by"] = user.get_full_name() or user.email
            else:
                bank["changed_at"] = before.get("changed_at", "")
                bank["changed_by"] = before.get("changed_by", "")
            attrs["bank"] = bank
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if "bank" in data and isinstance(instance.bank, dict):
            data["bank"] = {
                "iban": instance.bank.get("iban", ""),
                "bic": instance.bank.get("bic", ""),
                "holder": instance.bank.get("holder", ""),
                "changed_at": instance.bank.get("changed_at", ""),
                "changed_by": instance.bank.get("changed_by", ""),
            }
        return data


def next_number(org) -> str:
    """Fortlaufende Partnernummer „GP-0001“ (GP-12); bestehende Nummern bleiben."""
    highest = 0
    for number in BusinessPartner.objects.filter(organization=org).values_list("number", flat=True):
        prefix, _, digits = (number or "").rpartition("-")
        if prefix == "GP" and digits.isdigit():
            highest = max(highest, int(digits))
    return f"GP-{highest + 1:04d}"


class MenuSerializer(serializers.Serializer):
    partners_in_menu = serializers.BooleanField()


class PartnerAccess(OrgScopedMixin):
    read_permission = (PARTNERS_VIEW, BILLING_VIEW, FINANCE_VIEW)
    write_permission = (PARTNERS_EDIT, BILLING_EDIT, FINANCE_EDIT)
    allowed_org_types = ORG_TYPES


# Verweise, die beim Zusammenführen auf den bleibenden Partner wandern
def _references():
    from music.models import Performance

    from .models import Invoice

    refs = [(Invoice, "partner"), (Performance, "customer"), (PartnerContact, "partner")]
    refs += extra_references()
    return refs


def extra_references():
    """Verweise aus Kasse (P2), Rechnungseingang (P3), Vereinbarungen (P4) und Dokumenten (P5)."""
    from finance.models import BankLine, Booking, CashReceipt, Donation

    from .models import IncomingInvoice, PartnerAgreement, PartnerDocument

    return [
        (IncomingInvoice, "partner"),
        (PartnerAgreement, "partner"),
        (PartnerDocument, "partner"),
        (Booking, "partner"),
        (BankLine, "partner"),
        (CashReceipt, "partner"),
        (Donation, "partner"),
    ]


class PartnerViewSet(PartnerAccess, AuditMixin, viewsets.ModelViewSet):
    serializer_class = PartnerSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    pagination_class = None

    def get_queryset(self):
        return (
            BusinessPartner.objects.filter(organization=self.org)
            .select_related("unit", "membership__person")
            .prefetch_related("contacts")
        )

    def get_create_kwargs(self):
        return {"organization": self.org, "number": next_number(self.org)}

    def perform_create(self, serializer):
        with transaction.atomic():
            super().perform_create(serializer)
            instance = serializer.instance
            contact = (instance.details or {}).get("contact", "").strip()
            if contact:
                first, _, last = contact.rpartition(" ")
                PartnerContact.objects.create(
                    organization=self.org,
                    partner=instance,
                    first_name=first,
                    last_name=last or contact,
                    phone=(instance.details or {}).get("phone", ""),
                    is_primary=True,
                    receives_invoices=True,
                )

    def destroy(self, request, *args, **kwargs):
        partner = self.get_object()
        for model, field in _references():
            if model is PartnerContact:
                continue
            if model.objects.filter(**{field: partner}).exists():
                return Response(
                    {
                        "detail": gettext(
                            "Dieser Geschäftspartner wird noch verwendet (z. B. in Rechnungen "
                            "oder Buchungen). Bitte stattdessen auf „Inaktiv“ setzen."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": gettext("Dieser Geschäftspartner wird noch verwendet.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"])
    def merge(self, request, org_id, pk):
        """Einen doppelten Eintrag in diesen übernehmen (Verweise wandern mit)."""
        other_id = serializers.IntegerField(min_value=1).run_validation(request.data.get("other"))
        with transaction.atomic():
            keep = get_object_or_404(self.get_queryset().select_for_update(of=("self",)), pk=pk)
            other = get_object_or_404(
                self.get_queryset().select_for_update(of=("self",)), pk=other_id
            )
            if keep.pk == other.pk:
                raise serializers.ValidationError(gettext("Bitte zwei verschiedene Einträge."))
            moved = 0
            for model, field in _references():
                moved += model.objects.filter(**{field: other}).update(**{field: keep})
            keep.roles = sorted(set(keep.roles or []) | set(other.roles or []))
            details = {**(other.details or {}), **{k: v for k, v in keep.details.items() if v}}
            keep.details = details
            if not keep.bank and other.bank:
                keep.bank = other.bank
            if other.notes:
                keep.notes = "\n\n".join(p for p in (keep.notes, other.notes) if p)[:5000]
            keep.save()
            record(
                self.org,
                request.user,
                "update",
                keep,
                {"Zusammengeführt mit": [None, f"{other.number} {other.name}".strip()]},
            )
            record(self.org, request.user, "delete", other, diff(snapshot(other), {}))
            other.delete()
        # neu laden: die vorab geladenen Ansprechpartner kennen die übernommenen noch nicht
        keep = self.get_queryset().get(pk=keep.pk)
        return Response({**self.get_serializer(keep).data, "moved": moved})

    @action(detail=False, methods=["get"])
    def export(self, request, org_id):
        from openpyxl import Workbook

        money = can_see_money(self.org_permissions)
        book = Workbook()
        sheet = book.active
        sheet.title = gettext("Geschäftspartner")
        header = [
            gettext("Nummer"),
            gettext("Name"),
            gettext("Art"),
            gettext("Rollen"),
            gettext("Straße"),
            gettext("PLZ"),
            gettext("Ort"),
            gettext("Land"),
            gettext("E-Mail"),
            gettext("Telefon"),
            gettext("Webseite"),
            gettext("USt-IdNr."),
            gettext("Steuernummer"),
            gettext("Ansprechpartner"),
            gettext("Aktiv"),
        ]
        if money:
            header += [gettext("IBAN"), gettext("BIC"), gettext("Kontoinhaber")]
        sheet.append(header)
        roles = dict(BusinessPartner.Role.choices)
        kinds = dict(BusinessPartner.Kind.choices)
        for p in self.get_queryset():
            d = p.details or {}
            primary = next(iter(p.contacts.all()), None)
            row = [
                p.number,
                p.name,
                str(kinds.get(p.kind, p.kind)),
                ", ".join(str(roles.get(r, r)) for r in p.roles or []),
                d.get("street", ""),
                d.get("postcode", ""),
                d.get("city", ""),
                d.get("country", ""),
                d.get("email", ""),
                d.get("phone", ""),
                d.get("website", ""),
                d.get("vat_id", ""),
                d.get("tax_number", ""),
                str(primary) if primary else "",
                gettext("Ja") if p.is_active else gettext("Nein"),
            ]
            if money:
                b = p.bank or {}
                row += [b.get("iban", ""), b.get("bic", ""), b.get("holder", "")]
            sheet.append(row)
        out = io.BytesIO()
        book.save(out)
        response = HttpResponse(
            out.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="geschaeftspartner.xlsx"'
        response["Cache-Control"] = "private, no-store"
        record(self.org, request.user, "view", self.org, {"Export": [None, "Geschäftspartner"]})
        return response

    @action(detail=True, methods=["get"])
    def turnover(self, request, org_id, pk):
        """Einnahmen und Ausgaben je Geschäftsjahr mit diesem Partner (P2, nur Kasse)."""
        if not ("finance" in self.org.enabled_modules and FINANCE_VIEW in self.org_permissions):
            raise PermissionDenied(gettext("Dafür fehlt dir die Berechtigung."))
        from django.db.models import Count, Sum

        from finance.models import Booking

        partner = self.get_object()
        rows = (
            Booking.objects.filter(
                organization=self.org,
                partner=partner,
                cancels__isnull=True,
                cancellation__isnull=True,
            )
            .exclude(kind=Booking.Kind.TRANSFER)
            .values("year", "kind")
            .annotate(total=Sum("amount"), count=Count("pk"))
            .order_by("-year")
        )
        years: dict[int, dict] = {}
        for row in rows:
            entry = years.setdefault(
                row["year"], {"year": row["year"], "income": "0.00", "expense": "0.00", "count": 0}
            )
            entry[row["kind"]] = str(row["total"])
            entry["count"] += row["count"]
        recent = (
            Booking.objects.filter(organization=self.org, partner=partner)
            .select_related("organization")
            .order_by("-date", "-pk")[:10]
        )
        return Response(
            {
                "years": list(years.values()),
                "recent": [
                    {
                        "id": b.pk,
                        "number": b.display_number,
                        "date": b.date,
                        "kind": b.kind,
                        "amount": str(b.amount),
                        "text": b.text,
                    }
                    for b in recent
                ],
            }
        )

    @extend_schema(request=MenuSerializer, responses=MenuSerializer)
    @action(detail=False, methods=["post"])
    def menu(self, request, org_id):
        """``{partners_in_menu: bool}``: Geschäftspartner als eigenen Punkt oben im
        Hauptmenü zeigen statt unter Verein (gilt für alle in der Einheit)."""
        params = MenuSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        value = params.validated_data["partners_in_menu"]
        if value != self.org.partners_in_menu:
            record(
                self.org,
                request.user,
                "update",
                self.org,
                {
                    "Geschäftspartner im Hauptmenü": [
                        "ja" if not value else "nein",
                        "ja" if value else "nein",
                    ]
                },
            )
            self.org.partners_in_menu = value
            self.org.save(update_fields=["partners_in_menu"])
        return Response({"partners_in_menu": self.org.partners_in_menu})

    @action(detail=False, methods=["get", "post"])
    def mailing(self, request, org_id):
        """Serienbrief und E-Mail-Verteiler an eine Partnergruppe (P5)."""
        from .partner_files import mailing_get, mailing_post

        if request.method == "GET":
            return mailing_get(self, request)
        return mailing_post(self, request)

    @action(detail=False, methods=["get", "post"])
    def suggestions(self, request, org_id):
        """Bestand übernehmen (P2, GP-8): häufige Freitexte „Empfänger/Zahler“ ohne Partner.

        GET listet Vorschläge, POST ``{name, kind?, roles?}`` legt den Partner an und verknüpft
        Buchungen und Bankzeilen mit genau diesem Freitext. Nichts geschieht von selbst."""
        if not ("finance" in self.org.enabled_modules and FINANCE_VIEW in self.org_permissions):
            raise PermissionDenied(gettext("Dafür fehlt dir die Berechtigung."))
        from finance.models import BankLine, Booking

        known = {p.name.casefold() for p in BusinessPartner.objects.filter(organization=self.org)}
        bookings = Booking.objects.filter(organization=self.org, partner__isnull=True).exclude(
            counterparty=""
        )
        if request.method == "GET":
            names: dict[str, dict] = {}
            for name, membership in bookings.values_list("counterparty", "membership_id"):
                key = " ".join(name.split()).casefold()
                if not key or key in known or membership:
                    continue
                entry = names.setdefault(key, {"name": " ".join(name.split()), "count": 0})
                entry["count"] += 1
            result = sorted(
                (e for e in names.values() if e["count"] >= 2),
                key=lambda e: (-e["count"], e["name"].casefold()),
            )
            return Response(result[:100])
        if FINANCE_EDIT not in self.org_permissions:
            raise PermissionDenied(gettext("Dafür fehlt dir die Berechtigung."))
        name = serializers.CharField(max_length=200).run_validation(request.data.get("name"))
        name = " ".join(name.split())
        if name.casefold() in known:
            raise serializers.ValidationError(
                {"name": gettext("Einen Geschäftspartner mit diesem Namen gibt es schon.")}
            )
        kind = serializers.ChoiceField(
            choices=BusinessPartner.Kind.choices, default=BusinessPartner.Kind.COMPANY
        ).run_validation(request.data.get("kind", BusinessPartner.Kind.COMPANY))
        roles = serializers.ListField(
            child=serializers.ChoiceField(choices=BusinessPartner.Role.choices), default=list
        ).run_validation(request.data.get("roles", []))
        with transaction.atomic():
            partner = BusinessPartner(
                organization=self.org,
                name=name,
                details={"name": name, "country": "DE"},
                kind=kind,
                roles=sorted(set(roles)),
                number=next_number(self.org),
            )
            partner.save()
            record(self.org, request.user, "create", partner, diff({}, snapshot(partner)))
            needle = name.casefold()
            ids = [
                pk
                for pk, text in bookings.values_list("pk", "counterparty")
                if " ".join(text.split()).casefold() == needle
            ]
            linked = Booking.objects.filter(pk__in=ids).update(partner=partner)
            lines = [
                pk
                for pk, text in BankLine.objects.filter(
                    organization=self.org, partner__isnull=True
                ).values_list("pk", "name")
                if " ".join((text or "").split()).casefold() == needle
            ]
            BankLine.objects.filter(pk__in=lines).update(partner=partner)
            if linked:
                record(
                    self.org,
                    request.user,
                    "update",
                    partner,
                    {"Buchungen verknüpft": [None, linked]},
                )
        data = self.get_serializer(partner).data
        return Response({**data, "linked": linked}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="import")
    def import_file(self, request, org_id):
        """Excel mit Kopfzeile wie beim Export; Zeilen mit bekanntem Namen werden übersprungen.

        ``?probe=1`` zeigt nur, was passieren würde."""
        from openpyxl import load_workbook

        upload = request.FILES.get("file")
        if not upload or upload.size > 5 * 1024 * 1024:
            raise serializers.ValidationError({"file": gettext("Bitte eine Excel-Datei wählen.")})
        try:
            sheet = load_workbook(upload, read_only=True, data_only=True).active
            rows = list(sheet.iter_rows(values_only=True))
        except Exception as exc:  # noqa: BLE001 – jede kaputte Datei gleich melden
            raise serializers.ValidationError(
                {"file": gettext("Die Datei ist keine lesbare Excel-Datei.")}
            ) from exc
        if not rows:
            return Response({"created": 0, "skipped": 0, "errors": []})
        columns = {
            "nummer": "number",
            "number": "number",
            "name": "name",
            "straße": "street",
            "strasse": "street",
            "street": "street",
            "plz": "postcode",
            "postcode": "postcode",
            "ort": "city",
            "city": "city",
            "land": "country",
            "country": "country",
            "e-mail": "email",
            "email": "email",
            "telefon": "phone",
            "phone": "phone",
            "webseite": "website",
            "website": "website",
            "ust-idnr.": "vat_id",
            "vat id": "vat_id",
            "steuernummer": "tax_number",
            "tax number": "tax_number",
            "ansprechpartner": "contact",
            "contact": "contact",
            "art": "kind",
            "type": "kind",
            "rollen": "roles",
            "roles": "roles",
        }
        header = [columns.get(str(h or "").strip().casefold(), "") for h in rows[0]]
        if "name" not in header:
            raise serializers.ValidationError(
                {"file": gettext("Die erste Zeile braucht eine Spalte „Name“.")}
            )
        kind_by_label = {str(label).casefold(): v for v, label in BusinessPartner.Kind.choices}
        kind_by_label.update({v: v for v in BusinessPartner.Kind.values})
        role_by_label = {str(label).casefold(): v for v, label in BusinessPartner.Role.choices}
        role_by_label.update({v: v for v in BusinessPartner.Role.values})
        known = {p.name.casefold() for p in BusinessPartner.objects.filter(organization=self.org)}
        probe = request.query_params.get("probe") == "1"
        created, skipped, errors = 0, 0, []
        with transaction.atomic():
            number = next_number(self.org)
            counter = int(number.rpartition("-")[2])
            for index, raw in enumerate(rows[1:501], start=2):
                values = {
                    key: str(value).strip()
                    for key, value in zip(header, raw, strict=False)
                    if key and value not in (None, "")
                }
                name = values.get("name", "")
                if not name:
                    continue
                if name.casefold() in known:
                    skipped += 1
                    continue
                details = PartnerDetailsSerializer(
                    data={
                        k: values[k]
                        for k in (
                            "name",
                            "street",
                            "postcode",
                            "city",
                            "country",
                            "email",
                            "phone",
                            "website",
                            "vat_id",
                            "tax_number",
                            "contact",
                        )
                        if k in values
                    }
                )
                if not details.is_valid():
                    errors.append(
                        gettext("Zeile {index}: {error}").format(
                            index=index,
                            error="; ".join(
                                f"{k}: {' '.join(map(str, v))}" for k, v in details.errors.items()
                            ),
                        )
                    )
                    continue
                roles = sorted(
                    {
                        role_by_label[r.strip().casefold()]
                        for r in values.get("roles", "").split(",")
                        if r.strip().casefold() in role_by_label
                    }
                )
                known.add(name.casefold())
                created += 1
                if probe:
                    continue
                partner = BusinessPartner(
                    organization=self.org,
                    name=details.validated_data["name"],
                    details=details.validated_data,
                    kind=kind_by_label.get(values.get("kind", "").casefold(), "company"),
                    roles=roles,
                    number=values.get("number") or f"GP-{counter:04d}",
                    is_customer=not roles,
                )
                if not values.get("number"):
                    counter += 1
                partner.save()
                contact = details.validated_data.get("contact", "")
                if contact:
                    first, _, last = contact.rpartition(" ")
                    PartnerContact.objects.create(
                        organization=self.org,
                        partner=partner,
                        first_name=first,
                        last_name=last or contact,
                        is_primary=True,
                        receives_invoices=True,
                    )
            if probe:
                transaction.set_rollback(True)
            elif created:
                record(
                    self.org,
                    request.user,
                    "create",
                    self.org,
                    {"Import Geschäftspartner": [None, created]},
                )
        return Response({"created": created, "skipped": skipped, "errors": errors[:50]})


class PartnerContactViewSet(PartnerAccess, AuditMixin, viewsets.ModelViewSet):
    """Ansprechpartner eines Geschäftspartners: ``partners/{partner_pk}/contacts/``."""

    serializer_class = PartnerContactSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    pagination_class = None

    def partner(self):
        return get_object_or_404(
            BusinessPartner, organization=self.org, pk=self.kwargs["partner_pk"]
        )

    def get_queryset(self):
        return PartnerContact.objects.filter(organization=self.org, partner=self.partner())

    def get_create_kwargs(self):
        return {"organization": self.org, "partner": self.partner()}

    def _one_primary(self, instance):
        if instance.is_primary:
            PartnerContact.objects.filter(partner=instance.partner).exclude(pk=instance.pk).update(
                is_primary=False
            )

    def perform_create(self, serializer):
        with transaction.atomic():
            super().perform_create(serializer)
            self._one_primary(serializer.instance)

    def perform_update(self, serializer):
        with transaction.atomic():
            super().perform_update(serializer)
            self._one_primary(serializer.instance)


class PartnerLookupViewSet(PartnerAccess, viewsets.ReadOnlyModelViewSet):
    """Kontaktsuche für die App (P5): aktive Partner mit Ansprechpartnern, nur lesen.

    ``?suche=`` findet Name, Nummer, Ort und Ansprechpartner; höchstens 200 Treffer."""

    serializer_class = PartnerSerializer
    pagination_class = None
    LIMIT = 200

    def get_queryset(self):
        return (
            BusinessPartner.objects.filter(organization=self.org, is_active=True)
            .select_related("unit", "membership__person")
            .prefetch_related("contacts")
        )

    def list(self, request, *args, **kwargs):
        # Name ist verschlüsselt: sortieren in Python
        rows = sorted(self.get_queryset(), key=lambda p: (p.name.casefold(), p.pk))
        needle = request.query_params.get("suche", "").strip().casefold()
        if needle:
            rows = [p for p in rows if needle in _haystack(p)]
        return Response(self.get_serializer(rows[: self.LIMIT], many=True).data)


def _haystack(partner: BusinessPartner) -> str:
    details = partner.details or {}
    parts = [partner.name, partner.number, details.get("city", ""), details.get("email", "")]
    parts += [f"{c.first_name} {c.last_name} {c.function}" for c in partner.contacts.all()]
    return " ".join(p for p in parts if p).casefold()
