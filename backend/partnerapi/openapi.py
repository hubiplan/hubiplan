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

**Grenzen:** 600 Anfragen je Stunde und Zugang, sonst Antwort 429 mit `Retry-After`.

**Fehler:** `application/problem+json` (RFC 9457) mit einem festen `code`, zum Beispiel
`invalid_key`, `access_expired`, `access_idle`, `ip_not_allowed`, `missing_scope`,
`too_many_requests`, `not_found`, `invalid_request`, `legal_basis_missing`.

**Personendaten** (Verbandsmeldung namentlich, Mitglieder, Ehrungen, Qualifikationen) gibt ein
Zugang nur heraus, wenn die Einheit den Empfänger benannt und die Rechtsgrundlage bestätigt hat.
Kennungen (`id`, `member`) sind feste UUIDs. Jeder Abruf wird bei der Einheit protokolliert.

**Benachrichtigungen:** Auf Wunsch der Einheit sendet HUBIplan bei Änderungen ein `POST` an
eine Adresse des Empfängers, nur mit Art und Kennung, unterschrieben in der Kopfzeile
`X-HUBIplan-Signature: t=<Unixzeit>,v1=<HMAC-SHA256 über "<Unixzeit>.<Nachricht>">`.

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
    schema["info"]["license"] = {"name": "AGPL-3.0-or-later"}
    schema["servers"] = [{"url": "/", "description": "diese HUBIplan-Instanz"}]
    schema = _short_names(schema)
    components = schema.setdefault("components", {})
    components.setdefault("securitySchemes", {})["apiKey"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "hpk_…",
        "description": "API-Schlüssel aus Einstellungen › API-Zugänge",
    }
    for operations in schema.get("paths", {}).values():
        for operation in operations.values():
            if isinstance(operation, dict):
                operation["security"] = [{"apiKey": []}]
    return schema


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
