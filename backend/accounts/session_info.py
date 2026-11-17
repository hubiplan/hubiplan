"""Laufzeit der Anmeldung im Browser (UX-Audit 16.11., VW-04).

Die Web-App warnt zehn Minuten vor dem Ablauf und bietet „Angemeldet bleiben“ an. Dafür
braucht sie den Rest der Laufzeit; die steht am gespeicherten Sitzungseintrag, nicht im
Cookie, das die Oberfläche nicht lesen darf.
"""

from django.conf import settings
from django.contrib.sessions.models import Session
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView


class SessionInfoSerializer(serializers.Serializer):
    expires_in = serializers.IntegerField(help_text="Sekunden, bis die Anmeldung abläuft")


def remaining_seconds(request) -> int:
    """Rest der Laufzeit in Sekunden; ohne gespeicherten Eintrag die volle Laufzeit."""
    key = request.session.session_key
    expires = (
        Session.objects.filter(session_key=key).values_list("expire_date", flat=True).first()
        if key
        else None
    )
    if expires is None:
        return settings.SESSION_COOKIE_AGE
    return max(0, int((expires - timezone.now()).total_seconds()))


class SessionInfoView(APIView):
    """GET: Rest der Laufzeit · POST: Anmeldung um die volle Laufzeit verlängern."""

    @extend_schema(responses=SessionInfoSerializer)
    def get(self, request):
        return Response({"expires_in": remaining_seconds(request)})

    @extend_schema(request=None, responses=SessionInfoSerializer)
    def post(self, request):
        # Als geändert markiert, speichert die Sitzungs-Middleware den Eintrag neu und setzt
        # Ablauf und Cookie auf die volle Laufzeit ab jetzt.
        request.session.modified = True
        return Response({"expires_in": settings.SESSION_COOKIE_AGE})
