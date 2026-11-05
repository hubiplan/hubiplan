"""Explizites Eingabeschema für EN-16931-Rechnungsdaten (EUR)."""

from decimal import Decimal

from django.utils.translation import gettext
from rest_framework import serializers


class PartySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    street = serializers.CharField(max_length=200)
    postcode = serializers.CharField(max_length=20)
    city = serializers.CharField(max_length=100)
    country = serializers.RegexField(r"^[A-Z]{2}$", default="DE")
    email = serializers.EmailField()
    vat_id = serializers.CharField(max_length=40, allow_blank=True, default="")
    tax_number = serializers.CharField(max_length=40, allow_blank=True, default="")
    contact = serializers.CharField(max_length=100, allow_blank=True, default="")
    phone = serializers.CharField(max_length=50, allow_blank=True, default="")
    identifier = serializers.CharField(max_length=100, allow_blank=True, default="")
    endpoint_id = serializers.CharField(max_length=100, allow_blank=True, default="")
    endpoint_scheme = serializers.RegexField(r"^(EM|[0-9]{4})$", default="EM")

    def validate(self, attrs):
        if attrs.get("endpoint_scheme", "EM") != "EM" and not attrs.get("endpoint_id"):
            raise serializers.ValidationError(gettext("Bitte die elektronische Adresse angeben."))
        if attrs.get("endpoint_scheme", "EM") == "EM" and attrs.get("endpoint_id"):
            serializers.EmailField().run_validation(attrs["endpoint_id"])
        return attrs


class CommercialLineSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=200)
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=4, min_value=Decimal("0.0001")
    )
    unit = serializers.ChoiceField(
        choices=["C62", "HUR", "DAY", "MON", "KMT", "H87"], default="C62"
    )
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=6, min_value=0)
    allowance = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, default=Decimal("0")
    )
    charge = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, default=Decimal("0")
    )
    adjustment_reason = serializers.CharField(max_length=200, allow_blank=True, default="")
    tax_category = serializers.ChoiceField(choices=["S", "Z", "E", "AE", "O"])
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)
    tax_reason = serializers.CharField(max_length=300, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["tax_category"] == "S" and attrs["tax_rate"] <= 0:
            raise serializers.ValidationError(
                gettext("Für reguläre Umsatzsteuer ist ein positiver Steuersatz erforderlich.")
            )
        if attrs["tax_category"] != "S" and attrs["tax_rate"] != 0:
            raise serializers.ValidationError(
                gettext("Diese Steuerkategorie verlangt einen Steuersatz von null.")
            )
        if attrs["tax_category"] in ("E", "AE", "O") and not attrs["tax_reason"]:
            raise serializers.ValidationError(
                gettext("Bitte den Grund für die Steuerbefreiung oder Nichtsteuerbarkeit angeben.")
            )
        if attrs["tax_category"] in ("S", "Z") and attrs["tax_reason"]:
            raise serializers.ValidationError(
                gettext("Für diese Steuerkategorie ist kein Befreiungsgrund zulässig.")
            )
        if (attrs["allowance"] or attrs["charge"]) and not attrs["adjustment_reason"]:
            raise serializers.ValidationError(gettext("Bitte den Zu- oder Abschlag begründen."))
        if attrs["quantity"] * attrs["unit_price"] + attrs["charge"] < attrs["allowance"]:
            raise serializers.ValidationError(
                gettext("Der Abschlag übersteigt den Positionsbetrag.")
            )
        return attrs


class CommercialInvoiceSerializer(serializers.Serializer):
    document_kind = serializers.ChoiceField(
        choices=["invoice", "advance", "final"], default="invoice"
    )
    advance_invoices = serializers.ListField(
        child=serializers.IntegerField(min_value=1), max_length=20, default=list
    )
    partner = serializers.IntegerField(min_value=1)
    payment_category = serializers.IntegerField(min_value=1)
    date = serializers.DateField()
    due_date = serializers.DateField()
    subject = serializers.CharField(max_length=200)
    note = serializers.CharField(allow_blank=True, default="", max_length=5000)
    project = serializers.IntegerField(allow_null=True, default=None)
    seller = PartySerializer()
    buyer = PartySerializer()
    buyer_reference = serializers.CharField(max_length=200)
    order_reference = serializers.CharField(max_length=200, allow_blank=True, default="")
    service_start = serializers.DateField()
    service_end = serializers.DateField()
    iban = serializers.CharField(max_length=42)
    currency = serializers.ChoiceField(choices=["EUR"], default="EUR")
    lines = CommercialLineSerializer(many=True, allow_empty=False, max_length=200)

    def validate_iban(self, value):
        from .sepa import iban_valid

        value = value.replace(" ", "").upper()
        if not iban_valid(value):
            raise serializers.ValidationError(gettext("Die IBAN ist ungültig."))
        return value

    def validate(self, attrs):
        if attrs["due_date"] < attrs["date"]:
            raise serializers.ValidationError(gettext("Fällig vor dem Rechnungsdatum?"))
        if attrs["service_end"] < attrs["service_start"]:
            raise serializers.ValidationError(
                gettext("Das Leistungsende liegt vor dem Leistungsbeginn.")
            )
        seller = attrs["seller"]
        if not (seller["vat_id"] or seller["identifier"]):
            raise serializers.ValidationError(
                gettext(
                    "Ohne USt-IdNr. ist eine eindeutige Kennung des Rechnungsstellers erforderlich."
                )
            )
        if not seller["contact"] or not seller["phone"]:
            raise serializers.ValidationError(
                gettext(
                    "Für XRechnung fehlen Kontaktperson oder Telefonnummer des Rechnungsstellers."
                )
            )
        categories = {line["tax_category"] for line in attrs["lines"]}
        if "O" in categories and len(categories) > 1:
            raise serializers.ValidationError(
                gettext(
                    "Nicht steuerbare Positionen dürfen hier nicht mit anderen "
                    "Steuerkategorien kombiniert werden."
                )
            )
        if categories != {"O"} and not (seller["vat_id"] or seller["tax_number"]):
            raise serializers.ValidationError(
                gettext("Bitte Steuernummer oder USt-IdNr. des Rechnungsstellers angeben.")
            )
        if "O" in categories and (seller["vat_id"] or attrs["buyer"]["vat_id"]):
            raise serializers.ValidationError(
                gettext("Bei nicht steuerbaren Rechnungen dürfen keine USt-IdNr. angegeben werden.")
            )
        if "AE" in categories and not (seller["vat_id"] and attrs["buyer"]["vat_id"]):
            raise serializers.ValidationError(
                gettext(
                    "Bei Steuerschuldnerschaft des Empfängers sind beide USt-IdNr. erforderlich."
                )
            )
        return attrs
