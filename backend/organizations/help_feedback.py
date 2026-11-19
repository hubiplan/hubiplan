"""Hilfe: „Hat das geholfen?“ und Suchwörter ohne Treffer (docs/hilfe.md).

Gespeichert werden nur der Hilfetext, die Sprache, die Fassung, Ja oder Nein, ein
freiwilliger Satz und der Tag; bei der Suche nur die Suchwörter mit Zähler. Keine Person,
keine Einheit, keine Adresse. Das Konto dient allein dazu, die Zahl der Rückmeldungen je
Stunde zu begrenzen (Zähler im Zwischenspeicher, nicht in der Datenbank).

Lesen und Löschen darf nur die Plattformverwaltung.
"""

from __future__ import annotations

import re

from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core.ratelimit import TooMany, too_many
from core.version import running_version

from .models import HelpFeedback, HelpSearchMiss
from .views import IsPlatformAdmin

HELP_KEY = re.compile(r"^(guide|page)\.[a-z0-9_]{1,60}$")
LANGUAGES = ("de", "en")
MAX_COMMENT = 300
MAX_TERM = 60
MAX_WORDS = 4
PER_HOUR = 30
MISSES_PER_HOUR = 60
MAX_MISSES = 2000
SHOWN_COMMENTS = 20
SHOWN_MISSES = 100


def clean_term(raw: str) -> str:
    """Suchwörter klein und ohne Mehrfach-Leerzeichen; leer, wenn sie nach Daten einer Person
    aussehen (Ziffern, E-Mail-Adresse) oder zu lang sind."""
    term = " ".join(str(raw).lower().split())
    if not 3 <= len(term) <= MAX_TERM or len(term.split(" ")) > MAX_WORDS:
        return ""
    if any(c.isdigit() for c in term) or "@" in term:
        return ""
    if not all(c.isalpha() or c in " -" for c in term):
        return ""
    return term


class FeedbackSerializer(serializers.Serializer):
    key = serializers.RegexField(HELP_KEY)
    language = serializers.ChoiceField(choices=LANGUAGES)
    helpful = serializers.BooleanField()
    comment = serializers.CharField(
        max_length=MAX_COMMENT, required=False, allow_blank=True, trim_whitespace=True
    )


class SearchMissSerializer(serializers.Serializer):
    term = serializers.CharField(max_length=200)
    language = serializers.ChoiceField(choices=LANGUAGES)


class HelpFeedbackView(APIView):
    """POST: Rückmeldung zu einem Hilfetext abgeben (jede angemeldete Person)."""

    @extend_schema(request=FeedbackSerializer, responses={204: None})
    def post(self, request):
        ser = FeedbackSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        limit_key = f"hilfe-rueckmeldung:{request.user.pk}"
        if too_many(limit_key, PER_HOUR, 3600):
            raise TooMany(limit_key, "anfragen")
        data = ser.validated_data
        helpful = data["helpful"]
        HelpFeedback.objects.create(
            key=data["key"],
            language=data["language"],
            version=running_version(),
            helpful=helpful,
            # Der Satz gehört zur Frage „Was hat gefehlt?“ und damit nur zu einem Nein
            comment="" if helpful else " ".join(data.get("comment", "").split()),
            day=timezone.localdate(),
        )
        return Response(status=204)


class HelpSearchMissView(APIView):
    """POST: Suchwörter ohne Treffer zählen (jede angemeldete Person)."""

    @extend_schema(request=SearchMissSerializer, responses={204: None})
    @transaction.atomic
    def post(self, request):
        ser = SearchMissSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        term = clean_term(ser.validated_data["term"])
        language = ser.validated_data["language"]
        limit_key = f"hilfe-suche:{request.user.pk}"
        if not term or too_many(limit_key, MISSES_PER_HOUR, 3600):
            return Response(status=204)
        today = timezone.localdate()
        updated = HelpSearchMiss.objects.filter(term=term, language=language).update(
            count=F("count") + 1, last_day=today
        )
        if not updated and HelpSearchMiss.objects.count() < MAX_MISSES:
            HelpSearchMiss.objects.get_or_create(
                term=term, language=language, defaults={"last_day": today}
            )
        return Response(status=204)


def feedback_state() -> dict:
    rows = (
        HelpFeedback.objects.values("key")
        .annotate(yes=Count("id", filter=Q(helpful=True)), no=Count("id", filter=Q(helpful=False)))
        .order_by("-no", "-yes", "key")
    )
    comments: dict[str, list[dict]] = {}
    for c in HelpFeedback.objects.exclude(comment="").order_by("-day", "-id"):
        found = comments.setdefault(c.key, [])
        if len(found) < SHOWN_COMMENTS:
            found.append(
                {
                    "id": c.pk,
                    "text": c.comment,
                    "day": c.day.isoformat(),
                    "language": c.language,
                    "version": c.version,
                }
            )
    return {
        "entries": [
            {
                "key": r["key"],
                "yes": r["yes"],
                "no": r["no"],
                "comments": comments.get(r["key"], []),
            }
            for r in rows
        ],
        "misses": [
            {
                "id": m.pk,
                "term": m.term,
                "language": m.language,
                "count": m.count,
                "last_day": m.last_day.isoformat(),
            }
            for m in HelpSearchMiss.objects.order_by("-count", "term")[:SHOWN_MISSES]
        ],
    }


@extend_schema(responses=dict)
class PlatformHelpFeedbackView(APIView):
    """GET: Rückmeldungen je Hilfetext (meiste „Nein“ zuerst) und Suchen ohne Treffer."""

    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        return Response(feedback_state())


@extend_schema(request=None, responses=dict)
class PlatformHelpCommentView(APIView):
    """DELETE: den Satz einer Rückmeldung entfernen, etwa wenn er einen Namen nennt.

    Die Antwort selbst (Nein) bleibt in der Zählung.
    """

    permission_classes = [IsPlatformAdmin]

    def delete(self, request, pk: int):
        HelpFeedback.objects.filter(pk=pk).update(comment="")
        return Response(feedback_state())


@extend_schema(request=None, responses=dict)
class PlatformHelpMissView(APIView):
    """DELETE: ein Suchwort aus der Liste nehmen (erledigt oder unpassend)."""

    permission_classes = [IsPlatformAdmin]

    def delete(self, request, pk: int):
        HelpSearchMiss.objects.filter(pk=pk).delete()
        return Response(feedback_state())
