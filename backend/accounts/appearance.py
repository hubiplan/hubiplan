"""Darstellung der Web-App (Mein Konto › Profil › Darstellung, X-02).

Gespeichert wird nur die Wahl „Wie Gerät / Hell / Dunkel“ am Konto, damit sie auf allen
Geräten gilt. Dunkel zeigt die Web-App nur auf den Seiten für Mitglieder (Anmeldung, Start,
Termine, Mein Konto, Mitgliederbereich); die Verwaltung bleibt hell.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

CHOICES = ("auto", "light", "dark")


class AppearanceSerializer(serializers.Serializer):
    color_scheme = serializers.ChoiceField(choices=CHOICES)


class AppearanceView(APIView):
    """GET: eigene Darstellung · PATCH: Darstellung setzen."""

    @extend_schema(responses=AppearanceSerializer)
    def get(self, request):
        return Response({"color_scheme": request.user.color_scheme})

    @extend_schema(request=AppearanceSerializer, responses=AppearanceSerializer)
    def patch(self, request):
        data = AppearanceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = request.user
        user.color_scheme = data.validated_data["color_scheme"]
        user.save(update_fields=["color_scheme"])
        return Response({"color_scheme": user.color_scheme})
