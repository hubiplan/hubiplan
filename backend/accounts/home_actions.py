"""Schnellaktionen der Startseite wählen und ausblenden (Konzept S-04, Mein Konto).

Am Konto stehen nur Schlüssel: ``hidden`` blendet Aktionen des Vorschlags aus (``*`` den ganzen
Block), ``chosen`` hält je Arbeitsbereich (``o<id>`` Einheit, ``d<id>`` Untereinheit) die eigene
Auswahl in ihrer Reihenfolge. Welche Aktionen es gibt und welche Rechte sie brauchen, steht im
Frontend (components/home/roleActions.ts); fremde Schlüssel zeigt es einfach nicht.
Während einer Ansicht als Rolle sperrt access/preview.py das Speichern.
"""

import re

from django.utils.translation import gettext
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

ACTION_KEY = re.compile(r"^(\*|[a-z0-9_-]{1,40})$")
CHOICE_KEY = re.compile(r"^[a-z0-9_-]{1,40}$")
SCOPE_KEY = re.compile(r"^[od][0-9]{1,10}$")
MAX_HIDDEN = 50
# Mehr Arbeitsbereiche hat kaum jemand; die Grenze hält das Feld klein.
MAX_SCOPES = 30
# Gezeigt werden höchstens sechs (Frontend MAX_ACTIONS), gespeichert etwas Luft
MAX_CHOSEN = 12


def hidden_keys(user) -> list[str]:
    keys = user.home_actions_hidden or []
    return sorted({k for k in keys if isinstance(k, str) and ACTION_KEY.match(k)})


def _clean_list(keys) -> list[str]:
    seen: list[str] = []
    for k in keys if isinstance(keys, list) else []:
        if isinstance(k, str) and CHOICE_KEY.match(k) and k not in seen:
            seen.append(k)
    return seen[:MAX_CHOSEN]


def chosen_keys(user) -> dict[str, list[str]]:
    data = user.home_actions if isinstance(user.home_actions, dict) else {}
    return {
        scope: _clean_list(keys)
        for scope, keys in sorted(data.items())
        if isinstance(scope, str) and SCOPE_KEY.match(scope)
    }


class HomeActionsSerializer(serializers.Serializer):
    hidden = serializers.ListField(
        child=serializers.RegexField(ACTION_KEY), max_length=MAX_HIDDEN, allow_empty=True
    )
    chosen = serializers.DictField(
        child=serializers.ListField(
            child=serializers.RegexField(CHOICE_KEY),
            max_length=MAX_CHOSEN,
            allow_empty=True,
            allow_null=True,
        ),
        required=False,
        help_text="Je Arbeitsbereich die eigene Auswahl in Reihenfolge; null = wieder Vorschlag",
    )

    def validate_chosen(self, value):
        if any(not SCOPE_KEY.match(k) for k in value):
            raise serializers.ValidationError(gettext("Unbekannter Arbeitsbereich."))
        return value


class HomeActionsWriteSerializer(HomeActionsSerializer):
    # Ältere Fassungen schicken nur „hidden“, neuere auch nur „chosen“
    hidden = serializers.ListField(
        child=serializers.RegexField(ACTION_KEY),
        max_length=MAX_HIDDEN,
        allow_empty=True,
        required=False,
    )


def _payload(user) -> dict:
    return {"hidden": hidden_keys(user), "chosen": chosen_keys(user)}


class HomeActionsView(APIView):
    """GET: Auswahl und ausgeblendete Schnellaktionen · PUT: Teile ersetzen.

    ``hidden`` ersetzt die Liste ganz; in ``chosen`` ersetzt jeder genannte Bereich seine
    Auswahl, ``null`` stellt dort wieder den Vorschlag her, nicht genannte Bereiche bleiben.
    """

    @extend_schema(responses=HomeActionsSerializer)
    def get(self, request):
        return Response(_payload(request.user))

    @extend_schema(request=HomeActionsWriteSerializer, responses=HomeActionsSerializer)
    def put(self, request):
        data = HomeActionsWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = request.user
        fields = []
        if "hidden" in data.validated_data:
            user.home_actions_hidden = sorted(set(data.validated_data["hidden"])) or None
            fields.append("home_actions_hidden")
        if "chosen" in data.validated_data:
            chosen = chosen_keys(user)
            for scope, keys in data.validated_data["chosen"].items():
                if keys is None:
                    chosen.pop(scope, None)
                else:
                    chosen[scope] = _clean_list(keys)
            if len(chosen) > MAX_SCOPES:
                raise serializers.ValidationError({"chosen": gettext("Zu viele Arbeitsbereiche.")})
            user.home_actions = chosen or None
            fields.append("home_actions")
        if fields:
            user.save(update_fields=fields)
        return Response(_payload(user))
