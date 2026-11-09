"""Schnellaktionen der Startseite ausblenden (Konzept S-04, Mein Konto).

Gespeichert werden nur die Schlüssel der ausgeblendeten Aktionen am Konto; ``*`` blendet den
ganzen Block aus. Welche Aktionen es gibt, steht im Frontend (components/home/roleActions.ts).
Während einer Ansicht als Rolle sperrt access/preview.py das Speichern.
"""

import re

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

ACTION_KEY = re.compile(r"^(\*|[a-z0-9_-]{1,40})$")
MAX_HIDDEN = 50


def hidden_keys(user) -> list[str]:
    keys = user.home_actions_hidden or []
    return sorted({k for k in keys if isinstance(k, str) and ACTION_KEY.match(k)})


class HomeActionsSerializer(serializers.Serializer):
    hidden = serializers.ListField(
        child=serializers.RegexField(ACTION_KEY), max_length=MAX_HIDDEN, allow_empty=True
    )


class HomeActionsView(APIView):
    """GET: ausgeblendete Schnellaktionen · PUT: Liste ersetzen."""

    @extend_schema(responses=HomeActionsSerializer)
    def get(self, request):
        return Response({"hidden": hidden_keys(request.user)})

    @extend_schema(request=HomeActionsSerializer, responses=HomeActionsSerializer)
    def put(self, request):
        data = HomeActionsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = request.user
        user.home_actions_hidden = sorted(set(data.validated_data["hidden"])) or None
        user.save(update_fields=["home_actions_hidden"])
        return Response({"hidden": hidden_keys(user)})
