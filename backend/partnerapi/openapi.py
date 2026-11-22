"""OpenAPI-Beschreibung der API für andere Programme (docs/api.md).

Aus dem Code erzeugt und unter ``/api/partner/v1/openapi.json`` ohne Anmeldung ausgeliefert:
Sie beschreibt nur die Form der Schnittstelle, keine Daten einer Einheit.
"""

from __future__ import annotations

from functools import lru_cache

from django.conf import settings
from django.http import Http404, JsonResponse
from django.urls import include, path
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

PREFIX = "Partner"

DESCRIPTION = """\
Schnittstelle für andere Programme (Verbandssoftware, Webseiten, Fachsoftware, Skripte).

**Anmeldung:** Kopfzeile `Authorization: Bearer hpk_…`. Den Schlüssel vergibt der Vorstand der
Einheit in HUBIplan unter Einstellungen › API-Zugänge. Er gilt für genau eine Einheit und nur
für die dort angekreuzten Bereiche; welcher Bereich nötig ist, steht bei jedem Aufruf.

**Grenzen:** 600 Anfragen je Stunde und Zugang, davon höchstens 60 schreibende, sonst Antwort
429 mit `Retry-After`.

**Fehler:** `application/problem+json` (RFC 9457) mit einem festen `code`, zum Beispiel
`invalid_key`, `access_expired`, `access_idle`, `ip_not_allowed`, `missing_scope`,
`too_many_requests`, `not_found`, `invalid_request`, `legal_basis_missing`,
`write_not_allowed`, `external_id_exists`, `idempotency_conflict`, `record_locked`,
`too_many_open`.

**Personendaten** (Verbandsmeldung namentlich, Mitglieder, Ehrungen, Qualifikationen) gibt ein
Zugang nur heraus, wenn die Einheit den Empfänger benannt und die Rechtsgrundlage bestätigt hat.
Kennungen (`id`, `member`) sind feste UUIDs. Jeder Abruf wird bei der Einheit protokolliert.

**Benachrichtigungen:** Auf Wunsch der Einheit sendet HUBIplan bei Änderungen ein `POST` an
eine Adresse des Empfängers, nur mit Art und Kennung, unterschrieben in der Kopfzeile
`X-HUBIplan-Signature: t=<Unixzeit>,v1=<HMAC-SHA256 über "<Unixzeit>.<Nachricht>">`.

**Schreiben** (`POST`, `PATCH`) gibt es nur mit einem eigens angekreuzten Bereich. Geschrieben
wird Unkritisches (Termin, Ergebnis, Anwesenheit) oder ein Vorschlag bzw. Entwurf, den ein
Mensch in HUBIplan übernimmt; nichts wird gelöscht oder versendet. Ändern kann ein Zugang nur,
was er selbst angelegt hat. Mit der Kopfzeile `Idempotency-Key` (bis 100 Zeichen) legt eine
wiederholte Anfrage innerhalb von 24 Stunden nichts doppelt an; die Antwort trägt dann
`Idempotency-Replayed: true`. `external_id` ist die eigene Kennung des Dritten, je Zugang
eindeutig; unter `/lookup/` findet man den Datensatz dazu.

**Stabilität:** In `v1` kommen nur Felder und Aufrufe hinzu. Was wegfällt, wird zwölf Monate
vorher angekündigt. Unbekannte Felder bitte ignorieren.

**Zeiten** stehen in ISO 8601 mit Zeitzone. **Listen** mit `next_cursor` blättert man mit
`?cursor=…` weiter, bis `next_cursor` `null` ist.
"""


@lru_cache(maxsize=1)
def build() -> dict:
    from . import urls

    patterns = [path("api/", include(urls.v1_patterns))]
    schema = SchemaGenerator(
        title="HUBIplan API für andere Programme",
        version="1",
        description=DESCRIPTION,
        patterns=patterns,
    ).get_schema(request=None, public=True)
    # drf-spectacular übernimmt Titel, Fassung und Text aus SPECTACULAR_SETTINGS (die der
    # Verwaltungs-API), nicht aus den Angaben oben; deshalb hier ausdrücklich
    schema["info"] = {
        "title": "HUBIplan API für andere Programme",
        "version": "1",
        "description": DESCRIPTION,
        "license": {"name": "AGPL-3.0-or-later"},
    }
    schema["servers"] = [{"url": "/", "description": "diese HUBIplan-Instanz"}]
    schema = _short_names(schema)
    components = schema.setdefault("components", {})
    components.setdefault("securitySchemes", {})["apiKey"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "hpk_…",
        "description": "API-Schlüssel aus Einstellungen › API-Zugänge",
    }
    needed = _scopes(urls.v1_patterns)
    for route, operations in schema.get("paths", {}).items():
        for method, operation in operations.items():
            if isinstance(operation, dict):
                operation["security"] = [{"apiKey": []}]
                scope = needed.get((route, method))
                if scope:
                    # Welcher Bereich nötig ist, steht bei jedem Aufruf
                    operation["x-scope"] = scope
                    text = operation.get("description", "")
                    operation["description"] = f"{text}\n\nBereich: `{scope}`".strip()
    return schema


def _scopes(patterns) -> dict[tuple[str, str], str]:
    """(Adresse, Methode) → nötiger Bereich, aus den Ansichten gelesen."""
    import re

    out = {}
    for pattern in patterns:
        view = getattr(pattern.callback, "view_class", None)
        if view is None:
            continue
        route = "/api/" + re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", str(pattern.pattern))
        for method in ("get", "post", "patch", "put"):
            if not hasattr(view, method):
                continue
            write = getattr(view, "write_scope", None) if method != "get" else None
            scope = write or getattr(view, "scope", None)
            if scope:
                out[(route, method)] = scope
    return out


def _short_names(schema: dict) -> dict:
    """Im gemeinsamen Schema der Instanz heißen die Formate ``Partner…`` (eindeutig neben den
    internen); in der Beschreibung für Dritte fällt die Vorsilbe weg."""
    import json

    names = [n for n in schema.get("components", {}).get("schemas", {}) if n.startswith(PREFIX)]
    taken = set(schema.get("components", {}).get("schemas", {})) - set(names)
    text = json.dumps(schema, ensure_ascii=False)
    for name in sorted(names, key=len, reverse=True):
        short = name[len(PREFIX) :]
        if short in taken:
            continue
        text = text.replace(f'"#/components/schemas/{name}"', f'"#/components/schemas/{short}"')
        text = text.replace(f'"{name}": {{', f'"{short}": {{')
    return json.loads(text)


class OpenApiView(APIView):
    """Beschreibung der Schnittstelle als OpenAPI 3 (JSON), ohne Anmeldung."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(exclude=True)
    def get(self, request):
        if not settings.PARTNER_API_ENABLED:
            raise Http404
        response = JsonResponse(build(), json_dumps_params={"ensure_ascii": False})
        response["Access-Control-Allow-Origin"] = "*"
        response["Cache-Control"] = "public, max-age=3600"
        return response
