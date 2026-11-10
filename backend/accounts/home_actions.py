"""Startseite zusammenstellen: Schnellaktionen und Blöcke (Konzept S-04, Mein Konto).

Am Konto stehen nur Schlüssel: ``hidden`` blendet Aktionen des Vorschlags aus (``*`` den ganzen
Block), ``chosen`` hält je Arbeitsbereich (``o<id>`` Einheit, ``d<id>`` Untereinheit) die eigene
Auswahl in ihrer Reihenfolge. ``layout`` hält je Arbeitsbereich die Anordnung der Blöcke
(``order``, ausgeblendete ``hidden``, über die ganze Breite ``wide``, Größe ``sizes``).
Welche Aktionen und Blöcke es gibt und welche Rechte sie brauchen, steht im Frontend
(components/home/roleActions.ts, components/home/homeLayout.ts); fremde Schlüssel zeigt es
einfach nicht.
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
# Die Startseite hat weniger als zehn Blöcke; etwas Luft für spätere
MAX_BLOCKS = 20
LAYOUT_PARTS = ("order", "hidden", "wide")
# Raster der Startseite: 12 Spalten, Höhe in Rasterzeilen (je 0,5 rem); None = nach Inhalt
GRID_COLUMNS = 12
MIN_COLUMNS = 3
MIN_ROWS = 6
MAX_ROWS = 300


def hidden_keys(user) -> list[str]:
    keys = user.home_actions_hidden or []
    return sorted({k for k in keys if isinstance(k, str) and ACTION_KEY.match(k)})


def _clean_list(keys, limit: int = MAX_CHOSEN) -> list[str]:
    seen: list[str] = []
    for k in keys if isinstance(keys, list) else []:
        if isinstance(k, str) and CHOICE_KEY.match(k) and k not in seen:
            seen.append(k)
    return seen[:limit]


def _clean_blocks(keys) -> list[str]:
    return _clean_list(keys, MAX_BLOCKS)


def _clean_sizes(value) -> dict[str, dict]:
    sizes: dict[str, dict] = {}
    for key, size in (value if isinstance(value, dict) else {}).items():
        if len(sizes) >= MAX_BLOCKS:
            break
        if not (isinstance(key, str) and CHOICE_KEY.match(key) and isinstance(size, dict)):
            continue
        w, h = size.get("w"), size.get("h")
        if not isinstance(w, int) or isinstance(w, bool):
            continue
        w = max(MIN_COLUMNS, min(GRID_COLUMNS, w))
        if isinstance(h, int) and not isinstance(h, bool):
            h = max(MIN_ROWS, min(MAX_ROWS, h))
        else:
            h = None
        sizes[key] = {"w": w, "h": h}
    return sizes


def _clean_layout(value: dict) -> dict:
    layout = {part: _clean_blocks(value.get(part)) for part in LAYOUT_PARTS}
    layout["sizes"] = _clean_sizes(value.get("sizes"))
    return layout


def layout_of(user) -> dict[str, dict]:
    data = user.home_layout if isinstance(user.home_layout, dict) else {}
    return {
        scope: _clean_layout(value)
        for scope, value in sorted(data.items())
        if isinstance(scope, str) and SCOPE_KEY.match(scope) and isinstance(value, dict)
    }


def chosen_keys(user) -> dict[str, list[str]]:
    data = user.home_actions if isinstance(user.home_actions, dict) else {}
    return {
        scope: _clean_list(keys)
        for scope, keys in sorted(data.items())
        if isinstance(scope, str) and SCOPE_KEY.match(scope)
    }


def _block_list():
    return serializers.ListField(
        child=serializers.RegexField(CHOICE_KEY), max_length=MAX_BLOCKS, default=list
    )


class BlockSizeSerializer(serializers.Serializer):
    w = serializers.IntegerField(min_value=MIN_COLUMNS, max_value=GRID_COLUMNS)
    h = serializers.IntegerField(
        min_value=MIN_ROWS, max_value=MAX_ROWS, allow_null=True, required=False, default=None
    )


class HomeLayoutSerializer(serializers.Serializer):
    order = _block_list()
    hidden = _block_list()
    # Ältere Fassungen kennen nur „wide“ (ganze Breite); neuere schreiben beides
    wide = _block_list()
    sizes = serializers.DictField(
        child=BlockSizeSerializer(),
        default=dict,
        help_text="Je Block Breite w (Spalten von 12), Höhe h (Rasterzeilen, null = nach Inhalt)",
    )

    def validate_sizes(self, value):
        if len(value) > MAX_BLOCKS or any(not CHOICE_KEY.match(k) for k in value):
            raise serializers.ValidationError(gettext("Unbekannter Block."))
        return value


def _check_scopes(value):
    if any(not SCOPE_KEY.match(k) for k in value):
        raise serializers.ValidationError(gettext("Unbekannter Arbeitsbereich."))
    return value


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
    layout = serializers.DictField(
        child=HomeLayoutSerializer(allow_null=True),
        required=False,
        help_text="Je Arbeitsbereich die Anordnung der Blöcke; null = wieder Standard",
    )

    def validate_chosen(self, value):
        return _check_scopes(value)

    def validate_layout(self, value):
        return _check_scopes(value)


class HomeActionsWriteSerializer(HomeActionsSerializer):
    # Ältere Fassungen schicken nur „hidden“, neuere auch nur „chosen“
    hidden = serializers.ListField(
        child=serializers.RegexField(ACTION_KEY),
        max_length=MAX_HIDDEN,
        allow_empty=True,
        required=False,
    )


def _payload(user) -> dict:
    return {"hidden": hidden_keys(user), "chosen": chosen_keys(user), "layout": layout_of(user)}


class HomeActionsView(APIView):
    """GET: Schnellaktionen und Anordnung der Startseite · PUT: Teile ersetzen.

    ``hidden`` ersetzt die Liste ganz; in ``chosen`` und ``layout`` ersetzt jeder genannte
    Bereich seinen Stand, ``null`` stellt dort wieder Vorschlag bzw. Standard her, nicht
    genannte Bereiche bleiben.
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
        if "layout" in data.validated_data:
            layout = layout_of(user)
            for scope, value in data.validated_data["layout"].items():
                if value is None:
                    layout.pop(scope, None)
                else:
                    layout[scope] = _clean_layout(value)
            if len(layout) > MAX_SCOPES:
                raise serializers.ValidationError({"layout": gettext("Zu viele Arbeitsbereiche.")})
            user.home_layout = layout or None
            fields.append("home_layout")
        if fields:
            user.save(update_fields=fields)
        return Response(_payload(user))
