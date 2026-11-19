"""Einstellungen des Buchungskalenders je Objekt (``MaterialItem.booking_rules``)."""

from django.utils.translation import gettext as _
from rest_framework import serializers

DEFAULTS = {
    "enabled": False,
    # Buchungen ohne Freigaberecht sind erst Anfragen
    "approval": False,
    "buffer_before": 0,
    "buffer_after": 0,
    # Wie weit im Voraus buchbar (Tage)
    "horizon_days": 365,
    # Webseite: aus, nur belegt/frei, mit Titel öffentlicher Buchungen
    "website": "off",
    # Mitglieder dürfen im Mitgliederbereich (Portal) anfragen
    "portal": False,
    # Mietpreis als Vorschlag für „Rechnung anlegen“ ("" = keiner): je Buchung, Tag oder Stunde
    "price": "",
    "price_unit": "booking",
}


def rules_of(item) -> dict:
    return {**DEFAULTS, **(item.booking_rules or {})}


def enabled(item) -> bool:
    return bool((item.booking_rules or {}).get("enabled"))


class RulesInput(serializers.Serializer):
    enabled = serializers.BooleanField()
    approval = serializers.BooleanField(required=False, default=False)
    buffer_before = serializers.IntegerField(min_value=0, max_value=1440, required=False, default=0)
    buffer_after = serializers.IntegerField(min_value=0, max_value=1440, required=False, default=0)
    horizon_days = serializers.IntegerField(
        min_value=1, max_value=1095, required=False, default=365
    )
    website = serializers.ChoiceField(
        choices=["off", "busy", "titles"], required=False, default="off"
    )
    portal = serializers.BooleanField(required=False, default=False)
    price = serializers.DecimalField(
        max_digits=9, decimal_places=2, min_value=0, required=False, allow_null=True
    )
    price_unit = serializers.ChoiceField(
        choices=["booking", "day", "hour"], required=False, default="booking"
    )

    def validate(self, data):
        if data["buffer_before"] % 5 or data["buffer_after"] % 5:
            raise serializers.ValidationError(_("Rüstzeiten bitte in Schritten von 5 Minuten."))
        # Als Text speichern (JSON); leer = kein Mietpreis
        price = data.get("price")
        data["price"] = "" if price is None else str(price)
        return data
